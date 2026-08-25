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

# The first mass-produced cars. A fixed floor, unlike the ceiling, which moves
# with the calendar.
MIN_MODEL_YEAR = 1900

# Fields a correction may touch. Identity, status and the audit columns are
# reached only through the methods that own their rules.
EDITABLE_FIELDS = frozenset({"model", "year"})


class Vehicle(BaseModel):
    """A vehicle in the fleet, independent of how it is stored or served.

    ``validate_assignment`` is what lets this entity drop the ``change_*``
    setters it used to need: every rule below runs on construction *and* on
    every later assignment, so there is no way to write a field and skip its
    validation.
    """

    model_config = ConfigDict(validate_assignment=True)

    # Lengths mirror the columns in ``VehicleModel``, so a value the database
    # would truncate is rejected before it ever reaches SQL.
    registration_number: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=128)
    year: int
    vehicle_type: VehicleType = VehicleType.CAR
    status: VehicleStatus = VehicleStatus.AVAILABLE
    id: UUID = Field(default_factory=uuid4)
    # Set together with ``status = RETIRED``; a database check constraint keeps
    # the two from ever disagreeing.
    #
    # Deliberately not a cross-field ``model_validator``: ``retire`` writes the
    # two fields in separate assignments, so an after-validator would fire on
    # the inconsistent intermediate state — and, unlike a field validator, would
    # leave that state in place. ``retire`` being the only writer, backed by the
    # check constraint, is the guarantee.
    retired_at: datetime | None = None
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("year")
    @classmethod
    def _plausible_year(cls, year: int) -> int:
        """Reject a model year no real vehicle could carry.

        The ceiling is next year, because manufacturers ship model years ahead
        of the calendar. It moves on its own, so there is no constant to bump,
        and because it only ever widens, a row that was valid when written stays
        readable forever.
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

        Whether a rental is active is a fact about *other* rows, so it is passed
        in — the entity states the rule, the service supplies the evidence.
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
        """Apply corrections to the vehicle's descriptive fields.

        The retired guard runs once for the whole batch; each assignment then
        re-validates itself, so there is no per-field setter to keep in step
        with the rules as fields are added.
        """
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

        Status is the one field that cannot be a plain validated assignment: the
        rules need the clock and a fact about other rows. Every route into a
        status lands here, so nothing can skip the active-rental guard or leave
        ``retired_at`` out of step with ``status`` — which the database check
        constraint would reject.
        """
        self._validate_not_retired()

        if status is VehicleStatus.RETIRED:
            self.retire(at=at, has_active_rental=has_active_rental)
        elif status is VehicleStatus.MAINTENANCE:
            self.send_to_maintenance(has_active_rental=has_active_rental)
        else:
            self.status = status
