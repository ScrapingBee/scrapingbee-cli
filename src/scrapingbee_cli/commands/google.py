"""Google Search command."""

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
    DEVICE_DESKTOP_MOBILE,
    _batch_options,
    _validate_page,
    check_api_response,
    norm_val,
    parse_bool,
    prepare_batch_inputs,
    store_common_options,
    write_output,
)
from ..client import Client
from ..config import BASE_URL, get_api_key


def _warn_empty_organic(data: bytes, search_type: str | None) -> None:
    """Warn if a classic Google search returned an empty organic_results array."""
    if search_type and search_type.lower() not in ("classic", ""):
        return
    try:
        import json as _json

        obj = _json.loads(data)
    except Exception:
        return
    if not isinstance(obj, dict):
        return
    organic = obj.get("organic_results")
    if isinstance(organic, list) and len(organic) == 0:
        click.echo(
            "Warning: organic_results is empty. Possible causes: the query matched "
            "no results, an API-side parsing issue, or Google changed its HTML structure.",
            err=True,
        )


@click.command()
@click.argument("query", required=False)
@optgroup.group("Search", help="Search type, locale, and pagination")
@optgroup.option(
    "--search-type",
    type=click.Choice(
        ["classic", "news", "maps", "lens", "shopping", "images", "ai-mode"],
        case_sensitive=False,
    ),
    default=None,
    help="Search type. Default: classic. ai-mode returns an AI-generated answer.",
)
@optgroup.option(
    "--country-code",
    type=str,
    default=None,
    help="Country code for geolocation (ISO 3166-1, e.g. us, gb).",
)
@optgroup.option(
    "--device",
    type=click.Choice(DEVICE_DESKTOP_MOBILE, case_sensitive=False),
    default=None,
    help="Device: desktop or mobile. news not available with mobile.",
)
@optgroup.option("--page", type=int, default=None, help="Page number (default: 1).")
@optgroup.option(
    "--language",
    type=str,
    default=None,
    help="Language code for results (e.g. en, fr, de). Default: en.",
)
@optgroup.group("Filters", help="Autocorrection, extra params, and response format")
@optgroup.option("--nfpr", type=str, default=None, help="Disable autocorrection (true/false).")
@optgroup.option(
    "--extra-params", type=str, default=None, help="Extra URL parameters (URL-encoded)."
)
@optgroup.option(
    "--add-html", type=str, default=None, help="Include full HTML in response (true/false)."
)
@optgroup.option(
    "--light-request",
    type=str,
    default=None,
    help="Light request mode, 10 credits (true/false). Fewer data than regular.",
)
@_batch_options
@click.pass_obj
def google_cmd(
    obj: dict,
    query: str | None,
    search_type: str | None,
    country_code: str | None,
    device: str | None,
    page: int | None,
    language: str | None,
    nfpr: str | None,
    extra_params: str | None,
    add_html: str | None,
    light_request: str | None,
    **kwargs,
) -> None:
    """Search Google using the Google Search API."""
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
            click.echo("cannot use both global --input-file and positional query", err=True)
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
            return await client.google_search(
                q,
                search_type=norm_val(search_type),
                country_code=country_code,
                device=device,
                page=page,
                language=language,
                nfpr=parse_bool(nfpr),
                extra_params=extra_params,
                add_html=parse_bool(add_html),
                light_request=parse_bool(light_request),
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

    if not query:
        click.echo("expected one search query, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.google_search(
                query,
                search_type=norm_val(search_type),
                country_code=country_code,
                device=device,
                page=page,
                language=language,
                nfpr=parse_bool(nfpr),
                extra_params=extra_params,
                add_html=parse_bool(add_html),
                light_request=parse_bool(light_request),
                retries=obj.get("retries", 3) or 3,
                backoff=obj.get("backoff", 2.0) or 2.0,
            )
        check_api_response(data, status_code)
        _warn_empty_organic(data, search_type)
        write_output(
            data,
            headers,
            status_code,
            obj["output_file"],
            obj["verbose"],
            extract_field=obj.get("extract_field"),
            fields=obj.get("fields"),
            command="google",
        )

    asyncio.run(_single())


def register(cli: click.Group) -> None:
    cli.add_command(google_cmd, "google")
