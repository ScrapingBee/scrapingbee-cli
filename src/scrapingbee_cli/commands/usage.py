"""Usage command."""

from __future__ import annotations

import asyncio
import json as _json

import click

from ..batch import write_usage_file_cache
from ..cli_utils import _output_options, store_common_options
from ..client import Client, parse_usage, pretty_json
from ..config import BASE_URL, get_api_key
from ..theme import is_repl_mode


@click.command()
@_output_options
@click.pass_obj
def usage_cmd(obj: dict, **kwargs) -> None:
    """Check API credit usage and concurrency."""
    store_common_options(obj, **kwargs)
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
    retries = int(obj.get("retries") or 3)
    backoff = float(obj.get("backoff") or 2.0)

    async def _run() -> None:
        async with Client(key, BASE_URL) as client:
            data, _, status_code = await client.usage(retries=retries, backoff=backoff)
            if status_code != 200:
                click.echo(
                    f"API returned status {status_code}: {data.decode('utf-8', errors='replace')}",
                    err=True,
                )
                raise SystemExit(1)
            # Warm the shared file cache so concurrent batch subprocesses skip the API call.
            write_usage_file_cache(key, parse_usage(data))

            # Intentional: REPL prints a human dashboard; plain CLI prints raw JSON so a
            # script or AI can parse `usage`. Do not "fix" the CLI branch to human output.
            if is_repl_mode():
                _show_repl_usage(data)
            else:
                output_file = obj.get("output_file")
                if output_file:
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(pretty_json(data) + "\n")
                else:
                    click.echo(pretty_json(data))

    asyncio.run(_run())


def _show_repl_usage(data: bytes) -> None:
    """Render a fully styled usage dashboard to stderr (REPL mode only)."""
    from rich.text import Text

    from ..theme import (
        BEE_YELLOW,
        echo_key_value,
        echo_separator,
        err_console,
        format_honeycomb_meter,
    )

    raw = _json.loads(data)

    header = Text()
    header.append("  Credit Usage", style=f"bold {BEE_YELLOW}")
    err_console.print(header)
    err_console.print()

    used = raw.get("used_api_credit", 0) or 0
    total = raw.get("max_api_credit", 0) or 0
    remaining = total - used

    meter = format_honeycomb_meter(used, total)
    err_console.print(meter)
    err_console.print()

    echo_key_value("Credits used", f"{used:,}")
    echo_key_value("Credits remaining", f"{remaining:,}")
    echo_key_value("Total credits", f"{total:,}")
    err_console.print()

    max_conc = raw.get("max_concurrency", "N/A")
    cur_conc = raw.get("current_concurrency", 0)
    echo_key_value("Max concurrency", str(max_conc))
    echo_key_value("Current concurrency", str(cur_conc))
    err_console.print()

    renewal = raw.get("renewal_subscription_date", "")
    if renewal:
        try:
            date_part, time_part = renewal.split("T")
            time_clean = time_part.split(".")[0][:5]
            echo_key_value("Renewal date", f"{date_part} {time_clean} UTC")
        except Exception:
            echo_key_value("Renewal date", renewal)

    echo_separator()


def register(cli: click.Group) -> None:
    cli.add_command(usage_cmd, "usage")
