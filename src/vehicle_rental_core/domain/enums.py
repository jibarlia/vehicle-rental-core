from enum import StrEnum


class VehicleType(StrEnum):
    """Kind of vehicle in the fleet.

    Only ``CAR`` today; the type exists so other kinds are additive.
    """

    CAR = "car"


class Sex(StrEnum):
    """A customer's recorded sex.

    ``UNSPECIFIED`` exists so the column can stay ``NOT NULL``.
    """

    MALE = "male"
    FEMALE = "female"
    UNSPECIFIED = "unspecified"


class VehicleStatus(StrEnum):
    """Lifecycle state of a vehicle.

    ``RETIRED`` is terminal and keeps the row and its rental history.
    """

    AVAILABLE = "available"
    IN_USE = "in_use"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"
