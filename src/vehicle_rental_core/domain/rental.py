from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from vehicle_rental_core.domain.errors import (
    InvalidRentalPeriodError,
    RentalAlreadyEndedError,
)


class Rental(BaseModel):
    """A rental of one vehicle by one customer.

    Active means ``end_at IS NULL``, the same definition the partial unique
    index enforces.
    """

    model_config = ConfigDict(validate_assignment=True)

    vehicle_id: UUID
    # Nulled when the customer is deleted; customer_name outlives it so the
    # rental stays readable as history.
    customer_id: UUID | None = None
    customer_name: str = Field(min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime | None = None
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("start_at", "end_at")
    @classmethod
    def _timezone_aware(cls, value: datetime | None) -> datetime | None:
        """Reject a naive datetime rather than assume which zone it meant.

        Both columns are timestamptz, so a naive value would otherwise reach the
        comparison below against an aware one and raise TypeError.
        """
        if value is not None and value.tzinfo is None:
            raise InvalidRentalPeriodError(
                f"Rental timestamps must carry a timezone offset, got {value!r}."
            )
        return value

    @field_validator("start_at")
    @classmethod
    def _not_in_the_future(cls, start_at: datetime) -> datetime:
        """Reject a start no rental could have had.

        Backdating stays open — recording a rental that already ran is ordinary
        — but a future start would mark the vehicle in use for a rental that
        has not begun.
        """
        if start_at > datetime.now(UTC):
            raise InvalidRentalPeriodError(
                f"Rental cannot start in the future, got {start_at.isoformat()}."
            )
        return start_at

    @field_validator("end_at")
    @classmethod
    def _after_start(
        cls, end_at: datetime | None, info: ValidationInfo
    ) -> datetime | None:
        """Keep the period in order, on construction and on every assignment.

        ``info.data`` carries ``start_at`` because field validators run in
        declaration order.
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
