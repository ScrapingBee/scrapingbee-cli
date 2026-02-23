"""Google Search command."""

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
from ..cli_utils import DEVICE_DESKTOP_MOBILE, _validate_page, parse_bool, write_output


@click.command()
@click.argument("query", required=False)
@click.option(
    "--search-type",
    type=click.Choice(
        ["classic", "news", "maps", "lens", "shopping", "images"],
        case_sensitive=False,
    ),
    default=None,
    help="Search type. Default: classic.",
)
@click.option(
    "--country-code",
    type=str,
    default=None,
    help="Country code for geolocation (ISO 3166-1, e.g. us, gb).",
)
@click.option(
    "--device",
    type=click.Choice(DEVICE_DESKTOP_MOBILE, case_sensitive=False),
    default=None,
    help="Device: desktop or mobile. news not available with mobile.",
)
@click.option("--page", type=int, default=None, help="Page number (default: 1).")
@click.option(
    "--language",
    type=str,
    default=None,
    help="Language code for results (e.g. en, fr, de). Default: en.",
)
@click.option("--nfpr", type=str, default=None, help="Disable autocorrection (true/false).")
@click.option("--extra-params", type=str, default=None, help="Extra URL parameters (URL-encoded).")
@click.option(
    "--add-html", type=str, default=None, help="Include full HTML in response (true/false)."
)
@click.option(
    "--light-request",
    type=str,
    default=None,
    help="Light request mode, 10 credits (true/false). Fewer data than regular.",
)
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
) -> None:
    """Search Google using the Google Search API."""
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
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(None)
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(q: str):
                    try:
                        data, headers, status_code = await client.google_search(
                            q,
                            search_type=search_type,
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

    if not query:
        click.echo("expected one search query, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.google_search(
                query,
                search_type=search_type,
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
        write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


def register(cli):  # noqa: ANN001
    cli.add_command(google_cmd, "google")
