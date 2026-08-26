from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from vehicle_rental_core.domain import customer as customer_module
from vehicle_rental_core.domain.customer import MAX_AGE_YEARS, Customer
from vehicle_rental_core.domain.enums import Sex
from vehicle_rental_core.domain.errors import InvalidDateOfBirthError

TODAY = datetime.now(UTC).date()


def _customer(**overrides: object) -> Customer:
    defaults: dict[str, object] = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "date_of_birth": date(1990, 6, 1),
    }
    return Customer(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestDefaults:
    def test_sex_should_default_to_unspecified(self) -> None:
        assert _customer().sex is Sex.UNSPECIFIED


class TestNameValidation:
    def test_should_reject_a_blank_name(self) -> None:
        with pytest.raises(ValidationError):
            _customer(name="")

    def test_should_reject_a_blank_name_on_assignment(self) -> None:
        # validate_assignment is what makes the rule cover later writes too.
        customer = _customer()

        with pytest.raises(ValidationError):
            customer.name = ""


class TestEmailValidation:
    @pytest.mark.parametrize("email", ["not-an-email", "@example.com", "ada@"])
    def test_should_reject_a_malformed_address(self, email: str) -> None:
        with pytest.raises(ValidationError):
            _customer(email=email)

    def test_should_reject_a_malformed_address_on_assignment(self) -> None:
        customer = _customer()

        with pytest.raises(ValidationError):
            customer.email = "nope"


class TestDateOfBirthValidation:
    def test_should_reject_a_future_date(self) -> None:
        with pytest.raises(InvalidDateOfBirthError):
            _customer(date_of_birth=TODAY + timedelta(days=1))

    def test_should_reject_an_implausibly_old_date(self) -> None:
        with pytest.raises(InvalidDateOfBirthError):
            _customer(date_of_birth=date(TODAY.year - MAX_AGE_YEARS - 1, 1, 1))

    def test_should_accept_a_birth_date_of_today(self) -> None:
        assert _customer(date_of_birth=TODAY).age == 0

    def test_should_reject_a_future_date_on_assignment(self) -> None:
        customer = _customer()

        with pytest.raises(InvalidDateOfBirthError):
            customer.date_of_birth = TODAY + timedelta(days=1)


class TestAge:
    """Clock frozen: age depends on today's date, so a live clock would make
    these pass or fail depending on the day they run."""

    @pytest.fixture
    def _frozen_clock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        frozen = datetime(2026, 6, 15, tzinfo=UTC)

        class _FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
                return frozen

        monkeypatch.setattr(customer_module, "datetime", _FrozenDatetime)

    @pytest.mark.parametrize(
        ("born", "expected"),
        [
            (date(1996, 6, 14), 30),  # birthday was yesterday
            (date(1996, 6, 15), 30),  # birthday is today
            (date(1996, 6, 16), 29),  # birthday is tomorrow
            (date(1996, 12, 31), 29),  # birthday later this year
            (date(1996, 1, 1), 30),  # birthday earlier this year
        ],
    )
    def test_should_count_whole_years_lived(
        self, _frozen_clock: None, born: date, expected: int
    ) -> None:
        assert _customer(date_of_birth=born).age == expected

    def test_should_be_derived_not_stored(self) -> None:
        # No age field to set: it is computed, so it cannot go stale.
        assert "age" not in Customer.model_fields
