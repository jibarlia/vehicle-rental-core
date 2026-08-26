from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RentalCreate(BaseModel):
    vehicle_id: UUID
    # Must already exist: the name is snapshotted from their record.
    customer_id: UUID
    start_at: datetime | None = None


class RentalComplete(BaseModel):
    end_at: datetime | None = None


class ActiveRentalRead(BaseModel):
    """An open rental, as it appears inside a vehicle's status.

    A deliberate subset of :class:`RentalRead`; the full record is one
    ``GET /rentals/{id}`` away.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID | None
    customer_name: str
    start_at: datetime


class RentalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_id: UUID
    # Null once the customer has been deleted; customer_name outlives it.
    customer_id: UUID | None
    customer_name: str
    start_at: datetime
    end_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
