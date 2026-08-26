"""Read projections for the use cases.

These are the mirror of ``commands``: a command carries *what the caller asked
to change*, a view carries *what the caller asked to see*. Neither is a domain
entity, which is why both live here rather than in ``domain``.

They compose the existing entities instead of restating their fields, so a view
cannot drift out of step with the thing it is describing.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from vehicle_rental_core.domain.enums import VehicleStatus
from vehicle_rental_core.domain.rental import Rental
from vehicle_rental_core.domain.vehicle import Vehicle


@dataclass(frozen=True, slots=True)
class VehicleStatusEntry:
    """A vehicle's status, with the rental that explains it when in use.

    ``current_rental`` is set only for a vehicle that is out — for every other
    status there is nothing to explain, so it stays ``None`` and costs no query.
    """

    vehicle: Vehicle
    current_rental: Rental | None = None


@dataclass(frozen=True, slots=True)
class FleetStatus:
    """One page of the fleet, under counts describing all of it.

    ``counts`` and ``total`` are deliberately *not* narrowed by the filter or
    the page that produced ``entries``: the question "how is the fleet doing?"
    is not the question "what is on this screen?". Counts stay one aggregate
    over every row, so their size does not grow with the fleet.
    """

    counts: Mapping[VehicleStatus, int]
    total: int
    entries: Sequence[VehicleStatusEntry]
