from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from vehicle_rental_core.api.dependencies import get_customer_service
from vehicle_rental_core.application.customer_service import CustomerService
from vehicle_rental_core.domain.customer import Customer
from vehicle_rental_core.domain.enums import Sex
from vehicle_rental_core.domain.errors import (
    CustomerNotFoundError,
    EmailAlreadyExistsError,
)

NOW = datetime(2026, 6, 1, tzinfo=UTC)
BORN = date(1990, 6, 1)
PAYLOAD = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "date_of_birth": "1990-06-01",
}


@pytest.fixture
def customer_service() -> AsyncMock:
    return AsyncMock(spec=CustomerService)


@pytest.fixture
def client(app: FastAPI, customer_service: AsyncMock) -> AsyncClient:
    app.dependency_overrides[get_customer_service] = lambda: customer_service
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _customer(**overrides: object) -> Customer:
    defaults: dict[str, object] = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "date_of_birth": BORN,
        "created_at": NOW,
        "updated_at": NOW,
    }
    return Customer(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestCreateCustomer:
    async def test_should_return_201_with_the_created_customer(
        self, client: AsyncClient, customer_service: AsyncMock
    ) -> None:
        customer_service.create.return_value = _customer()

        response = await client.post("/customers", json=PAYLOAD)

        assert response.status_code == 201
        assert response.json()["email"] == "ada@example.com"

    async def test_should_serve_the_derived_age(
        self, client: AsyncClient, customer_service: AsyncMock
    ) -> None:
        customer = _customer()
        customer_service.create.return_value = customer

        response = await client.post("/customers", json=PAYLOAD)

        # Computed from date_of_birth, not stored, so it tracks the entity.
        assert response.json()["age"] == customer.age

    async def test_should_return_409_for_a_duplicate_email(
        self, client: AsyncClient, customer_service: AsyncMock
    ) -> None:
        customer_service.create.side_effect = EmailAlreadyExistsError("taken")

        response = await client.post("/customers", json=PAYLOAD)

        assert response.status_code == 409
        assert response.json()["error"] == "EmailAlreadyExistsError"

    async def test_should_return_422_for_a_malformed_email(
        self, client: AsyncClient
    ) -> None:
        response = await client.post("/customers", json={**PAYLOAD, "email": "nope"})

        assert response.status_code == 422

    async def test_should_default_sex_to_unspecified(
        self, client: AsyncClient, customer_service: AsyncMock
    ) -> None:
        customer_service.create.return_value = _customer()

        await client.post("/customers", json=PAYLOAD)

        assert customer_service.create.await_args.kwargs["sex"] is Sex.UNSPECIFIED


class TestListCustomers:
    async def test_should_return_the_page(
        self, client: AsyncClient, customer_service: AsyncMock
    ) -> None:
        customer_service.list.return_value = [_customer()]

        response = await client.get("/customers")

        assert response.status_code == 200
        assert len(response.json()) == 1

    async def test_should_reject_an_out_of_range_limit(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/customers", params={"limit": 500})

        assert response.status_code == 422


class TestGetCustomer:
    async def test_should_return_404_for_an_unknown_customer(
        self, client: AsyncClient, customer_service: AsyncMock
    ) -> None:
        customer_service.get.side_effect = CustomerNotFoundError("nope")

        response = await client.get(f"/customers/{uuid4()}")

        assert response.status_code == 404
        assert response.json()["error"] == "CustomerNotFoundError"


class TestUpdateCustomer:
    async def test_should_forward_only_the_fields_sent(
        self, client: AsyncClient, customer_service: AsyncMock
    ) -> None:
        customer_service.update.return_value = _customer(name="Grace Hopper")

        response = await client.patch(
            f"/customers/{uuid4()}", json={"name": "Grace Hopper"}
        )

        assert response.status_code == 200
        # exclude_unset is what keeps an omitted field omitted rather than None.
        changes = customer_service.update.await_args.args[1]
        assert changes.attributes() == {"name": "Grace Hopper"}

    async def test_should_return_409_when_the_new_email_is_taken(
        self, client: AsyncClient, customer_service: AsyncMock
    ) -> None:
        customer_service.update.side_effect = EmailAlreadyExistsError("taken")

        response = await client.patch(
            f"/customers/{uuid4()}", json={"email": "grace@example.com"}
        )

        assert response.status_code == 409


class TestDeleteCustomer:
    async def test_should_return_204(
        self, client: AsyncClient, customer_service: AsyncMock
    ) -> None:
        response = await client.delete(f"/customers/{uuid4()}")

        assert response.status_code == 204

    async def test_should_return_404_for_an_unknown_customer(
        self, client: AsyncClient, customer_service: AsyncMock
    ) -> None:
        customer_service.delete.side_effect = CustomerNotFoundError("nope")

        response = await client.delete(f"/customers/{uuid4()}")

        assert response.status_code == 404
