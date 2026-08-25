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

    Deliberately named ``vehicles``, not ``cars``: ``vehicle_type`` carries the
    distinction, so motorcycles, vans and trucks join without a rename.

    Both enum columns are VARCHAR with ``create_constraint=False``; their CHECK
    constraints are declared in ``__table_args__`` so Alembic can see them.
    ``values_callable`` stores the lowercase enum values ("car"), not the member
    names ("CAR").
    """

    __tablename__ = "vehicles"

    __table_args__ = (
        # Required status-filter operation.
        Index("ix_vehicles_status", "status"),
        enum_check("vehicle_type", VehicleType),
        enum_check("status", VehicleStatus),
        # A vehicle is retired exactly when it carries a retirement timestamp.
        # Without this the two could drift and every query would have to guess
        # which one is authoritative.
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

    # Unique across the whole table, retired rows included: a retired vehicle
    # keeps its plate forever, so the record of who drove which plate stays
    # unambiguous. Only a hard DELETE frees a registration number for reuse.
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

    # Retirement is a status, not a tombstone: the row and its rentals stay.
    # This records when the vehicle left the fleet.
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    rentals: Mapped[list[RentalModel]] = relationship(
        back_populates="vehicle", cascade="all, delete"
    )

    # SQLAlchemy bumps and checks this column on every UPDATE; a mismatch means
    # another transaction won and raises StaleDataError.
    __mapper_args__ = {"version_id_col": version}
