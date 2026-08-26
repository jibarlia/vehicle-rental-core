from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from vehicle_rental_core.application.customer_service import CustomerService
from vehicle_rental_core.application.rental_service import RentalService
from vehicle_rental_core.application.vehicle_service import VehicleService
from vehicle_rental_core.core.config import Settings
from vehicle_rental_core.infrastructure.repositories.customer_repository import (
    CustomerRepository,
)
from vehicle_rental_core.infrastructure.repositories.rental_repository import (
    RentalRepository,
)
from vehicle_rental_core.infrastructure.repositories.vehicle_repository import (
    VehicleRepository,
)


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


async def get_session(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[AsyncSession]:
    """One session per request, rolled back if the handler raises.

    Reading the factory off ``app.state`` (rather than a module global) is what
    lets tests swap in a throwaway engine with a plain dependency override.
    """
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_vehicle_repository(session: SessionDep) -> VehicleRepository:
    return VehicleRepository(session)


def get_rental_repository(session: SessionDep) -> RentalRepository:
    return RentalRepository(session)


def get_customer_repository(session: SessionDep) -> CustomerRepository:
    return CustomerRepository(session)


VehicleRepositoryDep = Annotated[VehicleRepository, Depends(get_vehicle_repository)]
RentalRepositoryDep = Annotated[RentalRepository, Depends(get_rental_repository)]
CustomerRepositoryDep = Annotated[CustomerRepository, Depends(get_customer_repository)]


def get_vehicle_service(
    session: SessionDep,
    vehicle_repository: VehicleRepositoryDep,
    rental_repository: RentalRepositoryDep,
) -> VehicleService:
    return VehicleService(session, vehicle_repository, rental_repository)


def get_rental_service(
    session: SessionDep,
    rental_repository: RentalRepositoryDep,
    vehicle_repository: VehicleRepositoryDep,
    customer_repository: CustomerRepositoryDep,
) -> RentalService:
    return RentalService(
        session, rental_repository, vehicle_repository, customer_repository
    )


def get_customer_service(
    session: SessionDep,
    customer_repository: CustomerRepositoryDep,
) -> CustomerService:
    return CustomerService(session, customer_repository)


VehicleServiceDep = Annotated[VehicleService, Depends(get_vehicle_service)]
RentalServiceDep = Annotated[RentalService, Depends(get_rental_service)]
CustomerServiceDep = Annotated[CustomerService, Depends(get_customer_service)]
