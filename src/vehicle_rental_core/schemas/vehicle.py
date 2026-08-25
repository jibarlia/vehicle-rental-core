from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from vehicle_rental_core.domain.enums import VehicleStatus, VehicleType


# Constraints are not duplicated in this module: the Vehicle entity validates
# its own fields on construction and on every assignment, so the rules cover
# non-HTTP callers too. These models describe the HTTP contract, nothing more.
class VehicleCreate(BaseModel):
    registration_number: str
    model: str
    year: int
    vehicle_type: VehicleType = VehicleType.CAR


class VehicleUpdate(BaseModel):
    """All fields optional so a PATCH can carry a partial change.

    Which fields were *sent* is the meaningful part — the router reads it with
    ``exclude_unset`` rather than treating ``None`` as "absent".
    """

    model: str | None = None
    year: int | None = None
    status: VehicleStatus | None = None


class VehicleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vehicle_type: VehicleType
    registration_number: str
    model: str
    year: int
    status: VehicleStatus
    version: int
    retired_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
