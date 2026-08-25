from pathlib import Path

import typer
from alembic import command
from alembic.config import Config

from vehicle_rental_core.core.config import get_settings

app = typer.Typer(help="Alembic migration commands.")

# Source checkout: <repo>/src/vehicle_rental_core/cli/db.py -> <repo>.
_CHECKOUT_ROOT = Path(__file__).resolve().parents[3]


def _project_root() -> Path:
    """Locate the directory holding alembic.ini and migrations/.

    Prefers the current working directory so an installed package (Docker,
    where the code lives in site-packages) still finds the migrations copied
    alongside it, and falls back to the source checkout layout.
    """
    cwd = Path.cwd()
    if (cwd / "alembic.ini").is_file():
        return cwd
    return _CHECKOUT_ROOT


def _alembic_config() -> Config:
    """Alembic config with the URL taken from settings, not alembic.ini.

    Keeps one source of truth for the database URL so the CLI, the API and the
    migrations can never drift onto different databases.
    """
    root = _project_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


@app.command()
def upgrade(revision: str = typer.Argument("head")) -> None:
    """Apply migrations up to REVISION."""
    command.upgrade(_alembic_config(), revision)


@app.command()
def downgrade(revision: str = typer.Argument("-1")) -> None:
    """Revert migrations down to REVISION."""
    command.downgrade(_alembic_config(), revision)


@app.command()
def revision(
    message: str = typer.Option(..., "--message", "-m", help="Migration summary."),
    autogenerate: bool = typer.Option(True, help="Diff models against the database."),
) -> None:
    """Create a new migration script."""
    command.revision(_alembic_config(), message=message, autogenerate=autogenerate)


@app.command()
def current() -> None:
    """Show the revision the database is currently stamped at."""
    command.current(_alembic_config(), verbose=True)


@app.command()
def history() -> None:
    """Show the full migration history."""
    command.history(_alembic_config(), verbose=True)
