from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vehicle_rental_core.infrastructure.db.base import Base
from vehicle_rental_core.infrastructure.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from vehicle_rental_core.infrastructure.models.customer import CustomerModel
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
        # At most one open rental per vehicle, enforced against concurrency.
        Index(
            "uq_rentals_one_active_per_vehicle",
            "vehicle_id",
            unique=True,
            postgresql_where=text("end_at IS NULL"),
        ),
        # Vehicle rental history and FK-related lookups, newest first.
        Index("ix_rentals_vehicle_start_at", "vehicle_id", text("start_at DESC")),
        # Customer rental history, and the lookup the FK's SET NULL performs.
        Index("ix_rentals_customer_id", "customer_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # CASCADE: a rental is meaningless without its vehicle.
    vehicle_id: Mapped[UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )

    # SET NULL, unlike vehicle_id above: a rental without its customer is
    # still valid history.
    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )

    # Snapshot taken at start: survives customer deletion and does not follow
    # a rename, because the rental records who rented, as they were.
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    vehicle: Mapped[VehicleModel] = relationship(back_populates="rentals")
    customer: Mapped[CustomerModel | None] = relationship(back_populates="rentals")
