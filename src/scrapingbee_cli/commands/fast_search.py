"""Fast Search command."""

from __future__ import annotations

import asyncio

import click
from click_option_group import optgroup

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
    _validate_page,
    check_api_response,
    prepare_batch_inputs,
    store_common_options,
    write_output,
)
from ..client import Client
from ..config import BASE_URL, get_api_key


@click.command("fast-search")
@click.argument("query", required=False)
@optgroup.group("Search", help="Pagination and locale")
@optgroup.option("--page", type=int, default=None, help="Page number (default: 1).")
@optgroup.option(
    "--country-code",
    type=str,
    default=None,
    help="Country code for results (ISO 3166-1, e.g. us, fr).",
)
@optgroup.option("--language", type=str, default=None, help="Language code (e.g. en, fr).")
@_batch_options
@click.pass_obj
def fast_search_cmd(
    obj: dict,
    query: str | None,
    page: int | None,
    country_code: str | None,
    language: str | None,
    **kwargs,
) -> None:
    """Search using the Fast Search API (sub-second results)."""
    store_common_options(obj, **kwargs)
    input_file = obj.get("input_file")
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
    _validate_page(page)

    if input_file:
        if query:
            click.echo("cannot use both --input-file and positional query", err=True)
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

        async def api_call(client, q):
            return await client.fast_search(
                q,
                page=page,
                country_code=country_code,
                language=language,
                retries=int(obj.get("retries") or 3),
                backoff=float(obj.get("backoff") or 2.0),
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
            output_format=obj.get("output_format"),
            post_process=obj.get("post_process"),
            update_csv_path=input_file if obj.get("update_csv") else None,
            input_column=obj.get("input_column"),
            output_file=obj.get("output_file") or None,
            extract_field=obj.get("extract_field"),
            fields=obj.get("fields"),
        )
        return

    if not query:
        click.echo("expected one search query, or use --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.fast_search(
                query,
                page=page,
                country_code=country_code,
                language=language,
                retries=int(obj.get("retries") or 3),
                backoff=float(obj.get("backoff") or 2.0),
            )
        check_api_response(data, status_code)
        from ..credits import fast_search_credits

        write_output(
            data,
            headers,
            status_code,
            obj["output_file"],
            obj["verbose"],
            smart_extract=obj.get("smart_extract"),
            extract_field=obj.get("extract_field"),
            fields=obj.get("fields"),
            command="fast-search",
            credit_cost=fast_search_credits(),
        )

    asyncio.run(_single())


def register(cli: click.Group) -> None:
    cli.add_command(fast_search_cmd, "fast-search")
