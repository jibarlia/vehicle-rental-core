from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from vehicle_rental_core.domain.errors import (
    InvalidRentalPeriodError,
    RentalAlreadyEndedError,
)


@dataclass
class Rental:
    """A rental of one vehicle by one customer.

    An *active* rental is defined by ``end_at IS NULL``. That single definition
    is what the partial unique index in the database enforces, so the domain and
    the schema agree on what "active" means.
    """

    vehicle_id: UUID
    customer_name: str
    start_at: datetime
    end_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self._validate_period_order()

    @property
    def is_active(self) -> bool:
        return self.end_at is None

    def end(self, at: datetime) -> None:
        if not self.is_active:
            raise RentalAlreadyEndedError(f"Rental {self.id} already ended.")
        self.end_at = at
        self._validate_period_order()

    def _validate_period_order(self) -> None:
        if self.end_at is not None and self.end_at < self.start_at:
            raise InvalidRentalPeriodError(
                "Rental end_at must be greater than or equal to start_at."
            )
