"""Read projections for the use cases, mirroring ``commands``."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.domain.vehicle import Vehicle


@dataclass(frozen=True, slots=True)
class VehicleStatusEntry:
    """A vehicle's status, with the rental that explains it when in use."""

    vehicle: Vehicle
    current_rental: Rental | None = None


@dataclass(frozen=True, slots=True)
class FleetStatus:
    """One page of the fleet, under counts describing all of it.

    ``counts`` tallies every status over every row; ``total`` is how many rows
    the current filter can page through.
    """

    counts: Mapping[VehicleStatus, int]
    total: int
    entries: Sequence[VehicleStatusEntry]
