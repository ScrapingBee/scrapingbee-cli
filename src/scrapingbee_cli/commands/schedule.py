"""Schedule command — repeatedly run a scrapingbee sub-command at a fixed interval."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime

import click

_DURATION_RE = re.compile(r"^(\d+)(s|m|h|d)$")

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_duration(s: str) -> int:
    """Parse a duration string like '30s', '5m', '1h', '2d' → seconds."""
    m = _DURATION_RE.match(s.strip())
    if not m:
        raise click.BadParameter(
            f"Invalid duration {s!r}. Use e.g. 30s, 5m, 1h, 2d.",
            param_hint="'--every'",
        )
    n, unit = int(m.group(1)), m.group(2)
    return n * _UNIT_SECONDS[unit]


def _extract_output_dir(cmd_args: tuple[str, ...]) -> str | None:
    """Extract the value of --output-dir from cmd_args, or None."""
    args = list(cmd_args)
    if "--output-dir" in args:
        idx = args.index("--output-dir")
        if idx + 1 < len(args):
            return args[idx + 1]
    return None


def _make_run_subdir(parent: str) -> str:
    """Return a unique timestamped sub-run directory path under parent.

    E.g. ``price-runs/`` → ``price-runs/run_20250115_100000``.
    Used by ``--auto-diff`` so each scheduled run writes to its own directory,
    preventing the same-dir guard from triggering when ``--diff-dir`` and
    ``--output-dir`` would otherwise point at the same path.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(parent, f"run_{ts}")


@click.command(
    "schedule",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--every", required=True, help="Run interval: 30s, 5m, 1h, 2d")
@click.option(
    "--auto-diff",
    is_flag=True,
    default=False,
    help=(
        "Automatically pass the previous run's output directory as --diff-dir "
        "to the next run, enabling change detection across runs."
    ),
)
@click.argument("cmd_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def schedule_cmd(obj: dict | None, every: str, auto_diff: bool, cmd_args: tuple[str, ...]) -> None:
    """Repeatedly run a scrapingbee command at a fixed interval.

    \b
    Examples:
      scrapingbee schedule --every 1h scrape https://example.com
      scrapingbee schedule --every 30m --auto-diff --output-dir run google "python news"

    Note: global options (--output-dir, --output-file, --input-file) must appear
    AFTER schedule's own options (--every, --auto-diff) but BEFORE the subcommand name.
    """
    interval = _parse_duration(every)
    entry = sys.argv[0]  # 'scrapingbee' executable path

    env = os.environ.copy()

    # Determine base output directory (cmd_args takes precedence over ctx.obj).
    # When --auto-diff is active this becomes the parent; each run writes to a
    # unique timestamped subdirectory to avoid the same-dir guard (which blocks
    # diff_dir == output_dir).
    base_output_dir: str | None = _extract_output_dir(cmd_args) or (
        obj.get("output_dir") if obj else None
    )
    output_dir_in_cmd_args: bool = "--output-dir" in list(cmd_args)

    run_n = 0
    prev_output_dir: str | None = None
    try:
        while True:
            run_n += 1
            click.echo(
                f"[schedule] Run #{run_n} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                err=True,
            )

            # When --auto-diff and a base output dir are both given, each run
            # writes to a unique timestamped subdirectory under base_output_dir.
            if auto_diff and base_output_dir:
                run_dir: str | None = _make_run_subdir(base_output_dir)
                if output_dir_in_cmd_args:
                    # Replace --output-dir value in-place inside cmd_args.
                    args = list(cmd_args)
                    idx = args.index("--output-dir")
                    args[idx + 1] = run_dir
                    effective_args: list[str] = args
                    extra_global: list[str] = []
                else:
                    # --output-dir was a global CLI option (in ctx.obj); inject it.
                    effective_args = list(cmd_args)
                    extra_global = ["--output-dir", run_dir]
            else:
                run_dir = None
                effective_args = list(cmd_args)
                extra_global = []

            # Inject --diff-dir pointing at the previous run's output directory.
            if auto_diff and prev_output_dir and "--diff-dir" not in effective_args:
                cmd = [entry, "--diff-dir", prev_output_dir] + extra_global + effective_args
            else:
                cmd = [entry] + extra_global + effective_args

            result = subprocess.run(cmd, env=env, capture_output=False)

            # Track the actual output directory used by this run so the next
            # run can reference it via --diff-dir.
            if auto_diff:
                prev_output_dir = run_dir or _extract_output_dir(cmd_args) or None

            if result.returncode != 0:
                click.echo(
                    f"[schedule] Run #{run_n} exited with code {result.returncode}.",
                    err=True,
                )

            click.echo(f"[schedule] Sleeping {every}...", err=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        click.echo("\n[schedule] Stopped.", err=True)


def register(cli: click.Group) -> None:
    cli.add_command(schedule_cmd, "schedule")
