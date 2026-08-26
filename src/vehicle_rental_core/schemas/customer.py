from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from vehicle_rental_core.domain.enums import Sex


# Constraints live on the Customer entity, so they cover non-HTTP callers too.
class CustomerCreate(BaseModel):
    name: str
    email: EmailStr
    date_of_birth: date
    sex: Sex = Sex.UNSPECIFIED


class CustomerUpdate(BaseModel):
    """All fields optional so a PATCH can carry a partial change.

    Which fields were *sent* is the meaningful part; the router reads it with
    ``exclude_unset``.
    """

    name: str | None = None
    email: EmailStr | None = None
    date_of_birth: date | None = None
    sex: Sex | None = None


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    date_of_birth: date
    # Derived on read rather than stored, so it cannot go stale.
    age: int
    sex: Sex
    created_at: datetime | None
    updated_at: datetime | None
