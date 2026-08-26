from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from vehicle_rental_core.domain.enums import Sex


# Constraints are not duplicated in this module: the Customer entity validates
# its own fields on construction and on every assignment, so the rules cover
# non-HTTP callers too. These models describe the HTTP contract, nothing more.
class CustomerCreate(BaseModel):
    name: str
    email: EmailStr
    date_of_birth: date
    sex: Sex = Sex.UNSPECIFIED


class CustomerUpdate(BaseModel):
    """All fields optional so a PATCH can carry a partial change.

    Which fields were *sent* is the meaningful part — the router reads it with
    ``exclude_unset`` rather than treating ``None`` as "absent".
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
    # Derived from date_of_birth on every read rather than stored, so it cannot
    # go stale. Served alongside the birth date, not instead of it.
    age: int
    sex: Sex
    created_at: datetime | None
    updated_at: datetime | None
