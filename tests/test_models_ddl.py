"""Pins the schema contract: the indexes and constraints the rules depend on.

These compile DDL against the PostgreSQL dialect — no connection is opened.
A model refactor that silently drops one of these fails here.
"""

from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from vehicle_rental_core.infrastructure.db.base import Base
from vehicle_rental_core.infrastructure.models.rental import RentalModel
from vehicle_rental_core.infrastructure.models.vehicle import VehicleModel

# Annotated so the compile() calls below stay in a typed context.
_DIALECT: Dialect = postgresql.dialect()  # type: ignore[no-untyped-call]


def _create_table(model: type[Base]) -> str:
    statement = CreateTable(model.__table__)  # type: ignore[arg-type]
    return str(statement.compile(dialect=_DIALECT))


def _indexes(model: type[Base]) -> dict[str, str]:
    return {
        index.name: str(CreateIndex(index).compile(dialect=_DIALECT))
        for index in model.__table__.indexes  # type: ignore[attr-defined]
        if index.name is not None
    }


class TestTableNames:
    def test_tables_should_be_plural(self) -> None:
        assert VehicleModel.__tablename__ == "vehicles"
        assert RentalModel.__tablename__ == "rentals"


class TestVehicleIndexes:
    def test_should_index_status_for_the_status_filter(self) -> None:
        ddl = _indexes(VehicleModel)["ix_vehicles_status"]

        assert "CREATE INDEX ix_vehicles_status ON vehicles (status)" in ddl

    def test_registration_number_should_be_uniquely_indexed(self) -> None:
        ddl = _indexes(VehicleModel)["ix_vehicles_registration_number"]

        assert "CREATE UNIQUE INDEX" in ddl
        assert "(registration_number)" in ddl


class TestVehicleConstraints:
    def test_should_constrain_vehicle_type_to_known_values(self) -> None:
        ddl = _create_table(VehicleModel)

        assert "ck_vehicles_vehicle_type" in ddl
        assert "vehicle_type IN ('car')" in ddl

    def test_should_constrain_status_to_known_values(self) -> None:
        ddl = _create_table(VehicleModel)

        assert "status IN ('available', 'in_use', 'maintenance', 'retired')" in ddl

    def test_retired_at_should_be_nullable(self) -> None:
        assert VehicleModel.__table__.c.retired_at.nullable is True

    def test_should_tie_retired_status_to_the_retire_timestamp(self) -> None:
        ddl = _create_table(VehicleModel)

        # Neither can move without the other, so no query has to guess which
        # of the two is authoritative.
        assert "ck_vehicles_retired_status_matches_timestamp" in ddl
        assert "(status = 'retired') = (retired_at IS NOT NULL)" in ddl

    def test_should_carry_a_version_column_for_optimistic_locking(self) -> None:
        version_column = VehicleModel.__mapper__.version_id_col

        assert version_column is VehicleModel.__table__.c.version


class TestRentalIndexes:
    def test_should_allow_only_one_active_rental_per_vehicle(self) -> None:
        ddl = _indexes(RentalModel)["uq_rentals_one_active_per_vehicle"]

        assert "CREATE UNIQUE INDEX" in ddl
        assert "(vehicle_id)" in ddl
        # The partial predicate is what permits many *ended* rentals per vehicle.
        assert "WHERE end_at IS NULL" in ddl

    def test_should_index_rental_history_newest_first(self) -> None:
        ddl = _indexes(RentalModel)["ix_rentals_vehicle_start_at"]

        assert "(vehicle_id, start_at DESC)" in ddl


class TestRentalConstraints:
    def test_should_require_end_at_to_follow_start_at(self) -> None:
        ddl = _create_table(RentalModel)

        assert "ck_rentals_end_at_after_start_at" in ddl
        assert "end_at IS NULL OR end_at >= start_at" in ddl

    def test_should_cascade_hard_deletion_of_a_vehicle(self) -> None:
        ddl = _create_table(RentalModel)

        # A rental is meaningless without its vehicle, so a hard delete takes
        # the rentals with it. Retiring a vehicle for real is retiring.
        assert "ON DELETE CASCADE" in ddl

    def test_end_at_should_be_nullable_because_null_means_active(self) -> None:
        assert RentalModel.__table__.c.end_at.nullable is True
