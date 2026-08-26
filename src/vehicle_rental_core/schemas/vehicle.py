from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from vehicle_rental_core.domain.enums import VehicleStatus, VehicleType
from vehicle_rental_core.schemas.rental import ActiveRentalRead


# Constraints live on the Vehicle entity, so they cover non-HTTP callers too.
# These models describe the HTTP contract, nothing more.
class VehicleCreate(BaseModel):
    registration_number: str
    model: str
    year: int
    vehicle_type: VehicleType = VehicleType.CAR


class VehicleUpdate(BaseModel):
    """All fields optional so a PATCH can carry a partial change.

    Which fields were *sent* is the meaningful part; the router reads it with
    ``exclude_unset``.
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


class VehicleStatusRead(BaseModel):
    """A vehicle as it appears on a status board.

    Deliberately not a subclass of :class:`VehicleRead`: inheriting would
    re-fatten this response the day ``VehicleRead`` gains a field.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    registration_number: str
    model: str
    year: int
    status: VehicleStatus
    current_rental: ActiveRentalRead | None = None


class FleetStatusRead(BaseModel):
    """The fleet at a glance: counts over every vehicle, plus one page of them.

    ``counts`` covers the whole fleet, every status included at zero;
    ``total`` is scoped to the filter, and so to what ``items`` can yield.
    """

    counts: dict[VehicleStatus, int]
    total: int
    items: list[VehicleStatusRead]
