"""Schedule command — register cron jobs to run scrapingbee commands at intervals."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import click

_DURATION_RE = re.compile(r"^(\d+)(s|m|h|d)$")

_CONFIG_DIR = Path.home() / ".config" / "scrapingbee-cli"
_REGISTRY_FILE = _CONFIG_DIR / "schedules.json"
_LOG_DIR = _CONFIG_DIR / "logs"

_CRON_TAG = "# scrapingbee-schedule:"


def _duration_to_cron(s: str) -> str:
    """Convert a duration string like '5m', '1h', '2d' to a cron expression.
    Supports: Ns (not supported in cron — error), Nm, Nh, Nd."""
    m = _DURATION_RE.match(s.strip())
    if not m:
        raise click.BadParameter(
            f"Invalid duration {s!r}. Use e.g. 5m, 1h, 2d.",
            param_hint="'--every'",
        )
    n, unit = int(m.group(1)), m.group(2)
    if unit == "s":
        if n < 60:
            raise click.BadParameter(
                "Cron does not support intervals shorter than 1 minute. Use 1m or higher.",
                param_hint="'--every'",
            )
        # Convert seconds to minutes
        n = n // 60
        unit = "m"
    if unit == "m":
        if n <= 0:
            raise click.BadParameter("Interval must be at least 1m.", param_hint="'--every'")
        return f"*/{n} * * * *"
    if unit == "h":
        return f"0 */{n} * * *"
    if unit == "d":
        return f"0 0 */{n} * *"
    raise click.BadParameter(f"Unknown unit {unit!r}.", param_hint="'--every'")


def _find_scrapingbee() -> str:
    """Find the scrapingbee executable path."""
    exe = shutil.which("scrapingbee")
    if exe:
        return exe
    return sys.argv[0]


def _get_current_crontab() -> str:
    """Read the current user crontab. Returns empty string if none."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


def _write_crontab(content: str) -> None:
    """Write a new crontab for the current user."""
    try:
        proc = subprocess.run(
            ["crontab", "-"],
            input=content,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "crontab timed out. On macOS, grant Terminal 'Full Disk Access' in "
            "System Settings > Privacy & Security, or run: crontab -e"
        )
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to write crontab: {proc.stderr.strip()}")


def _load_registry() -> dict[str, dict]:
    """Load the schedules registry."""
    try:
        return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def _save_registry(registry: dict[str, dict]) -> None:
    """Save the schedules registry."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _REGISTRY_FILE.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def _auto_name(cmd_args: tuple[str, ...]) -> str:
    """Generate a schedule name from the command args."""
    parts = [a for a in cmd_args if not a.startswith("-")]
    if parts:
        return "-".join(parts[:2])[:30]
    return f"schedule-{os.getpid()}"


def _format_running_since(created_at: str) -> str:
    """Format how long a schedule has been running."""
    try:
        dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
        total_s = int((datetime.now() - dt).total_seconds())
        if total_s < 60:
            return f"{total_s}s"
        if total_s < 3600:
            return f"{total_s // 60}m"
        if total_s < 86400:
            h, m = divmod(total_s // 60, 60)
            return f"{h}h {m}m"
        d, h = divmod(total_s // 3600, 24)
        return f"{d}d {h}h"
    except ValueError:
        return "?"


def _print_schedules(registry: dict[str, dict]) -> None:
    """Print a table of registered schedules."""
    if not registry:
        click.echo("No active schedules.", err=True)
        return
    click.echo(f"\nActive schedules ({len(registry)}):", err=True)
    click.echo(f"  {'Name':<20} {'Interval':<10} {'Running':<12} Command", err=True)
    click.echo(f"  {'─' * 20} {'─' * 10} {'─' * 12} {'─' * 40}", err=True)
    for name, info in registry.items():
        running = _format_running_since(info.get("created_at", ""))
        click.echo(
            f"  {name:<20} {info.get('interval', '?'):<10} "
            f"{running:<12} {info.get('command', '?')}",
            err=True,
        )
    click.echo(err=True)


def _add_schedule(name: str, every: str, cmd_args: tuple[str, ...]) -> None:
    """Add a cron job for the schedule."""
    cron_expr = _duration_to_cron(every)
    exe = _find_scrapingbee()

    # Build the command (without schedule --every --name)
    full_cmd = f"{exe} {' '.join(cmd_args)}"

    # Ensure log directory exists
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOG_DIR / f"{name}.log"

    # Cron line: command >> log 2>&1, tagged with name for identification
    cron_line = f'{cron_expr} {full_cmd} >> "{log_path}" 2>&1 {_CRON_TAG}{name}'

    # Read current crontab, check for duplicate name
    current = _get_current_crontab()
    tag = f"{_CRON_TAG}{name}"

    lines = current.splitlines()
    # Remove any existing entry with the same name
    had_existing = any(tag in line for line in lines)
    if had_existing:
        if not click.confirm(f"Schedule '{name}' already exists. Replace it?"):
            click.echo("Cancelled.", err=True)
            return
    lines = [line for line in lines if tag not in line]
    lines.append(cron_line)

    # Write updated crontab
    new_crontab = "\n".join(lines).strip() + "\n"
    _write_crontab(new_crontab)

    # Update registry
    registry = _load_registry()
    registry[name] = {
        "interval": every,
        "cron": cron_expr,
        "command": full_cmd,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "log": str(log_path),
    }
    _save_registry(registry)

    click.echo(f"Schedule '{name}' created: {cron_expr}", err=True)
    click.echo(f"  Command: {full_cmd}", err=True)
    click.echo(f"  Log: {log_path}", err=True)
    click.echo(f"  Stop with: scrapingbee schedule --stop {name}", err=True)

    _print_schedules(registry)


def _remove_cron_entry(name: str) -> None:
    """Remove a cron entry by schedule name tag."""
    current = _get_current_crontab()
    tag = f"{_CRON_TAG}{name}"
    lines = [line for line in current.splitlines() if tag not in line]
    new_crontab = "\n".join(lines).strip() + "\n" if lines else ""
    _write_crontab(new_crontab)


def _stop_schedule(name: str | None) -> None:
    """Stop one or all schedules by removing cron entries."""
    registry = _load_registry()

    if not registry:
        click.echo("No active schedules to stop.", err=True)
        raise SystemExit(1)

    if name:
        if name not in registry:
            click.echo(f"No schedule named '{name}' found.", err=True)
            _print_schedules(registry)
            raise SystemExit(1)
        _remove_cron_entry(name)
        del registry[name]
        _save_registry(registry)
        click.echo(f"Stopped schedule '{name}'.", err=True)
    else:
        click.echo(f"Stopping all {len(registry)} schedule(s):", err=True)
        for sname in list(registry):
            _remove_cron_entry(sname)
            click.echo(f"  Removed '{sname}'", err=True)
        _save_registry({})
        click.echo("Done.", err=True)


@click.command(
    "schedule",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--every", required=False, default=None, help="Run interval: 5m, 1h, 2d (minimum 1m)")
@click.option(
    "--name",
    default=None,
    help="Name for this schedule. Auto-generated if omitted.",
)
@click.option(
    "--stop",
    "stop_name",
    default=None,
    type=str,
    is_flag=False,
    flag_value="__all__",
    help="Stop a schedule by name (e.g. --stop btc-price), or stop all (--stop all).",
)
@click.option(
    "--list",
    "list_schedules",
    is_flag=True,
    default=False,
    help="List all active schedules.",
)
@click.argument("cmd_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def schedule_cmd(
    obj: dict | None,
    every: str | None,
    name: str | None,
    stop_name: str | None,
    list_schedules: bool,
    cmd_args: tuple[str, ...],
) -> None:
    """Schedule a scrapingbee command to run at a fixed interval using cron.

    \b
    Examples:
      scrapingbee schedule --every 5m --name btc-price --update-csv scrape --input-file btc.csv --input-column url --extract-rules '{"price":".amount"}'
      scrapingbee schedule --every 1h --name news google "breaking news" --search-type news
      scrapingbee schedule --list
      scrapingbee schedule --stop btc-price
      scrapingbee schedule --stop all

    All options (--update-csv, --input-file, etc.) are part of the subcommand being scheduled.
    """
    if list_schedules:
        _print_schedules(_load_registry())
        return

    if stop_name is not None:
        _stop_schedule(None if stop_name in ("__all__", "all") else stop_name)
        return

    if not every:
        click.echo("--every is required (unless using --stop or --list).", err=True)
        raise SystemExit(1)

    if not cmd_args:
        click.echo("No command specified. Provide a scrapingbee command to schedule.", err=True)
        raise SystemExit(1)

    schedule_name = name or _auto_name(cmd_args)
    _add_schedule(schedule_name, every, cmd_args)


def register(cli: click.Group) -> None:
    cli.add_command(schedule_cmd, "schedule")
