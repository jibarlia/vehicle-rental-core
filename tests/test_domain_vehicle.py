from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from vehicle_rental_core.domain.enums import VehicleStatus, VehicleType
from vehicle_rental_core.domain.errors import (
    InvalidVehicleYearError,
    VehicleHasActiveRentalError,
    VehicleRetiredError,
)
from vehicle_rental_core.domain.vehicle import MIN_MODEL_YEAR, Vehicle

NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _vehicle(**overrides: object) -> Vehicle:
    defaults: dict[str, object] = {
        "registration_number": "AA-111",
        "model": "Corolla",
        "year": 2022,
    }
    return Vehicle(**{**defaults, **overrides})  # type: ignore[arg-type]


def _retired() -> Vehicle:
    vehicle = _vehicle()
    vehicle.retire(at=NOW, has_active_rental=False)
    return vehicle


class TestVehicleDefaults:
    def test_should_default_to_an_available_car(self) -> None:
        vehicle = _vehicle()

        assert vehicle.vehicle_type is VehicleType.CAR
        assert vehicle.status is VehicleStatus.AVAILABLE
        assert vehicle.is_retired is False
        assert vehicle.is_rentable is True


class TestRentability:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (VehicleStatus.AVAILABLE, True),
            (VehicleStatus.IN_USE, False),
            (VehicleStatus.MAINTENANCE, False),
            (VehicleStatus.RETIRED, False),
        ],
    )
    def test_only_available_vehicles_should_be_rentable(
        self, status: VehicleStatus, expected: bool
    ) -> None:
        assert _vehicle(status=status).is_rentable is expected


class TestRetiring:
    def test_should_set_status_and_timestamp_together(self) -> None:
        # The database check constraint requires these two to agree, so the
        # entity must never move one without the other.
        vehicle = _retired()

        assert vehicle.status is VehicleStatus.RETIRED
        assert vehicle.retired_at == NOW
        assert vehicle.is_retired is True

    def test_should_refuse_retiring_while_a_rental_is_active(self) -> None:
        vehicle = _vehicle()

        with pytest.raises(VehicleHasActiveRentalError):
            vehicle.retire(at=NOW, has_active_rental=True)

        assert vehicle.is_retired is False
        assert vehicle.retired_at is None

    def test_retiring_should_be_terminal(self) -> None:
        vehicle = _retired()

        with pytest.raises(VehicleRetiredError):
            vehicle.retire(at=NOW, has_active_rental=False)

    def test_retired_vehicle_should_refuse_maintenance(self) -> None:
        vehicle = _retired()

        with pytest.raises(VehicleRetiredError):
            vehicle.send_to_maintenance(has_active_rental=False)

    def test_retired_vehicle_should_refuse_any_status_change(self) -> None:
        vehicle = _retired()

        with pytest.raises(VehicleRetiredError):
            vehicle.change_status(
                VehicleStatus.AVAILABLE, at=NOW, has_active_rental=False
            )

        assert vehicle.status is VehicleStatus.RETIRED


class TestMaintenance:
    def test_should_move_to_maintenance_when_no_rental_is_active(self) -> None:
        vehicle = _vehicle()

        vehicle.send_to_maintenance(has_active_rental=False)

        assert vehicle.status is VehicleStatus.MAINTENANCE

    def test_should_refuse_maintenance_while_a_rental_is_active(self) -> None:
        vehicle = _vehicle()

        with pytest.raises(VehicleHasActiveRentalError):
            vehicle.send_to_maintenance(has_active_rental=True)

        assert vehicle.status is VehicleStatus.AVAILABLE


class TestChangeStatus:
    def test_should_route_retiring_through_the_active_rental_guard(self) -> None:
        vehicle = _vehicle()

        with pytest.raises(VehicleHasActiveRentalError):
            vehicle.change_status(VehicleStatus.RETIRED, at=NOW, has_active_rental=True)

    def test_should_route_maintenance_through_the_active_rental_guard(self) -> None:
        vehicle = _vehicle()

        with pytest.raises(VehicleHasActiveRentalError):
            vehicle.change_status(
                VehicleStatus.MAINTENANCE, at=NOW, has_active_rental=True
            )

    def test_should_stamp_retired_at_when_retiring_via_status_change(self) -> None:
        vehicle = _vehicle()

        vehicle.change_status(VehicleStatus.RETIRED, at=NOW, has_active_rental=False)

        assert vehicle.retired_at == NOW

    def test_unguarded_status_changes_should_apply_directly(self) -> None:
        vehicle = _vehicle(status=VehicleStatus.MAINTENANCE)

        vehicle.change_status(VehicleStatus.AVAILABLE, at=NOW, has_active_rental=False)

        assert vehicle.status is VehicleStatus.AVAILABLE
        assert vehicle.retired_at is None


class TestYearValidation:
    """Validation runs in the constructor, so no caller can skip it."""

    @staticmethod
    def _next_year() -> int:
        # Derived the same way the entity derives it, so the test stays correct
        # as the calendar moves without freezing the clock.
        return datetime.now(UTC).year + 1

    def test_should_accept_the_current_model_year(self) -> None:
        assert _vehicle(year=datetime.now(UTC).year).year > MIN_MODEL_YEAR

    def test_should_accept_next_years_model(self) -> None:
        # Manufacturers ship model years ahead of the calendar.
        assert _vehicle(year=self._next_year()).year == self._next_year()

    def test_should_reject_a_year_beyond_next_year(self) -> None:
        with pytest.raises(InvalidVehicleYearError):
            _vehicle(year=self._next_year() + 1)

    def test_ceiling_should_track_the_calendar(self) -> None:
        # The boundary is not a constant: it sits exactly one year ahead of now,
        # so nothing needs bumping as years pass.
        _vehicle(year=self._next_year())

        with pytest.raises(InvalidVehicleYearError):
            _vehicle(year=self._next_year() + 1)

    def test_should_accept_the_oldest_plausible_year(self) -> None:
        assert _vehicle(year=MIN_MODEL_YEAR).year == MIN_MODEL_YEAR

    def test_should_reject_a_year_before_cars_existed(self) -> None:
        with pytest.raises(InvalidVehicleYearError):
            _vehicle(year=MIN_MODEL_YEAR - 1)

    def test_should_reject_a_transposed_typo(self) -> None:
        # 2202 for 2022 is the mistake a loose ceiling like 2100 let through.
        with pytest.raises(InvalidVehicleYearError):
            _vehicle(year=2202)


class TestFieldAssignment:
    """Validation runs on assignment too, so there is no setter to bypass."""

    def test_should_apply_a_valid_correction(self) -> None:
        vehicle = _vehicle(year=2022)

        vehicle.year = 2023

        assert vehicle.year == 2023

    def test_should_reject_an_implausible_correction(self) -> None:
        vehicle = _vehicle(year=2022)

        with pytest.raises(InvalidVehicleYearError):
            vehicle.year = 99999

        # The rule runs before the write, so a rejected correction leaves the
        # entity on its last good value.
        assert vehicle.year == 2022

    def test_should_reject_a_blank_model(self) -> None:
        vehicle = _vehicle(model="Corolla")

        with pytest.raises(ValidationError):
            vehicle.model = ""

        assert vehicle.model == "Corolla"


class TestApplyingCorrections:
    def test_should_apply_every_field_it_is_given(self) -> None:
        vehicle = _vehicle(model="Corolla", year=2022)

        vehicle.apply({"model": "Civic", "year": 2023})

        assert vehicle.model == "Civic"
        assert vehicle.year == 2023

    def test_should_leave_fields_it_is_not_given_alone(self) -> None:
        vehicle = _vehicle(model="Corolla", year=2022)

        vehicle.apply({"year": 2023})

        assert vehicle.model == "Corolla"

    def test_should_validate_each_field_it_applies(self) -> None:
        vehicle = _vehicle(year=2022)

        with pytest.raises(InvalidVehicleYearError):
            vehicle.apply({"year": 99999})

    def test_should_refuse_a_field_that_is_not_a_correction(self) -> None:
        # Status and identity have their own rules; reaching them through a
        # correction would skip every one of them.
        vehicle = _vehicle()

        with pytest.raises(ValueError, match="not a correctable field"):
            vehicle.apply({"status": VehicleStatus.RETIRED})

    def test_should_refuse_to_change_a_retired_vehicle(self) -> None:
        with pytest.raises(VehicleRetiredError):
            _retired().apply({"model": "Civic"})

    def test_should_accept_an_empty_correction(self) -> None:
        # A PATCH carrying only a status change reaches here with nothing to do.
        retired = _retired()

        retired.apply({})

        assert retired.model == "Corolla"
