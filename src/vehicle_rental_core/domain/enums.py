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

    ``RETIRED`` is terminal: the vehicle leaves the fleet, but its row and its
    rental history are kept. It is the only supported way to take a vehicle out
    of service — a hard ``DELETE`` cascades and destroys the rentals with it.
    """

    AVAILABLE = "available"
    IN_USE = "in_use"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"
