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

    Deleting one is a real DELETE, unlike retiring a vehicle: the FK on
    ``rentals`` is ``ON DELETE SET NULL``, so the history stays.
    """

    __tablename__ = "customers"

    __table_args__ = (enum_check("sex", Sex),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # 320 = 64 local + @ + 255 domain, the maximum an address can have.
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )

    # Stored instead of an age, which would go stale; Customer.age derives it.
    date_of_birth: Mapped[date] = mapped_column(Date(), nullable=False)

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

    # passive_deletes lets the database apply ON DELETE SET NULL instead of
    # SQLAlchemy loading every rental to null the FK itself.
    rentals: Mapped[list[RentalModel]] = relationship(
        back_populates="customer", passive_deletes=True
    )
