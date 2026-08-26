"""Input objects for the use cases: what the caller asked to change."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr

from vehicle_rental_core.domain.enums import Sex, VehicleStatus


class VehicleChanges(BaseModel):
    """A partial change to a vehicle: unset fields are left alone."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    year: int | None = None
    status: VehicleStatus | None = None

    def attributes(self) -> dict[str, Any]:
        """The descriptive fields the caller sent. ``status`` is not one: it
        moves through the entity's own rules."""
        return self.model_dump(exclude_unset=True, exclude={"status"})


class CustomerChanges(BaseModel):
    """A partial change to a customer: unset fields are left alone."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    email: EmailStr | None = None
    date_of_birth: date | None = None
    sex: Sex | None = None

    def attributes(self) -> dict[str, Any]:
        """The fields the caller sent."""
        return self.model_dump(exclude_unset=True)
