"""ChatGPT command."""

from __future__ import annotations

import asyncio

import click

from ..batch import (
    get_batch_usage,
    read_input_file,
    resolve_batch_concurrency,
    run_batch_async,
    validate_batch_run,
    write_batch_output_to_dir,
)
from ..client import Client
from ..config import BASE_URL, get_api_key
from ..cli_utils import check_api_response, write_output


@click.command()
@click.argument("prompt", nargs=-1, required=False)
@click.pass_obj
def chatgpt_cmd(
    obj: dict,
    prompt: tuple[str, ...],
) -> None:
    """Send a prompt to the ChatGPT API."""
    input_file = obj.get("input_file")
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if prompt:
            click.echo("cannot use both global --input-file and positional prompt", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(None)
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(p: str):
                    try:
                        data, headers, status_code = await client.chatgpt(
                            p,
                            retries=obj.get("retries", 3) or 3,
                            backoff=obj.get("backoff", 2.0) or 2.0,
                        )
                        if status_code >= 400:
                            err = RuntimeError(f"HTTP {status_code}")
                            return data, headers, status_code, err, "json"
                        return data, headers, status_code, None, "json"
                    except Exception as e:
                        return b"", {}, 0, e, "json"

                results = await run_batch_async(
                    inputs, concurrency, do_one, from_user=obj["concurrency"] > 0
                )
            out_dir = write_batch_output_to_dir(
                results, obj.get("output_dir") or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not prompt:
        click.echo("expected at least one prompt argument, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    prompt_str = " ".join(prompt)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.chatgpt(
                prompt_str,
                retries=obj.get("retries", 3) or 3,
                backoff=obj.get("backoff", 2.0) or 2.0,
            )
        check_api_response(data, status_code)
        write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


def register(cli):  # noqa: ANN001
    cli.add_command(chatgpt_cmd, "chatgpt")
