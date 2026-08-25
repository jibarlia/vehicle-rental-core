from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RentalCreate(BaseModel):
    vehicle_id: UUID
    customer_name: str = Field(min_length=1, max_length=255)
    start_at: datetime | None = None


class RentalComplete(BaseModel):
    end_at: datetime | None = None


class RentalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_id: UUID
    customer_name: str
    start_at: datetime
    end_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
