"""ChatGPT command."""

from __future__ import annotations

import asyncio

import click

from ..batch import (
    _find_completed_n,
    get_batch_usage,
    read_input_file,
    resolve_batch_concurrency,
    run_api_batch,
    validate_batch_run,
)
from ..cli_utils import (
    _batch_options,
    check_api_response,
    prepare_batch_inputs,
    store_common_options,
    write_output,
)
from ..client import Client
from ..config import BASE_URL, get_api_key


@click.command()
@click.argument("prompt", nargs=-1, required=False)
@_batch_options
@click.pass_obj
def chatgpt_cmd(obj: dict, prompt: tuple[str, ...], **kwargs) -> None:
    """Send a prompt to the ChatGPT API."""
    store_common_options(obj, **kwargs)
    input_file = obj.get("input_file")
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if prompt:
            click.echo("cannot use both --input-file and positional prompt", err=True)
            raise SystemExit(1)
        try:
            inputs = read_input_file(input_file, input_column=obj.get("input_column"))
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        inputs = prepare_batch_inputs(inputs, obj)
        usage_info = get_batch_usage(None)
        try:
            validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        skip_n = (
            _find_completed_n(obj.get("output_dir") or "") if obj.get("resume") else frozenset()
        )

        async def api_call(client, p):
            return await client.chatgpt(
                p,
                retries=obj.get("retries", 3) or 3,
                backoff=obj.get("backoff", 2.0) or 2.0,
            )

        run_api_batch(
            key=key,
            inputs=inputs,
            concurrency=concurrency,
            from_user=obj["concurrency"] > 0,
            skip_n=skip_n,
            output_dir=obj.get("output_dir") or None,
            verbose=obj["verbose"],
            show_progress=obj.get("progress", True),
            api_call=api_call,
            on_complete=obj.get("on_complete"),
            output_format=obj.get("output_format", "files"),
            post_process=obj.get("post_process"),
            update_csv_path=input_file if obj.get("update_csv") else None,
            input_column=obj.get("input_column"),
        )
        return

    if not prompt:
        click.echo("expected at least one prompt argument, or use --input-file for batch", err=True)
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
        write_output(
            data,
            headers,
            status_code,
            obj["output_file"],
            obj["verbose"],
            extract_field=obj.get("extract_field"),
            fields=obj.get("fields"),
            command="chatgpt",
        )

    asyncio.run(_single())


def register(cli: click.Group) -> None:
    cli.add_command(chatgpt_cmd, "chatgpt")
