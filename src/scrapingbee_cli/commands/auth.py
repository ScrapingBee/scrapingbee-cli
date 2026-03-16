"""Auth, docs, and logout commands."""

from __future__ import annotations

import asyncio
import getpass

import click

from ..client import Client
from ..config import (
    BASE_URL,
    auth_config_path,
    get_api_key_if_set,
    remove_api_key_from_dotenv,
    save_api_key_to_dotenv,
)

DOCS_URL = "https://www.scrapingbee.com/documentation/"


def _validate_api_key(key: str) -> bool:
    """Validate API key by calling the usage endpoint. Returns True if valid."""

    async def _check() -> int:
        async with Client(key, BASE_URL) as client:
            _, _, status_code = await client.usage(retries=1, backoff=1.0)
            return status_code

    try:
        status = asyncio.run(_check())
        return status == 200
    except Exception:
        return False


@click.command()
@click.option(
    "--api-key",
    "auth_api_key",
    default=None,
    help="API key to save (non-interactive); otherwise uses env/.env or prompt.",
)
@click.option(
    "--show",
    "show_path_only",
    is_flag=True,
    default=False,
    help="Only show the path where the API key is or would be stored; do not save.",
)
@click.pass_obj
def auth_cmd(obj: dict, auth_api_key: str | None, show_path_only: bool) -> None:
    """Save API key to ~/.config/scrapingbee-cli/.env (from --api-key, env/.env, or prompt)."""
    path = auth_config_path()
    if show_path_only:
        click.echo(str(path))
        return
    key = auth_api_key or get_api_key_if_set(None)
    if not key:
        try:
            raw = getpass.getpass("ScrapingBee API key: ")
        except (EOFError, KeyboardInterrupt):
            click.echo(
                "Cannot read API key (non-interactive). Use --api-key KEY or set SCRAPINGBEE_API_KEY.",
                err=True,
            )
            raise SystemExit(1)
        key = raw.strip()
        if not key:
            click.echo("No API key entered.", err=True)
            raise SystemExit(1)
    click.echo("Validating API key...", err=True)
    if not _validate_api_key(key):
        click.echo("Invalid API key. Please check your key and try again.", err=True)
        raise SystemExit(1)
    path = save_api_key_to_dotenv(key)
    click.echo(f"API key saved to {path}. You can now run scrapingbee commands.")


@click.command()
@click.option(
    "--open/--no-open",
    "open_browser",
    default=False,
    help="Open the documentation URL in the default browser.",
)
def docs_cmd(open_browser: bool) -> None:
    """Print or open the ScrapingBee API documentation URL."""
    click.echo(DOCS_URL)
    if open_browser:
        import webbrowser

        webbrowser.open(DOCS_URL)


@click.command()
@click.pass_obj
def logout_cmd(obj: dict) -> None:
    """Remove stored API key from ~/.config/scrapingbee-cli/.env."""
    import json
    from pathlib import Path

    # Check for active schedules
    registry_path = Path.home() / ".config" / "scrapingbee-cli" / "schedules.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        registry = {}

    if registry:
        names = ", ".join(registry)
        click.echo(
            f"Warning: you have {len(registry)} active schedule(s): {names}.\n"
            "These will fail without an API key.",
            err=True,
        )
        if not click.confirm("Stop all schedules and logout?"):
            click.echo("Logout cancelled.", err=True)
            return
        # Stop all schedules
        from .schedule import _remove_cron_entry, _save_registry

        for name in list(registry):
            _remove_cron_entry(name)
            click.echo(f"  Stopped schedule '{name}'.", err=True)
        _save_registry({})

    removed = remove_api_key_from_dotenv()
    if removed:
        click.echo(f"API key removed from {auth_config_path()}.")
    else:
        click.echo(f"No stored API key found in {auth_config_path()}.")
    click.echo(
        "If you set SCRAPINGBEE_API_KEY in your shell, unset it with: unset SCRAPINGBEE_API_KEY"
    )


def register(cli: click.Group) -> None:
    cli.add_command(auth_cmd, "auth")
    cli.add_command(docs_cmd, "docs")
    cli.add_command(logout_cmd, "logout")
