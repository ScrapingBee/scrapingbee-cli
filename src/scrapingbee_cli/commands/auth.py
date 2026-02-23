"""Auth, docs, and logout commands."""

from __future__ import annotations

import getpass

import click

from ..config import (
    auth_config_path,
    get_api_key,
    get_api_key_if_set,
    remove_api_key_from_dotenv,
    save_api_key_to_dotenv,
)

DOCS_URL = "https://www.scrapingbee.com/documentation/"


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
    if key:
        path = save_api_key_to_dotenv(key)
        click.echo(f"API key saved to {path}. You can now run scrapingbee commands.")
        return
    try:
        raw = getpass.getpass("ScrapingBee API key: ")
    except (EOFError, KeyboardInterrupt):
        click.echo(
            "Cannot read API key (non-interactive). Use --api-key=KEY or set SCRAPINGBEE_API_KEY.",
            err=True,
        )
        raise SystemExit(1)
    key = raw.strip()
    if not key:
        click.echo("No API key entered.", err=True)
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
    removed = remove_api_key_from_dotenv()
    if removed:
        click.echo(f"API key removed from {auth_config_path()}.")
    else:
        click.echo(f"No stored API key found in {auth_config_path()}.")
    click.echo(
        "If you set SCRAPINGBEE_API_KEY in your shell, unset it with: unset SCRAPINGBEE_API_KEY"
    )


def register(cli):  # noqa: ANN001
    cli.add_command(auth_cmd, "auth")
    cli.add_command(docs_cmd, "docs")
    cli.add_command(logout_cmd, "logout")
