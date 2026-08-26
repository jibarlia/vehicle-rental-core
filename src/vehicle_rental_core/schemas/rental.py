from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RentalCreate(BaseModel):
    vehicle_id: UUID
    # The customer must already exist: their name is snapshotted onto the
    # rental at start, so there is nowhere to put an unregistered one.
    customer_id: UUID
    start_at: datetime | None = None


class RentalComplete(BaseModel):
    end_at: datetime | None = None


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
