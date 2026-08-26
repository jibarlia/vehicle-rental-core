import asyncio

import typer
import uvicorn
from sqlalchemy import text

from vehicle_rental_core.cli import db as db_commands
from vehicle_rental_core.cli import rental as rental_commands
from vehicle_rental_core.cli import seed as seed_commands
from vehicle_rental_core.cli import vehicle as vehicle_commands
from vehicle_rental_core.core.config import Settings, get_settings
from vehicle_rental_core.core.observability.logging import configure_logging
from vehicle_rental_core.infrastructure.db import create_engine

app = typer.Typer(
    help="vehicle-rental-core developer console.",
    no_args_is_help=True,
)
app.add_typer(db_commands.app, name="db")
app.add_typer(vehicle_commands.app, name="vehicle")
app.add_typer(rental_commands.app, name="rental")
app.command(name="seed")(seed_commands.seed)


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Override API_HOST."),
    port: int | None = typer.Option(None, help="Override API_PORT."),
    reload: bool = typer.Option(False, "--reload", help="Autoreload on file change."),
) -> None:
    """Run the API with uvicorn."""
    settings = get_settings()
    uvicorn.run(
        "vehicle_rental_core.main:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=reload,
        log_level=settings.log_level.lower(),
    )


async def _ping_database(settings: Settings) -> None:
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


@app.command()
def healthcheck() -> None:
    """Verify the configured database is reachable.

    Typer commands stay synchronous and cross into async with a single
    ``asyncio.run`` at the boundary, so there is exactly one event loop per
    command invocation.
    """
    settings = get_settings()
    configure_logging(settings)
    try:
        asyncio.run(_ping_database(settings))
    except Exception as exc:
        typer.secho(f"database unreachable: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho("database reachable", fg=typer.colors.GREEN)


@app.command()
def config() -> None:
    """Print the resolved settings, with database credentials redacted."""
    settings = get_settings()
    for field, value in settings.model_dump().items():
        if field == "database_url":
            value = _redact(str(value))
        typer.echo(f"{field}={value}")


def _redact(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    credentials, host = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


if __name__ == "__main__":
    app()
