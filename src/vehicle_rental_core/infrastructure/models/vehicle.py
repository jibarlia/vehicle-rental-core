from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vehicle_rental_core.domain.enums import VehicleStatus, VehicleType
from vehicle_rental_core.infrastructure.db.base import Base
from vehicle_rental_core.infrastructure.db.constraints import enum_check
from vehicle_rental_core.infrastructure.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from vehicle_rental_core.infrastructure.models.rental import RentalModel


class VehicleModel(TimestampMixin, Base):
    """``vehicles`` table.

    Enum columns are VARCHAR with ``create_constraint=False`` so their CHECKs
    can be declared in ``__table_args__`` where Alembic sees them.
    """

    __tablename__ = "vehicles"

    __table_args__ = (
        # Required status-filter operation.
        Index("ix_vehicles_status", "status"),
        enum_check("vehicle_type", VehicleType),
        enum_check("status", VehicleStatus),
        # Keeps status and retired_at from ever drifting apart.
        CheckConstraint(
            "(status = 'retired') = (retired_at IS NOT NULL)",
            name="retired_status_matches_timestamp",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    vehicle_type: Mapped[VehicleType] = mapped_column(
        Enum(
            VehicleType,
            name="vehicle_type",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum: [member.value for member in enum],
            length=32,
        ),
        nullable=False,
        default=VehicleType.CAR,
    )

    # Unique across retired rows too, so a plate is never ambiguous.
    registration_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[VehicleStatus] = mapped_column(
        Enum(
            VehicleStatus,
            name="vehicle_status",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum: [member.value for member in enum],
            length=32,
        ),
        nullable=False,
        default=VehicleStatus.AVAILABLE,
    )

    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # passive_deletes lets the database apply the ON DELETE CASCADE instead of
    # SQLAlchemy loading every rental to delete it one at a time.
    rentals: Mapped[list[RentalModel]] = relationship(
        back_populates="vehicle", cascade="all, delete", passive_deletes=True
    )

    # SQLAlchemy bumps and checks this on every UPDATE; a mismatch raises
    # StaleDataError.
    __mapper_args__ = {"version_id_col": version}
