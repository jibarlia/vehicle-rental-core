from enum import StrEnum


class VehicleType(StrEnum):
    """Kind of vehicle in the fleet.

    Only ``CAR`` is in use today. The type exists so motorcycles, vans and
    trucks become additive changes — a new member plus a migration widening the
    check constraint — rather than a schema redesign.
    """

    CAR = "car"


class VehicleStatus(StrEnum):
    """Lifecycle state of a vehicle.

    ``ARCHIVED`` is terminal: the vehicle is retired from the fleet but its row
    and rental history are retained. It is the only supported way to retire a
    vehicle — a hard ``DELETE`` cascades and destroys the rentals with it.
    """

    AVAILABLE = "available"
    IN_USE = "in_use"
    MAINTENANCE = "maintenance"
    ARCHIVED = "archived"
