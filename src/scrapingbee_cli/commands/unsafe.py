"""Unsafe mode management — list status, disable, view audit log."""

from __future__ import annotations

import click

from ..audit import AUDIT_LOG_PATH, read_audit_log
from ..exec_gate import (
    get_whitelist,
    is_exec_enabled,
    remove_unsafe_verified,
)


@click.command("unsafe")
@click.option(
    "--list",
    "list_status",
    is_flag=True,
    default=False,
    help="Show unsafe mode status and whitelist.",
)
@click.option(
    "--disable",
    is_flag=True,
    default=False,
    help="Disable unsafe mode (removes unsafe verified flag).",
)
@click.option(
    "--audit",
    "show_audit",
    is_flag=True,
    default=False,
    help="Print recent audit log entries.",
)
@click.option(
    "--audit-lines",
    type=int,
    default=50,
    help="Number of audit log lines to show (default: 50).",
)
@click.pass_obj
def unsafe_cmd(
    obj: dict,
    list_status: bool,
    disable: bool,
    show_audit: bool,
    audit_lines: int,
) -> None:
    """Manage unsafe shell execution features.

    Use --list to check status, --disable to turn off, --audit to review log.
    To enable unsafe mode, use: scrapingbee auth --unsafe
    """
    if disable:
        remove_unsafe_verified()
        click.echo("Unsafe mode disabled.", err=True)
        return

    if show_audit:
        click.echo(f"Audit log: {AUDIT_LOG_PATH}", err=True)
        click.echo(read_audit_log(audit_lines))
        return

    if list_status:
        enabled = is_exec_enabled()
        whitelist = get_whitelist()

        click.echo(f"Unsafe mode: {'ENABLED' if enabled else 'DISABLED'}", err=True)
        if whitelist:
            click.echo(f"Whitelisted commands ({len(whitelist)}):", err=True)
            for cmd in whitelist:
                click.echo(f"  • {cmd}", err=True)
        else:
            click.echo("No whitelisted commands.", err=True)
        click.echo(f"Audit log: {AUDIT_LOG_PATH}", err=True)
        return

    # No flags — show help
    click.echo("Use --list, --disable, or --audit. Run 'scrapingbee unsafe --help' for details.")


def register(cli: click.Group) -> None:
    cli.add_command(unsafe_cmd, "unsafe")
