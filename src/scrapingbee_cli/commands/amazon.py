"""Amazon product and search commands."""

from __future__ import annotations

import asyncio

import click
from click_option_group import optgroup

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
from ..cli_utils import DEVICE_DESKTOP_MOBILE_TABLET, _validate_page, parse_bool, write_output

AMAZON_SORT_BY = [
    "most_recent",
    "price_low_to_high",
    "price_high_to_low",
    "average_review",
    "bestsellers",
    "featured",
]


@click.command("amazon-product")
@click.argument("asin", required=False)
@click.option(
    "--device",
    type=click.Choice(DEVICE_DESKTOP_MOBILE_TABLET, case_sensitive=False),
    default=None,
    help="Device: desktop, mobile, or tablet.",
)
@click.option("--domain", type=str, default=None, help="Amazon domain (e.g. com, co.uk, de, fr).")
@click.option("--country", type=str, default=None, help="Country code (e.g. us, gb, de).")
@click.option("--zip-code", type=str, default=None, help="ZIP code for local availability/pricing.")
@click.option(
    "--language", type=str, default=None, help="Language code (e.g. en_US, es_US, fr_FR)."
)
@click.option("--currency", type=str, default=None, help="Currency code (e.g. USD, EUR, GBP).")
@click.option(
    "--add-html", type=str, default=None, help="Include full HTML in response (true/false)."
)
@click.option("--light-request", type=str, default=None, help="Light request mode (true/false).")
@click.option("--screenshot", type=str, default=None, help="Take screenshot (true/false).")
@click.pass_obj
def amazon_product_cmd(
    obj: dict,
    asin: str | None,
    device: str | None,
    domain: str | None,
    country: str | None,
    zip_code: str | None,
    language: str | None,
    currency: str | None,
    add_html: str | None,
    light_request: str | None,
    screenshot: str | None,
) -> None:
    """Fetch Amazon product details by ASIN."""
    input_file = obj.get("input_file")
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if asin:
            click.echo("cannot use both global --input-file and positional ASIN", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(None)
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(a: str):
                    try:
                        data, headers, status_code = await client.amazon_product(
                            a,
                            device=device,
                            domain=domain,
                            country=country,
                            zip_code=zip_code,
                            language=language,
                            currency=currency,
                            add_html=parse_bool(add_html),
                            light_request=parse_bool(light_request),
                            screenshot=parse_bool(screenshot),
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

    if not asin:
        click.echo("expected one ASIN, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.amazon_product(
                asin,
                device=device,
                domain=domain,
                country=country,
                zip_code=zip_code,
                language=language,
                currency=currency,
                add_html=parse_bool(add_html),
                light_request=parse_bool(light_request),
                screenshot=parse_bool(screenshot),
                retries=obj.get("retries", 3) or 3,
                backoff=obj.get("backoff", 2.0) or 2.0,
            )
        write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


@click.command("amazon-search")
@click.argument("query", required=False)
@optgroup.group("Pagination & sort", help="Pages and sort order")
@optgroup.option("--start-page", type=int, default=None, help="Starting page number.")
@optgroup.option("--pages", type=int, default=None, help="Number of pages to fetch.")
@optgroup.option(
    "--sort-by",
    type=click.Choice(AMAZON_SORT_BY, case_sensitive=False),
    default=None,
    help="Sort order.",
)
@optgroup.group("Device & locale", help="Device, domain, country, language")
@optgroup.option(
    "--device",
    type=click.Choice(DEVICE_DESKTOP_MOBILE_TABLET, case_sensitive=False),
    default=None,
    help="Device: desktop, mobile, or tablet.",
)
@optgroup.option("--domain", type=str, default=None, help="Amazon domain (e.g. com, co.uk, de).")
@optgroup.option("--country", type=str, default=None, help="Country code.")
@optgroup.option("--zip-code", type=str, default=None, help="ZIP code for local results.")
@optgroup.option("--language", type=str, default=None, help="Language code (e.g. en_US, fr_FR).")
@optgroup.option("--currency", type=str, default=None, help="Currency code.")
@optgroup.group("Filters & output", help="Category, merchant, response format")
@optgroup.option("--category-id", type=str, default=None, help="Amazon category ID.")
@optgroup.option("--merchant-id", type=str, default=None, help="Merchant/seller ID.")
@optgroup.option(
    "--autoselect-variant",
    type=str,
    default=None,
    help="Auto-select product variants (true/false).",
)
@optgroup.option("--add-html", type=str, default=None, help="Include full HTML (true/false).")
@optgroup.option("--light-request", type=str, default=None, help="Light request (true/false).")
@optgroup.option("--screenshot", type=str, default=None, help="Take screenshot (true/false).")
@click.pass_obj
def amazon_search_cmd(
    obj: dict,
    query: str | None,
    start_page: int | None,
    pages: int | None,
    sort_by: str | None,
    device: str | None,
    domain: str | None,
    country: str | None,
    zip_code: str | None,
    language: str | None,
    currency: str | None,
    category_id: str | None,
    merchant_id: str | None,
    autoselect_variant: str | None,
    add_html: str | None,
    light_request: str | None,
    screenshot: str | None,
) -> None:
    """Search Amazon products."""
    input_file = obj.get("input_file")
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
    _validate_page(start_page, "start_page")
    _validate_page(pages, "pages")

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
                        data, headers, status_code = await client.amazon_search(
                            q,
                            start_page=start_page,
                            pages=pages,
                            sort_by=sort_by,
                            device=device,
                            domain=domain,
                            country=country,
                            zip_code=zip_code,
                            language=language,
                            currency=currency,
                            category_id=category_id,
                            merchant_id=merchant_id,
                            autoselect_variant=parse_bool(autoselect_variant),
                            add_html=parse_bool(add_html),
                            light_request=parse_bool(light_request),
                            screenshot=parse_bool(screenshot),
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
            data, headers, status_code = await client.amazon_search(
                query,
                start_page=start_page,
                pages=pages,
                sort_by=sort_by,
                device=device,
                domain=domain,
                country=country,
                zip_code=zip_code,
                language=language,
                currency=currency,
                category_id=category_id,
                merchant_id=merchant_id,
                autoselect_variant=parse_bool(autoselect_variant),
                add_html=parse_bool(add_html),
                light_request=parse_bool(light_request),
                screenshot=parse_bool(screenshot),
                retries=obj.get("retries", 3) or 3,
                backoff=obj.get("backoff", 2.0) or 2.0,
            )
        write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


def register(cli):  # noqa: ANN001
    cli.add_command(amazon_product_cmd, "amazon-product")
    cli.add_command(amazon_search_cmd, "amazon-search")
