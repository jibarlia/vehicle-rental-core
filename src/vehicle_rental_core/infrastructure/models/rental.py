from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vehicle_rental_core.infrastructure.db.base import Base
from vehicle_rental_core.infrastructure.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from vehicle_rental_core.infrastructure.models.vehicle import VehicleModel


class RentalModel(TimestampMixin, Base):
    """``rentals`` table. An active rental is one with ``end_at IS NULL``."""

    __tablename__ = "rentals"

    __table_args__ = (
        # end_at may be open, but never before the rental started.
        CheckConstraint(
            "end_at IS NULL OR end_at >= start_at",
            name="end_at_after_start_at",
        ),
        # At most one open rental per vehicle. Enforced by the database, so two
        # concurrent transactions cannot both win the race.
        Index(
            "uq_rentals_one_active_per_vehicle",
            "vehicle_id",
            unique=True,
            postgresql_where=text("end_at IS NULL"),
        ),
        # Vehicle rental history and FK-related lookups, newest first.
        Index("ix_rentals_vehicle_start_at", "vehicle_id", text("start_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # CASCADE: a rental is meaningless without the vehicle it refers to, so
    # hard-deleting a vehicle takes its rentals with it. Retiring a vehicle
    # while keeping the record is retiring, not deleting.
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )

    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    vehicle: Mapped[VehicleModel] = relationship(back_populates="rentals")
