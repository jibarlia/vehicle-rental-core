"""Input objects for the use cases.

These sit between the API contract in ``schemas`` and the entities in
``domain``: they carry *what the caller asked to change*, which is a different
question from *what a vehicle is*. Keeping them here is what lets a service take
a partial change without importing an HTTP schema.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr

from vehicle_rental_core.domain.enums import Sex, VehicleStatus


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


class CustomerChanges(BaseModel):
    """A partial change to a customer: unset fields are left alone.

    As with :class:`VehicleChanges`, field constraints live on the entity so
    they apply to every caller, not only those arriving through here.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    email: EmailStr | None = None
    date_of_birth: date | None = None
    sex: Sex | None = None

    def attributes(self) -> dict[str, Any]:
        """The fields the caller actually sent.

        Nothing is excluded: every customer field is a plain validated
        assignment, unlike a vehicle's ``status``, which moves through rules
        that need a clock and facts about other rows.
        """
        return self.model_dump(exclude_unset=True)
