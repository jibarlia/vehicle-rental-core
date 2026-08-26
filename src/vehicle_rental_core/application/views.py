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

    The two answer different questions, and are scoped accordingly:

    ``counts`` is the fleet tally — every status over every row, untouched by
    the filter or the page, because "how is the fleet doing?" is not "what is
    on this screen?". Its size is fixed, so it does not grow with the fleet.

    ``total`` is how many rows the caller can page through under the filter
    that produced ``entries``. Keeping it in step with ``entries`` is the whole
    of its job: a total that counts rows no amount of paging will reach is
    worse than no total at all.
    """

    counts: Mapping[VehicleStatus, int]
    total: int
    entries: Sequence[VehicleStatusEntry]
