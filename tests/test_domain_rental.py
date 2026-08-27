from datetime import UTC, datetime
from uuid import uuid4

import pytest

from vehicle_rental_core.domain.errors import (
    InvalidRentalPeriodError,
    RentalAlreadyEndedError,
)
from vehicle_rental_core.domain.rental import Rental

START = datetime(2026, 1, 1, tzinfo=UTC)


def _rental(**overrides: object) -> Rental:
    defaults: dict[str, object] = {
        "vehicle_id": uuid4(),
        "customer_name": "Ada Lovelace",
        "start_at": START,
    }
    return Rental(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestRentalPeriod:
    def test_open_rental_should_be_active(self) -> None:
        assert _rental().is_active is True

    def test_closed_rental_should_not_be_active(self) -> None:
        assert _rental(end_at=START).is_active is False

    def test_end_at_equal_to_start_at_should_be_allowed(self) -> None:
        # The rule is end_at >= start_at, so a zero-length rental is valid.
        assert _rental(end_at=START).end_at == START

    def test_end_at_before_start_at_should_be_rejected(self) -> None:
        with pytest.raises(InvalidRentalPeriodError):
            _rental(end_at=datetime(2025, 12, 31, tzinfo=UTC))


class TestNaiveTimestamps:
    def test_naive_start_at_should_be_rejected(self) -> None:
        with pytest.raises(InvalidRentalPeriodError):
            _rental(start_at=datetime(2026, 1, 1))

    def test_naive_end_at_should_be_rejected(self) -> None:
        with pytest.raises(InvalidRentalPeriodError):
            _rental(end_at=datetime(2026, 1, 5))

    def test_completing_with_a_naive_end_should_be_rejected(self) -> None:
        rental = _rental()

        with pytest.raises(InvalidRentalPeriodError):
            rental.complete(datetime(2026, 1, 5))

        assert rental.is_active is True


class TestCompletingARental:
    def test_should_close_an_active_rental(self) -> None:
        rental = _rental()
        finished = datetime(2026, 1, 5, tzinfo=UTC)

        rental.complete(finished)

        assert rental.end_at == finished
        assert rental.is_active is False

    def test_should_reject_completing_before_it_started(self) -> None:
        rental = _rental()

        with pytest.raises(InvalidRentalPeriodError):
            rental.complete(datetime(2025, 1, 1, tzinfo=UTC))

        # Validation runs before the write, so the rental stays open.
        assert rental.end_at is None
        assert rental.is_active is True

    def test_should_reject_completing_twice(self) -> None:
        rental = _rental()
        rental.complete(datetime(2026, 1, 5, tzinfo=UTC))

        with pytest.raises(RentalAlreadyEndedError):
            rental.complete(datetime(2026, 1, 6, tzinfo=UTC))
