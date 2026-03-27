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


_UNSAFE_DISCLAIMER = """
════════════════════════════════════════════════════════════════
⚠  WARNING: UNSAFE MODE
════════════════════════════════════════════════════════════════

You are enabling shell execution features (--post-process,
--on-complete, and the schedule command). These execute ARBITRARY SHELL COMMANDS
on your machine.

RISKS:
  • Data exfiltration (SSH keys, credentials, files)
  • Arbitrary code execution
  • Persistent backdoors via cron scheduling

DO NOT enable this in AI agent environments where commands
may be constructed from scraped web content.

ScrapingBee is NOT responsible for any damages caused by
these features. Use at your own discretion.

════════════════════════════════════════════════════════════════
"""


def _wipe_api_key_everywhere() -> None:
    """Remove the API key from config .env, cwd .env, and os.environ."""
    import os
    from pathlib import Path

    from ..config import ENV_API_KEY

    # Remove from config .env
    remove_api_key_from_dotenv()

    # Remove from cwd .env if present
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        try:
            lines = []
            with open(cwd_env, encoding="utf-8") as f:
                for line in f:
                    if ENV_API_KEY not in line:
                        lines.append(line)
            with open(cwd_env, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except OSError:
            pass

    # Remove from current process env
    os.environ.pop(ENV_API_KEY, None)


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
@click.option(
    "--unsafe",
    "unsafe_mode",
    is_flag=True,
    default=False,
    hidden=True,
    help="Enable advanced shell execution features.",
)
@click.pass_obj
def auth_cmd(obj: dict, auth_api_key: str | None, show_path_only: bool, unsafe_mode: bool) -> None:
    """Save API key to ~/.config/scrapingbee-cli/.env (from --api-key, env/.env, or prompt)."""
    from ..exec_gate import is_exec_enabled, require_auth_unsafe, set_unsafe_verified

    path = auth_config_path()

    if show_path_only:
        click.echo(str(path))
        return

    if unsafe_mode:
        # Gate: check env vars are set (vague error if not)
        if not require_auth_unsafe():
            raise SystemExit(1)

        # Gate: reject --api-key (must be interactive only)
        if auth_api_key:
            click.echo("Something went wrong. Please try again later.", err=True)
            raise SystemExit(1)

        # Wipe API key from everywhere
        _wipe_api_key_everywhere()
        click.echo("API key removed for security re-authentication.", err=True)

        # Show disclaimer
        click.echo(_UNSAFE_DISCLAIMER, err=True)

        # Require acceptance
        try:
            answer = input("Do you accept the risks? (yes/no): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            click.echo("\nAborted.", err=True)
            raise SystemExit(1)
        if answer != "yes":
            click.echo("Aborted. Unsafe mode not enabled.", err=True)
            raise SystemExit(1)

        # Prompt for API key (interactive only)
        try:
            raw = getpass.getpass("ScrapingBee API key: ")
        except (EOFError, KeyboardInterrupt):
            click.echo("\nAborted.", err=True)
            raise SystemExit(1)
        key = raw.strip()
        if not key:
            click.echo("No API key entered.", err=True)
            raise SystemExit(1)

        click.echo("Validating API key...", err=True)
        if not _validate_api_key(key):
            click.echo("Invalid API key.", err=True)
            raise SystemExit(1)

        # Save key and set unsafe verified
        save_api_key_to_dotenv(key)
        set_unsafe_verified()
        click.echo("API key saved. Unsafe mode enabled.", err=True)
        return

    # Normal auth flow (show warning if unsafe is enabled)
    if is_exec_enabled():
        click.echo("⚠ Unsafe mode is active. Shell execution features are enabled.", err=True)

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

    # Also remove unsafe verified flag
    from ..exec_gate import remove_unsafe_verified

    remove_unsafe_verified()

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
