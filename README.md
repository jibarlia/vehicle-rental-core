# Vehicle Rental Core

A production-minded FastAPI service for managing vehicles, customers, and rentals.

## Quick start

Run the complete application with Docker:

```bash
docker compose up --build
```

Docker Compose starts PostgreSQL, applies the Alembic migrations, and starts the API
only after its dependencies are ready.

- API documentation: <http://localhost:8000/docs>
- Liveness check: <http://localhost:8000/health>
- Readiness check: <http://localhost:8000/health/ready>
- Prometheus metrics: <http://localhost:8000/metrics>

Stop the application with:

```bash
docker compose down
```

## Local development

Requirements: Python 3.14, [uv](https://docs.astral.sh/uv/), and PostgreSQL 14+ —
either the Docker container from `docker-compose.yml` or an installation on your
machine.

### 1. Install the project

```bash
uv sync --all-groups
cp .env.example .env
uv run pre-commit install
```

`uv sync` creates the virtual environment and installs the exact dependency versions
recorded in `uv.lock`.

### 2. Provide a database

`vrc db upgrade` creates the *tables*, not the database itself, so an empty
`vehicle_rental` database has to exist before it runs. Pick one of the two options
below.

**Option A — PostgreSQL in Docker**

```bash
docker compose up -d postgres
```

The container creates the `vehicle_rental` database and the `postgres` role on first
start and publishes them on host port **55432**, which is what `.env.example` already
points at. Nothing else to configure.

**Option B — a PostgreSQL installed on your machine**

Create the database once:

```bash
createdb vehicle_rental
```

Then point `DATABASE_URL` in `.env` at your server. A local installation listens on the
default port **5432**, and its credentials are your own rather than the container's
`postgres:postgres`:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/vehicle_rental
```

If the installation has no `postgres` role, either connect as your OS user
(`postgresql+psycopg://$(whoami)@localhost:5432/vehicle_rental`) or create the role once
so the URL matches the container's:

```bash
psql -d postgres -c "CREATE ROLE postgres LOGIN SUPERUSER PASSWORD 'postgres';"
```

### 3. Migrate and run

Identical for both options:

```bash
uv run vrc db upgrade      # apply the Alembic migrations
uv run vrc healthcheck     # confirm the API can reach the database
uv run vrc serve --reload  # run the application
```

VS Code equivalents live in [`.vscode/launch.json`](.vscode/launch.json): **DB: upgrade**
applies the migrations, **Healthcheck** verifies the connection, and **API (reload)** or
**API + Swagger** starts the server. They all load `.env`, so they follow whichever
option you configured above.

## Using the application

### REST API

The interactive Swagger UI at <http://localhost:8000/docs> is the easiest way to
explore and call the API.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/vehicles` | Add a vehicle to the fleet |
| `GET` | `/vehicles` | List vehicles, optionally filtered by `status` |
| `GET` | `/vehicles/status` | Fleet status: counts across every vehicle, plus a page of them |
| `GET` | `/vehicles/{vehicle_id}` | Get a vehicle |
| `PATCH` | `/vehicles/{vehicle_id}` | Update its details or status |
| `POST` | `/vehicles/{vehicle_id}/retire` | Permanently retire it from service |
| `GET` | `/vehicles/{vehicle_id}/rentals` | List its rental history |
| `POST` | `/customers` | Register a customer |
| `GET` | `/customers` | List customers |
| `GET` | `/customers/{customer_id}` | Get a customer |
| `PATCH` | `/customers/{customer_id}` | Update a customer |
| `DELETE` | `/customers/{customer_id}` | Delete a customer while preserving rental history |
| `POST` | `/rentals` | Start a rental |
| `GET` | `/rentals/{rental_id}` | Get a rental |
| `POST` | `/rentals/{rental_id}/complete` | Complete a rental and release the vehicle |

Domain failures are translated consistently at the API boundary: missing resources
return `404`, state conflicts return `409`, and invalid input returns `422`.

#### Fleet status

`GET /vehicles/status` answers "how is the fleet doing right now?" in one call:

```jsonc
{
  "counts": { "available": 8, "in_use": 3, "maintenance": 1, "retired": 0 },
  "total": 12,
  "items": [
    {
      "id": "…", "registration_number": "AB-123-CD",
      "model": "Corolla", "year": 2021, "status": "in_use",
      "current_rental": {
        "id": "…", "customer_id": "…",
        "customer_name": "Dana Levi", "start_at": "2026-08-24T09:12:00Z"
      }
    }
  ]
}
```

Two things are worth knowing about the shape:

- **`counts` and `total` describe the whole fleet.** They are unaffected by
  `status`, `offset` and `limit`, which page `items` alone, and every status is
  present even at zero — so a dashboard can render a fixed set of tiles without
  walking the table. Retired vehicles are counted under their own status even
  though `items` hides them, because a tally that omitted them would not add up.
- **`items` is always one page**, `limit` capped at 100. Grouping is done by
  filtering: `?status=in_use` is the group, paginated on its own.

A vehicle that is out carries the rental explaining it, which saves a caller from
asking each vehicle in turn. Rows are a deliberate subset of `GET /vehicles` — the
fields a board displays and no more; the full record is a `GET /vehicles/{id}` away.

### CLI

`vrc` provides operational commands and an HTTP client for the API:

```bash
uv run vrc vehicle add -r IL-12345 -m Corolla -y 2024
uv run vrc vehicle list
uv run vrc vehicle list --status available

uv run vrc rental start --vehicle-id VEHICLE_UUID --customer-id CUSTOMER_UUID
uv run vrc rental end RENTAL_UUID
```

Useful development and database commands:

```bash
uv run vrc seed --vehicles 20 --customers 10 --rentals 15
uv run vrc healthcheck
uv run vrc config

uv run vrc db upgrade
uv run vrc db current
uv run vrc db history
uv run vrc db downgrade -1
```

Vehicle and rental commands call the REST API. Seeding runs directly through the
application services so it can generate data without a running API while still
respecting the same business rules.

## Configuration

Configuration is validated in one place with Pydantic Settings. Environment variables
take precedence over `.env`; the common local values and defaults are documented in
[`.env.example`](.env.example).

The API, CLI, and migrations all use the same `DATABASE_URL`. It must select an async
driver — psycopg 3:

```env
# Docker Compose publishes PostgreSQL on host port 55432
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:55432/vehicle_rental

# A PostgreSQL installed on your machine listens on 5432
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/vehicle_rental
```

The port is the only difference between the two, and it is the usual cause of a
`connection refused` on a fresh checkout.

Run `uv run vrc config` to inspect the resolved configuration. Credentials are
redacted from its output.

## Architecture

The current implementation is a layered modular service. HTTP requests remain
request-response operations; asynchronous Python and database I/O improve concurrency
without making the business workflow event-driven.

```mermaid
flowchart TB
    User["Internal user or operator"]

    subgraph Interfaces["Interfaces"]
        API["FastAPI REST API"]
        CLI["Typer CLI"]
    end

    subgraph Application["Application layer"]
        Services["Vehicle, customer, and rental use cases"]
    end

    subgraph Domain["Domain layer"]
        Rules["Entities, validation, and state transitions"]
    end

    subgraph Infrastructure["Infrastructure layer"]
        Repositories["Async SQLAlchemy repositories"]
        Migrations["Alembic migrations"]
        Observability["Logging, metrics, and health checks"]
    end

    Database[("PostgreSQL")]

    User --> API
    User --> CLI
    CLI -->|"vehicle and rental commands"| API
    API --> Services
    CLI -->|"seed command"| Services
    Services --> Rules
    Services --> Repositories
    Repositories --> Database
    CLI -->|"database commands"| Migrations
    Migrations --> Database
    API -.-> Observability
    CLI -.-> Observability
```

- **API:** validates the HTTP contract and maps domain errors to responses.
- **Application:** coordinates use cases and owns transaction boundaries.
- **Domain:** contains entities and business rules without FastAPI, SQLAlchemy, or I/O.
- **Infrastructure:** persists domain entities and integrates with PostgreSQL.

```text
src/vehicle_rental_core/
├── api/              # FastAPI application, dependencies, and routers
├── application/      # Use-case services, commands, and clock abstraction
├── domain/           # Entities, enums, and business errors
├── infrastructure/   # Database models, repositories, and mappings
├── schemas/          # HTTP request and response models
├── cli/              # Typer commands
└── core/             # Configuration and observability
```

## Key business flows

| Flow | What happens | Consistency guarantee |
| --- | --- | --- |
| Start a rental | Verify the vehicle and customer, snapshot the customer name, open the rental, and mark the vehicle `in_use` | Rental and vehicle update commit in one transaction; a partial unique index permits only one active rental per vehicle |
| Complete a rental | Set its end time and return an `in_use` vehicle to `available` | Both changes commit in one transaction |
| Retire a vehicle | Reject active rentals, set `status=retired`, and record `retired_at` | Retirement is terminal and the row and rental history remain available |
| Delete a customer | Delete the customer record while retaining previous rentals | The customer foreign key becomes `NULL`; the snapshotted customer name preserves historical context |

## Design decisions

- **`vehicles`, not `cars`:** the current type is `car`, but the model can add
  motorcycles, vans, or trucks without renaming tables, foreign keys, and endpoints.
- **Consistent naming:** Python types are singular (`Vehicle`, `Rental`); database tables
  and API collections are plural (`vehicles`, `/rentals`).
- **Async I/O, synchronous workflow:** API routes and persistence are async, while each
  user operation still returns a definitive success or failure in the same request.
- **Retirement instead of deletion:** vehicles leave service without erasing their
  identity or rental history. No hard-delete endpoint is exposed.
- **History survives customer deletion:** rentals snapshot the customer's name when
  they start, so later profile changes or deletion do not rewrite the past.
- **Rules at two levels:** domain entities provide meaningful failures; PostgreSQL
  constraints remain authoritative under concurrent requests.
- **Concurrency protection:** registration numbers are unique, active rentals use a
  partial unique index, and vehicle updates use optimistic locking through `version`.
- **Purposeful indexes:** status filtering, active-rental lookup, and newest-first rental
  history match the service's actual query patterns.

## Tests and quality checks

Run the unit test suite with coverage:

```bash
uv run pytest
uv run pytest --cov-report=html
```

The unit suite is hermetic: it uses mocks and HTTPX's in-process ASGI transport and does
not require PostgreSQL or network access.

Run all static checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
```

## Observability

- Standard Python logging with a single process-wide console format.
- `GET /health` for liveness without touching external dependencies.
- `GET /health/ready` for PostgreSQL readiness.
- `GET /metrics` for Prometheus request counts and latency histograms.
- Route-template metric labels such as `/vehicles/{vehicle_id}` keep cardinality
  bounded.
- The container health check and CLI health check use the same database-readiness
  definition.

## Technology stack

| Concern | Choice |
| --- | --- |
| Runtime | Python 3.14 |
| API | FastAPI + Uvicorn |
| CLI | Typer |
| Validation and configuration | Pydantic + pydantic-settings |
| Persistence | PostgreSQL + async SQLAlchemy 2.x + psycopg 3 |
| Migrations | Alembic |
| Tests | pytest, pytest-asyncio, HTTPX, pytest-cov |
| Quality | Ruff, mypy strict, pre-commit |
| Metrics | Prometheus client |
| Packaging | uv, `pyproject.toml`, and a committed `uv.lock` |
| Runtime packaging | Docker + Docker Compose |

## Roadmap

1. Add integration tests against PostgreSQL for repositories, migrations, and database
   constraints.
2. Introduce a Unit of Work as the explicit transaction and repository boundary.
3. Add a transactional outbox and RabbitMQ audit consumer if asynchronous messaging is
   included in the final scope.
4. Add authentication and authorization.
5. Add configurable rotating file logging for standalone deployments.
6. Add reproducible performance benchmarks and load-test baselines.
