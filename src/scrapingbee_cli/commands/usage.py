"""Usage command."""

from __future__ import annotations

import asyncio

import click

from ..client import Client, pretty_json
from ..config import BASE_URL, get_api_key


@click.command()
@click.pass_obj
def usage_cmd(obj: dict) -> None:
    """Check API credit usage and concurrency."""
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
            click.echo(pretty_json(data))

    asyncio.run(_run())


def register(cli: click.Group) -> None:
    cli.add_command(usage_cmd, "usage")
