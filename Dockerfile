# syntax=docker/dockerfile:1

# ---------------------------------------------------------------- builder
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies before the source so a code edit does not invalidate
# the dependency layer. --frozen makes the build fail if uv.lock is stale.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-install-project --no-dev

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ ./src/

# --no-editable bakes the package into site-packages; the default editable
# install would leave the venv pointing at /app/src, which the runtime stage
# does not carry.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------------------------------------------------------------- runtime
FROM python:3.14-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations/ ./migrations/

USER app

EXPOSE 8000

# Reuses the CLI's own probe so the container and the orchestrator agree on
# what "healthy" means.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["vrc", "healthcheck"]

CMD ["uvicorn", "vehicle_rental_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
