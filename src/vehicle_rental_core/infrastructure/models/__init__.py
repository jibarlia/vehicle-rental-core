"""ORM table definitions.

Importing every table module here populates ``Base.metadata`` and lets
SQLAlchemy resolve the string-based relationships between models, which Alembic
autogenerate depends on.
"""

from vehicle_rental_core.infrastructure.models.customer import CustomerModel
from vehicle_rental_core.infrastructure.models.rental import RentalModel
from vehicle_rental_core.infrastructure.models.vehicle import VehicleModel

__all__ = ["CustomerModel", "RentalModel", "VehicleModel"]
