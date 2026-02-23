"""Walmart search and product commands."""

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
from ..cli_utils import (
    DEVICE_DESKTOP_MOBILE_TABLET,
    _validate_price_range,
    parse_bool,
    write_output,
)

WALMART_SORT_BY = ["best_match", "price_low", "price_high", "best_seller"]


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
    help="Fulfillment: today, tomorrow, 2_days, anytime.",
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
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(None)
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(q: str):
                    try:
                        data, headers, status_code = await client.walmart_search(
                            q,
                            min_price=min_price,
                            max_price=max_price,
                            sort_by=sort_by,
                            device=device,
                            domain=domain,
                            fulfillment_speed=fulfillment_speed,
                            fulfillment_type=fulfillment_type,
                            delivery_zip=delivery_zip,
                            store_id=store_id,
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
            data, headers, status_code = await client.walmart_search(
                query,
                min_price=min_price,
                max_price=max_price,
                sort_by=sort_by,
                device=device,
                domain=domain,
                fulfillment_speed=fulfillment_speed,
                fulfillment_type=fulfillment_type,
                delivery_zip=delivery_zip,
                store_id=store_id,
                add_html=parse_bool(add_html),
                light_request=parse_bool(light_request),
                screenshot=parse_bool(screenshot),
                retries=obj.get("retries", 3) or 3,
                backoff=obj.get("backoff", 2.0) or 2.0,
            )
        write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

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
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(None)
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(pid: str):
                    try:
                        data, headers, status_code = await client.walmart_product(
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
        write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


def register(cli):  # noqa: ANN001
    cli.add_command(walmart_search_cmd, "walmart-search")
    cli.add_command(walmart_product_cmd, "walmart-product")
