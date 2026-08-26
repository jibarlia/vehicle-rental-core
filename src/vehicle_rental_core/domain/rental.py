from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from vehicle_rental_core.domain.errors import (
    InvalidRentalPeriodError,
    RentalAlreadyEndedError,
)


class Rental(BaseModel):
    """A rental of one vehicle by one customer.

    An *active* rental is defined by ``end_at IS NULL``. That single definition
    is what the partial unique index in the database enforces, so the domain and
    the schema agree on what "active" means.
    """

    model_config = ConfigDict(validate_assignment=True)

    vehicle_id: UUID
    # The id may go away; the name may not. Deleting a customer nulls the FK
    # and leaves ``customer_name`` standing, so the rental stays readable as
    # history. That asymmetry is the point, not an oversight.
    customer_id: UUID | None = None
    customer_name: str = Field(min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime | None = None
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("end_at")
    @classmethod
    def _after_start(
        cls, end_at: datetime | None, info: ValidationInfo
    ) -> datetime | None:
        """Keep the period in order, on construction and on every assignment.

        Reading ``start_at`` from ``info.data`` works because field validators
        run in declaration order and ``start_at`` is declared first. Validating
        here rather than after the write means a rejected end leaves the rental
        untouched instead of holding an impossible date.
        """
        start_at = info.data.get("start_at")
        if end_at is not None and start_at is not None and end_at < start_at:
            raise InvalidRentalPeriodError(
                "Rental end_at must be greater than or equal to start_at."
            )
        return end_at

    @property
    def is_active(self) -> bool:
        return self.end_at is None

    def complete(self, at: datetime) -> None:
        if not self.is_active:
            raise RentalAlreadyEndedError(f"Rental {self.id} already ended.")
        self.end_at = at
