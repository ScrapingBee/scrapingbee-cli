"""Amazon product and search commands."""

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
    DEVICE_DESKTOP_MOBILE_TABLET,
    NormalizedChoice,
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

AMAZON_SORT_BY = [
    "most-recent",
    "price-low-to-high",
    "price-high-to-low",
    "average-review",
    "bestsellers",
    "featured",
]


@click.command("amazon-product")
@click.argument("asin", required=False)
@optgroup.group("Locale", help="Device, domain, country, language, and currency")
@optgroup.option(
    "--device",
    type=click.Choice(DEVICE_DESKTOP_MOBILE_TABLET, case_sensitive=False),
    default=None,
    help="Device: desktop, mobile, or tablet.",
)
@optgroup.option(
    "--domain", type=str, default=None, help="Amazon domain (e.g. com, co.uk, de, fr)."
)
@optgroup.option("--country", type=str, default=None, help="Country code (e.g. us, gb, de).")
@optgroup.option(
    "--zip-code", type=str, default=None, help="ZIP code for local availability/pricing."
)
@optgroup.option(
    "--language", type=str, default=None, help="Language code (e.g. en_US, es_US, fr_FR)."
)
@optgroup.option("--currency", type=str, default=None, help="Currency code (e.g. USD, EUR, GBP).")
@optgroup.group("Output", help="Response format options")
@optgroup.option(
    "--add-html", type=str, default=None, help="Include full HTML in response (true/false)."
)
@optgroup.option("--light-request", type=str, default=None, help="Light request mode (true/false).")
@optgroup.option("--screenshot", type=str, default=None, help="Take screenshot (true/false).")
@_batch_options
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
    **kwargs,
) -> None:
    """Fetch Amazon product details by ASIN."""
    store_common_options(obj, **kwargs)
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

        async def api_call(client, a):
            return await client.amazon_product(
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
        check_api_response(data, status_code)
        from ..credits import amazon_credits

        write_output(
            data,
            headers,
            status_code,
            obj["output_file"],
            obj["verbose"],
            extract_field=obj.get("extract_field"),
            fields=obj.get("fields"),
            command="amazon-product",
            credit_cost=amazon_credits(parse_bool(light_request)),
        )

    asyncio.run(_single())


@click.command("amazon-search")
@click.argument("query", required=False)
@optgroup.group("Pagination & sort", help="Pages and sort order")
@optgroup.option("--start-page", type=int, default=None, help="Starting page number.")
@optgroup.option("--pages", type=int, default=None, help="Number of pages to fetch.")
@optgroup.option(
    "--sort-by",
    type=NormalizedChoice(AMAZON_SORT_BY, case_sensitive=False),
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
@_batch_options
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
    **kwargs,
) -> None:
    """Search Amazon products."""
    store_common_options(obj, **kwargs)
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
            return await client.amazon_search(
                q,
                start_page=start_page,
                pages=pages,
                sort_by=norm_val(sort_by),
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
            data, headers, status_code = await client.amazon_search(
                query,
                start_page=start_page,
                pages=pages,
                sort_by=norm_val(sort_by),
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
        check_api_response(data, status_code)
        from ..credits import amazon_credits

        write_output(
            data,
            headers,
            status_code,
            obj["output_file"],
            obj["verbose"],
            extract_field=obj.get("extract_field"),
            fields=obj.get("fields"),
            command="amazon-search",
            credit_cost=amazon_credits(parse_bool(light_request)),
        )

    asyncio.run(_single())


def register(cli: click.Group) -> None:
    cli.add_command(amazon_product_cmd, "amazon-product")
    cli.add_command(amazon_search_cmd, "amazon-search")
