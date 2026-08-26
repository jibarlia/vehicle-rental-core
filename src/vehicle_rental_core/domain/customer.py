from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from vehicle_rental_core.domain.enums import Sex
from vehicle_rental_core.domain.errors import InvalidDateOfBirthError

# No verified human has reached this age.
MAX_AGE_YEARS = 120


class Customer(BaseModel):
    """Someone who rents vehicles, independent of how they are stored."""

    model_config = ConfigDict(validate_assignment=True)

    # Mirrors the column in CustomerModel, so SQL never has to truncate.
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    date_of_birth: date
    sex: Sex = Sex.UNSPECIFIED
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("date_of_birth")
    @classmethod
    def _plausible_date_of_birth(cls, date_of_birth: date) -> date:
        """Reject a birth date no living customer could carry.

        Validates input only: the floor advances with the calendar, so a stored
        row can later fall outside the range.
        """
        today = datetime.now(UTC).date()
        if date_of_birth > today:
            raise InvalidDateOfBirthError(
                f"Date of birth {date_of_birth} is in the future."
            )

        # By year, not a floor date: date(year - 120, 2, 29) raises on a leap day.
        if today.year - date_of_birth.year > MAX_AGE_YEARS:
            raise InvalidDateOfBirthError(
                f"Date of birth {date_of_birth} implies an age over {MAX_AGE_YEARS}."
            )
        return date_of_birth

    @property
    def age(self) -> int:
        """Whole years lived, derived so it cannot go stale."""
        today = datetime.now(UTC).date()
        born = self.date_of_birth
        had_birthday_this_year = (today.month, today.day) >= (born.month, born.day)
        return today.year - born.year - (0 if had_birthday_this_year else 1)
