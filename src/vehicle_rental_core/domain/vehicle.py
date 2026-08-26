from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vehicle_rental_core.domain.enums import VehicleStatus, VehicleType
from vehicle_rental_core.domain.errors import (
    InvalidVehicleYearError,
    VehicleHasActiveRentalError,
    VehicleRetiredError,
)

# The first mass-produced cars.
MIN_MODEL_YEAR = 1900

EDITABLE_FIELDS = frozenset({"model", "year"})


class Vehicle(BaseModel):
    """A vehicle in the fleet, independent of how it is stored or served."""

    model_config = ConfigDict(validate_assignment=True)

    # Lengths mirror VehicleModel, so a value the database would truncate is
    # rejected before it reaches SQL.
    registration_number: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=128)
    year: int
    vehicle_type: VehicleType = VehicleType.CAR
    status: VehicleStatus = VehicleStatus.AVAILABLE
    id: UUID = Field(default_factory=uuid4)
    # Not a cross-field model_validator: retire() writes this and status in
    # separate assignments, so an after-validator would fire on the inconsistent
    # intermediate state and leave it in place.
    retired_at: datetime | None = None
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("year")
    @classmethod
    def _plausible_year(cls, year: int) -> int:
        """Reject a model year no real vehicle could carry.

        The ceiling is next year: manufacturers ship model years ahead of the
        calendar, and a ceiling that only widens keeps old rows readable.
        """
        ceiling = datetime.now(UTC).year + 1
        if not MIN_MODEL_YEAR <= year <= ceiling:
            raise InvalidVehicleYearError(
                f"Vehicle year must be between {MIN_MODEL_YEAR} and {ceiling}, "
                f"got {year}."
            )
        return year

    @property
    def is_retired(self) -> bool:
        return self.status is VehicleStatus.RETIRED

    @property
    def is_rentable(self) -> bool:
        return self.status is VehicleStatus.AVAILABLE

    def _validate_no_active_rental(self, *, has_active_rental: bool) -> None:
        """Guard the transitions a live rental must block.

        The fact is passed in because it concerns other rows: the entity states
        the rule, the service supplies the evidence.
        """
        if has_active_rental:
            raise VehicleHasActiveRentalError(
                f"Vehicle {self.id} has an active rental."
            )

    def _validate_not_retired(self) -> None:
        """Retiring is terminal, so a retired vehicle accepts no changes."""
        if self.is_retired:
            raise VehicleRetiredError(f"Vehicle {self.id} is retired.")

    def apply(self, changes: Mapping[str, Any]) -> None:
        """Apply corrections to the vehicle's descriptive fields."""
        if not changes:
            return

        self._validate_not_retired()
        for name, value in changes.items():
            if name not in EDITABLE_FIELDS:
                raise ValueError(f"{name!r} is not a correctable field.")
            setattr(self, name, value)

    def retire(self, *, at: datetime, has_active_rental: bool) -> None:
        """Retire the vehicle, keeping the row and its rental history."""
        self._validate_not_retired()
        self._validate_no_active_rental(has_active_rental=has_active_rental)
        self.status = VehicleStatus.RETIRED
        self.retired_at = at

    def send_to_maintenance(self, *, has_active_rental: bool) -> None:
        self._validate_not_retired()
        self._validate_no_active_rental(has_active_rental=has_active_rental)
        self.status = VehicleStatus.MAINTENANCE

    def change_status(
        self, status: VehicleStatus, *, at: datetime, has_active_rental: bool
    ) -> None:
        """Apply a status change through the rules that govern it.

        Every route into a status lands here, so nothing can skip the
        active-rental guard or leave ``retired_at`` out of step with ``status``.
        """
        self._validate_not_retired()

        if status is VehicleStatus.RETIRED:
            self.retire(at=at, has_active_rental=has_active_rental)
        elif status is VehicleStatus.MAINTENANCE:
            self.send_to_maintenance(has_active_rental=has_active_rental)
        else:
            self.status = status
