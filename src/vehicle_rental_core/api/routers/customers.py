from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from vehicle_rental_core.api.dependencies import CustomerServiceDep
from vehicle_rental_core.application.commands import CustomerChanges
from vehicle_rental_core.schemas.customer import (
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
)

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate, customer_service: CustomerServiceDep
) -> CustomerRead:
    customer = await customer_service.create(
        name=payload.name,
        email=payload.email,
        date_of_birth=payload.date_of_birth,
        sex=payload.sex,
    )
    return CustomerRead.model_validate(customer)


@router.get("", response_model=list[CustomerRead])
async def list_customers(
    customer_service: CustomerServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[CustomerRead]:
    customers = await customer_service.list(offset=offset, limit=limit)
    return [CustomerRead.model_validate(customer) for customer in customers]


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: UUID, customer_service: CustomerServiceDep
) -> CustomerRead:
    return CustomerRead.model_validate(await customer_service.get(customer_id))


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: UUID, payload: CustomerUpdate, customer_service: CustomerServiceDep
) -> CustomerRead:
    # Built from what the client actually sent, so an omitted field stays
    # omitted all the way down instead of arriving as an indistinguishable None.
    changes = CustomerChanges(**payload.model_dump(exclude_unset=True))
    customer = await customer_service.update(customer_id, changes)
    return CustomerRead.model_validate(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: UUID, customer_service: CustomerServiceDep
) -> Response:
    """Delete a customer, keeping their rentals on record.

    Unlike a vehicle, a customer is genuinely deleted. Their rentals survive:
    the FK is ``ON DELETE SET NULL`` and ``customer_name`` was snapshotted when
    each rental started, so the history stays readable without them.
    """
    await customer_service.delete(customer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
