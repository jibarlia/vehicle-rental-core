from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Date, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vehicle_rental_core.domain.enums import Sex
from vehicle_rental_core.infrastructure.db.base import Base
from vehicle_rental_core.infrastructure.db.constraints import enum_check
from vehicle_rental_core.infrastructure.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from vehicle_rental_core.infrastructure.models.rental import RentalModel


class CustomerModel(TimestampMixin, Base):
    """``customers`` table.

    Deleting a customer is a real DELETE, unlike retiring a vehicle: the FK on
    ``rentals`` is ``ON DELETE SET NULL``, so the rentals survive with their
    ``customer_name`` snapshot intact. The record goes, the history stays.
    """

    __tablename__ = "customers"

    __table_args__ = (enum_check("sex", Sex),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # 320 is the maximum length an address can have (64 local + @ + 255 domain).
    # Unique because an email is what identifies a customer to a human.
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )

    # Stored instead of an age, which would be wrong the day after it was
    # written. ``Customer.age`` derives the number on read.
    date_of_birth: Mapped[date] = mapped_column(Date(), nullable=False)

    # VARCHAR with create_constraint=False, matching VehicleModel: the CHECK is
    # declared in __table_args__ so Alembic can see it.
    sex: Mapped[Sex] = mapped_column(
        Enum(
            Sex,
            name="sex",
            native_enum=False,
            create_constraint=False,
            values_callable=lambda enum: [member.value for member in enum],
            length=32,
        ),
        nullable=False,
        default=Sex.UNSPECIFIED,
    )

    # passive_deletes lets the database apply the ON DELETE SET NULL. Without
    # it SQLAlchemy loads every rental and nulls the FK itself, which both
    # diverges from the DDL and gets expensive for a long-standing customer.
    rentals: Mapped[list[RentalModel]] = relationship(
        back_populates="customer", passive_deletes=True
    )
