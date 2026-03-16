"""Usage command."""

from __future__ import annotations

import asyncio

import click

from ..cli_utils import _output_options, store_common_options
from ..client import Client, pretty_json
from ..config import BASE_URL, get_api_key


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
    retries = obj.get("retries", 3) or 3
    backoff = obj.get("backoff", 2.0) or 2.0

    async def _run() -> None:
        async with Client(key, BASE_URL) as client:
            data, _, status_code = await client.usage(retries=retries, backoff=backoff)
            if status_code != 200:
                click.echo(
                    f"API returned status {status_code}: {data.decode('utf-8', errors='replace')}",
                    err=True,
                )
                raise SystemExit(1)
            output_file = obj.get("output_file")
            if output_file:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(pretty_json(data) + "\n")
            else:
                click.echo(pretty_json(data))

    asyncio.run(_run())


def register(cli: click.Group) -> None:
    cli.add_command(usage_cmd, "usage")
