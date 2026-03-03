"""Walmart search and product commands."""

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
    _validate_price_range,
    check_api_response,
    norm_val,
    parse_bool,
    write_output,
)
from ..client import Client
from ..config import BASE_URL, get_api_key

WALMART_SORT_BY = ["best-match", "price-low", "price-high", "best-seller"]


@click.command("walmart-search")
@click.argument("query", required=False)
@optgroup.group("Filters", help="Price and sort")
@optgroup.option("--min-price", type=int, default=None, help="Minimum price filter (integer).")
@optgroup.option("--max-price", type=int, default=None, help="Maximum price filter (integer).")
@optgroup.option(
    "--sort-by",
    type=click.Choice(WALMART_SORT_BY, case_sensitive=False),
    default=None,
    help="Sort order.",
)
@optgroup.group("Device & delivery", help="Device, domain, fulfillment")
@optgroup.option(
    "--device",
    type=click.Choice(DEVICE_DESKTOP_MOBILE_TABLET, case_sensitive=False),
    default=None,
    help="Device: desktop, mobile, or tablet.",
)
@optgroup.option("--domain", type=str, default=None, help="Walmart domain.")
@optgroup.option(
    "--fulfillment-speed",
    type=str,
    default=None,
    help="Fulfillment: today, tomorrow, 2-days, anytime.",
)
@optgroup.option(
    "--fulfillment-type",
    type=str,
    default=None,
    help="Fulfillment type (e.g. in_store for pickup).",
)
@optgroup.option("--delivery-zip", type=str, default=None, help="Delivery ZIP code.")
@optgroup.option("--store-id", type=str, default=None, help="Walmart store ID.")
@optgroup.group("Output", help="Response format")
@optgroup.option("--add-html", type=str, default=None, help="Include full HTML (true/false).")
@optgroup.option("--light-request", type=str, default=None, help="Light request (true/false).")
@optgroup.option("--screenshot", type=str, default=None, help="Take screenshot (true/false).")
@click.pass_obj
def walmart_search_cmd(
    obj: dict,
    query: str | None,
    min_price: int | None,
    max_price: int | None,
    sort_by: str | None,
    device: str | None,
    domain: str | None,
    fulfillment_speed: str | None,
    fulfillment_type: str | None,
    delivery_zip: str | None,
    store_id: str | None,
    add_html: str | None,
    light_request: str | None,
    screenshot: str | None,
) -> None:
    """Search Walmart products."""
    input_file = obj.get("input_file")
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
    _validate_price_range(min_price, max_price)

    if input_file:
        if query:
            click.echo("cannot use both global --input-file and positional query", err=True)
            raise SystemExit(1)
        try:
            inputs = read_input_file(input_file)
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
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
            return await client.walmart_search(
                q,
                min_price=min_price,
                max_price=max_price,
                sort_by=norm_val(sort_by),
                device=device,
                domain=domain,
                fulfillment_speed=norm_val(fulfillment_speed),
                fulfillment_type=norm_val(fulfillment_type),
                delivery_zip=delivery_zip,
                store_id=store_id,
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
            diff_dir=obj.get("diff_dir"),
        )
        return

    if not query:
        click.echo("expected one search query, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.walmart_search(
                query,
                min_price=min_price,
                max_price=max_price,
                sort_by=norm_val(sort_by),
                device=device,
                domain=domain,
                fulfillment_speed=norm_val(fulfillment_speed),
                fulfillment_type=norm_val(fulfillment_type),
                delivery_zip=delivery_zip,
                store_id=store_id,
                add_html=parse_bool(add_html),
                light_request=parse_bool(light_request),
                screenshot=parse_bool(screenshot),
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
            command="walmart-search",
        )

    asyncio.run(_single())


@click.command("walmart-product")
@click.argument("product_id", required=False)
@click.option("--domain", type=str, default=None, help="Walmart domain.")
@click.option("--delivery-zip", type=str, default=None, help="Delivery ZIP code.")
@click.option("--store-id", type=str, default=None, help="Walmart store ID.")
@click.option("--add-html", type=str, default=None, help="Include full HTML (true/false).")
@click.option("--light-request", type=str, default=None, help="Light request (true/false).")
@click.option("--screenshot", type=str, default=None, help="Take screenshot (true/false).")
@click.pass_obj
def walmart_product_cmd(
    obj: dict,
    product_id: str | None,
    domain: str | None,
    delivery_zip: str | None,
    store_id: str | None,
    add_html: str | None,
    light_request: str | None,
    screenshot: str | None,
) -> None:
    """Fetch Walmart product details by product ID."""
    input_file = obj.get("input_file")
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if product_id:
            click.echo("cannot use both global --input-file and positional product-id", err=True)
            raise SystemExit(1)
        try:
            inputs = read_input_file(input_file)
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
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

        async def api_call(client, pid):
            return await client.walmart_product(
                pid,
                domain=domain,
                delivery_zip=delivery_zip,
                store_id=store_id,
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
            diff_dir=obj.get("diff_dir"),
        )
        return

    if not product_id:
        click.echo("expected one product ID, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.walmart_product(
                product_id,
                domain=domain,
                delivery_zip=delivery_zip,
                store_id=store_id,
                add_html=parse_bool(add_html),
                light_request=parse_bool(light_request),
                screenshot=parse_bool(screenshot),
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
            command="walmart-product",
        )

    asyncio.run(_single())


def register(cli: click.Group) -> None:
    cli.add_command(walmart_search_cmd, "walmart-search")
    cli.add_command(walmart_product_cmd, "walmart-product")
