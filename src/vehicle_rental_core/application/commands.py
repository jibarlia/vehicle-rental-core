"""Input objects for the use cases.

These sit between the API contract in ``schemas`` and the entities in
``domain``: they carry *what the caller asked to change*, which is a different
question from *what a vehicle is*. Keeping them here is what lets a service take
a partial change without importing an HTTP schema.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from vehicle_rental_core.domain.enums import VehicleStatus


class VehicleChanges(BaseModel):
    """A partial change to a vehicle: unset fields are left alone.

    Field constraints are deliberately absent — the entity owns them, so they
    apply to every caller rather than only the ones who come through here.
    """

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    year: int | None = None
    status: VehicleStatus | None = None

    def attributes(self) -> dict[str, Any]:
        """The descriptive fields the caller actually sent.

        ``exclude_unset`` is what distinguishes "omitted" from "sent as null",
        which a ``None`` default alone cannot. ``status`` is excluded because it
        is not a plain assignment — it moves through the entity's own rules.
        """
        return self.model_dump(exclude_unset=True, exclude={"status"})
