"""HTTP plumbing for the CLI commands that drive the API over the wire."""

from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
import typer
from rich.console import Console
from rich.table import Table

from vehicle_rental_core.core.config import get_settings

_console = Console()

# Long enough for a cold start, short enough not to hang the terminal.
_TIMEOUT = 10.0


def base_url(override: str | None = None) -> str:
    """Where to reach the API.

    ``--base-url`` wins, then ``API_BASE_URL``. Never api_host: that is the
    bind address, which is not dialable.
    """
    return (override or get_settings().api_base_url).rstrip("/")


def request(
    method: str,
    path: str,
    *,
    override: str | None = None,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """Call the API, turning any failure into a readable message and exit 1."""
    url = f"{base_url(override)}{path}"
    try:
        response = httpx.request(
            method, url, json=json, params=params, timeout=_TIMEOUT
        )
    except httpx.ConnectError as exc:
        _fail(f"API unreachable at {base_url(override)} — is 'vrc serve' running?")
        raise typer.Exit(code=1) from exc
    except httpx.TimeoutException as exc:
        _fail(f"API did not answer within {_TIMEOUT:.0f}s at {url}")
        raise typer.Exit(code=1) from exc

    if response.is_success:
        # 204 carries no body; every other success in this API returns JSON.
        return None if response.status_code == 204 else response.json()

    _fail(_describe(response))
    raise typer.Exit(code=1)


def _describe(response: httpx.Response) -> str:
    """Render a failed response, falling back when it is not our envelope."""
    try:
        payload = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text.strip() or 'no body'}"

    if isinstance(payload, dict) and "detail" in payload:
        detail = payload["detail"]
        name = payload.get("error")
        # FastAPI's own request validation nests its detail as a list.
        if isinstance(detail, list):
            detail = "; ".join(
                f"{'.'.join(str(p) for p in item.get('loc', []))}: {item.get('msg')}"
                for item in detail
            )
        return f"{name}: {detail}" if name else str(detail)

    return f"HTTP {response.status_code}: {payload}"


def _fail(message: str) -> None:
    _console.print(f"[red]{message}[/red]")


def render(payload: Any, *, as_json: bool, columns: list[str] | None = None) -> None:
    """Print a result as a table, or as raw JSON when asked."""
    if as_json:
        _console.print_json(data=payload)
        return

    if payload is None:
        _console.print("[green]done[/green]")
    elif isinstance(payload, list):
        _table(payload, columns)
    else:
        _detail(payload)


def _table(rows: list[dict[str, Any]], columns: list[str] | None) -> None:
    if not rows:
        _console.print("[dim]no results[/dim]")
        return

    names = columns or list(rows[0])
    table = Table(show_header=True, header_style="bold")
    for name in names:
        table.add_column(name)
    for row in rows:
        table.add_row(*(_cell(row.get(name)) for name in names))
    _console.print(table)


def _detail(row: dict[str, Any]) -> None:
    table = Table(show_header=False, box=None)
    for name, value in row.items():
        table.add_row(f"[bold]{name}[/bold]", _cell(value))
    _console.print(table)


def _cell(value: Any) -> str:
    if value is None:
        return "[dim]—[/dim]"
    return str(value)


def as_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def as_str(value: UUID | None) -> str | None:
    return str(value) if value is not None else None
