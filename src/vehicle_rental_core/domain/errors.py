"""Domain errors.

These describe rule violations in business terms and know nothing about HTTP.
The API layer is responsible for translating them into status codes.
"""


class DomainError(Exception):
    """Base class for every business-rule violation."""


class NotFoundError(DomainError):
    """An entity was addressed by an identifier that does not exist."""


class VehicleNotFoundError(NotFoundError):
    pass


class RentalNotFoundError(NotFoundError):
    pass


class CustomerNotFoundError(NotFoundError):
    pass


class ConflictError(DomainError):
    """The request contradicts the current state of the system."""


class RegistrationNumberAlreadyExistsError(ConflictError):
    pass


class EmailAlreadyExistsError(ConflictError):
    """Two customers cannot share an email — it is their natural key."""


class VehicleHasActiveRentalError(ConflictError):
    """Blocks retiring and maintenance while a vehicle is rented out."""


class VehicleRetiredError(ConflictError):
    """Retiring is terminal — a retired vehicle can no longer be changed."""


class VehicleNotRentableError(ConflictError):
    """The vehicle exists but is not in a state that allows renting."""


class RentalAlreadyEndedError(ConflictError):
    pass


class ConcurrentUpdateError(ConflictError):
    """Optimistic lock lost — the row changed under us."""


class ValidationError(DomainError):
    """The request is internally inconsistent, independent of stored state."""


class InvalidRentalPeriodError(ValidationError):
    pass


class InvalidVehicleYearError(ValidationError):
    """The model year is outside the range a real vehicle could carry."""


class InvalidDateOfBirthError(ValidationError):
    """The birth date is in the future or implies an implausible age."""
