from typing import cast

from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.schema import CreateTable

from vehicle_rental_core.infrastructure.db import TimestampMixin


class _Base(DeclarativeBase):
    """Throwaway metadata so this probe table never reaches a real migration."""


class _Widget(TimestampMixin, _Base):
    __tablename__ = "widgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


def _table_of(model: type[_Base]) -> Table:
    # __table__ is declared as FromClause on DeclarativeBase; every mapped
    # class here is backed by a real Table.
    return cast(Table, model.__table__)


def _compiled_ddl() -> str:
    statement = CreateTable(_table_of(_Widget))
    # DDLElement.compile() is untyped in SQLAlchemy's own annotations.
    compiled = statement.compile(dialect=postgresql.dialect())  # type: ignore[no-untyped-call]
    return str(compiled)


class TestTimestampMixin:
    def test_should_declare_database_side_defaults(self) -> None:
        created = _table_of(_Widget).c.created_at
        updated = _table_of(_Widget).c.updated_at

        assert created.server_default is not None
        assert updated.server_default is not None
        assert created.onupdate is None  # created_at must never be rewritten
        assert updated.onupdate is not None
        assert created.nullable is False
        assert updated.nullable is False

    def test_should_emit_not_null_defaults_in_postgres_ddl(self) -> None:
        # Compiling the DDL proves the INSERT path is covered without opening a
        # connection: PostgreSQL fills both columns, so neither can arrive NULL.
        ddl = _compiled_ddl().lower()

        assert "created_at timestamp with time zone default now() not null" in ddl
        assert "updated_at timestamp with time zone default now() not null" in ddl

    def test_should_be_reusable_across_tables(self) -> None:
        # A shared Column instance could only attach to one table; the mixin
        # must give each table its own.
        class _Other(TimestampMixin, _Base):
            __tablename__ = "others"

            id: Mapped[int] = mapped_column(primary_key=True)

        assert _table_of(_Other).c.created_at is not _table_of(_Widget).c.created_at
