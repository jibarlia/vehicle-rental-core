from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from vehicle_rental_core.domain.enums import VehicleStatus, VehicleType
from vehicle_rental_core.schemas.rental import ActiveRentalRead


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


class VehicleStatusRead(BaseModel):
    """A vehicle as it appears on a status board.

    Deliberately *not* a subclass of :class:`VehicleRead`. Only what a board
    displays is here — ``version``, ``retired_at``, ``vehicle_type`` and the
    audit timestamps are dropped, since they are paid for on every row of every
    page and shown on none. Declaring the fields outright is what keeps that
    true: inheriting would re-fatten this response the day ``VehicleRead``
    gains a field.

    ``registration_number`` stays: it is how a person identifies a vehicle.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    registration_number: str
    model: str
    year: int
    status: VehicleStatus
    # Present only while the vehicle is out — the rental is what explains an
    # ``in_use`` status, and there is nothing to explain for the others.
    current_rental: ActiveRentalRead | None = None


class FleetStatusRead(BaseModel):
    """The fleet at a glance: counts over every vehicle, plus one page of them.

    ``counts`` covers the whole fleet and is unaffected by ``status``,
    ``offset`` and ``limit``. Every status appears, zero included, so a client
    can render a fixed set of tiles.

    ``total`` is scoped to the filter instead: it is how many vehicles match
    ``status``, and so how many ``items`` can yield across every page.
    """

    counts: dict[VehicleStatus, int]
    total: int
    items: list[VehicleStatusRead]
