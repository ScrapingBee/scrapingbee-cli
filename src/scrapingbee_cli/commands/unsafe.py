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
@click.option(
    "--audit-since",
    type=str,
    default=None,
    help="Show entries from this time (e.g. '2026-03-31', '2026-03-31T14:00').",
)
@click.option(
    "--audit-until",
    type=str,
    default=None,
    help="Show entries until this time (e.g. '2026-03-31', '2026-03-31T18:00').",
)
@click.pass_obj
def unsafe_cmd(
    obj: dict,
    list_status: bool,
    disable: bool,
    show_audit: bool,
    audit_lines: int,
    audit_since: str | None,
    audit_until: str | None,
) -> None:
    """Manage unsafe shell execution features.

    Use --list to check status, --disable to turn off, --audit to review log.
    To enable unsafe mode, use: scrapingbee auth --unsafe
    """
    if disable:
        if not is_exec_enabled():
            click.echo("Unsafe mode is already disabled.", err=True)
            return
        remove_unsafe_verified()
        click.echo("Unsafe mode disabled.", err=True)
        return

    if show_audit or audit_since or audit_until:
        if audit_lines < 0:
            click.echo("--audit-lines must be a positive number.", err=True)
            raise SystemExit(1)

        from datetime import datetime, timezone

        since_dt = None
        until_dt = None
        if audit_since:
            try:
                since_dt = datetime.fromisoformat(audit_since)
                if since_dt.tzinfo is None:
                    since_dt = since_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                click.echo(
                    f"Invalid --audit-since format: '{audit_since}'. "
                    "Use ISO format (e.g. '2026-03-31' or '2026-03-31T14:00').",
                    err=True,
                )
                raise SystemExit(1)
        if audit_until:
            try:
                until_dt = datetime.fromisoformat(audit_until)
                if until_dt.tzinfo is None:
                    until_dt = until_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                click.echo(
                    f"Invalid --audit-until format: '{audit_until}'. "
                    "Use ISO format (e.g. '2026-03-31' or '2026-03-31T18:00').",
                    err=True,
                )
                raise SystemExit(1)

        click.echo(f"Audit log: {AUDIT_LOG_PATH}", err=True)
        click.echo(read_audit_log(n=audit_lines, since=since_dt, until=until_dt))
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
