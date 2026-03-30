"""Scrape command (single URL and batch)."""

from __future__ import annotations

import asyncio
import json
import os

import click
from click_option_group import optgroup

from ..batch import (
    _find_completed_n,
    extension_for_crawl,
    get_batch_usage,
    read_input_file,
    resolve_batch_concurrency,
    run_batch_async,
    validate_batch_run,
    write_batch_output_to_dir,
)
from ..cli_utils import (
    CLIENT_TIMEOUT_BUFFER_SECONDS,
    DEFAULT_CLIENT_TIMEOUT_SECONDS,
    DEVICE_DESKTOP_MOBILE,
    WAIT_BROWSER_HELP,
    _batch_options,
    _validate_json_option,
    _validate_range,
    build_scrape_kwargs,
    chunk_text,
    parse_bool,
    prepare_batch_inputs,
    scrape_with_escalation,
    store_common_options,
    write_output,
)
from ..client import Client, pretty_json
from ..config import BASE_URL, get_api_key
from ..crawl import _preferred_extension_from_scrape_params


def _apply_chunking(url: str, data: bytes, chunk_size: int, chunk_overlap: int) -> bytes:
    """Split text/markdown content into NDJSON chunks for LLM/vector DB pipelines."""
    import json as _json
    from datetime import datetime, timezone

    text = data.decode("utf-8", errors="replace")
    chunks = chunk_text(text, chunk_size, chunk_overlap)
    total = len(chunks)
    fetched_at = datetime.now(timezone.utc).isoformat()
    lines = [
        _json.dumps(
            {
                "url": url,
                "chunk_index": i,
                "total_chunks": total,
                "content": c,
                "fetched_at": fetched_at,
            },
            ensure_ascii=False,
        )
        for i, c in enumerate(chunks)
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


SCRAPE_PRESETS = (
    "screenshot",
    "screenshot-and-html",
    "fetch",
    "extract-links",
    "extract-emails",
    "extract-phones",
    "scroll-page",
)


@click.command()
@click.argument("url", required=False)
@click.option(
    "--preset",
    type=click.Choice(SCRAPE_PRESETS, case_sensitive=False),
    default=None,
    help="Apply a predefined set of options. Preset only sets options you did not set. See --help for list.",
)
@click.option(
    "--scraping-config",
    type=str,
    default=None,
    help="Apply a pre-saved scraping configuration by name. Create configs in the ScrapingBee dashboard. Inline options override config settings.",
)
@click.option(
    "--force-extension",
    type=str,
    default=None,
    help="Force output file extension (e.g. html, json). Skips inference when --output-file has no extension.",
)
@optgroup.group("Rendering", help="JavaScript rendering and viewport options")
@optgroup.option(
    "--render-js",
    type=str,
    default=None,
    help="Enable/disable JS rendering (true/false). When omitted, parameter is not sent (API default may apply). Set true for headless browser.",
)
@optgroup.option(
    "--js-scenario",
    type=str,
    default=None,
    help="JSON JavaScript scenario (e.g. click, wait, scroll). Stringify before passing.",
)
@optgroup.option(
    "--wait", type=int, default=None, help="Wait time in ms (0-35000) before returning HTML."
)
@optgroup.option(
    "--wait-for", type=str, default=None, help="CSS or XPath selector to wait for before returning."
)
@optgroup.option("--wait-browser", type=str, default=None, help=WAIT_BROWSER_HELP)
@optgroup.option(
    "--block-ads",
    type=str,
    default=None,
    help="Block ads (true/false). Unnecessary if render_js=false.",
)
@optgroup.option(
    "--block-resources",
    type=str,
    default=None,
    help="Block images and CSS (true/false). Default blocks for speed.",
)
@optgroup.option(
    "--window-width",
    type=int,
    default=None,
    help="Viewport width in pixels. Only with render_js=true.",
)
@optgroup.option(
    "--window-height",
    type=int,
    default=None,
    help="Viewport height in pixels. Only with render_js=true.",
)
@optgroup.group("Proxy", help="Proxy and geo options")
@optgroup.option(
    "--premium-proxy",
    type=str,
    default=None,
    help="Use premium/residential proxies (true/false). Default: false. 25 credits per request with JS.",
)
@optgroup.option(
    "--stealth-proxy",
    type=str,
    default=None,
    help="Use stealth proxies for hard-to-scrape sites (true/false). Default: false. 75 credits per request.",
)
@optgroup.option(
    "--country-code",
    type=str,
    default=None,
    help="Proxy country code (ISO 3166-1, e.g. us, de, gb).",
)
@optgroup.option(
    "--own-proxy",
    type=str,
    default=None,
    help="Your proxy: user:pass@host:port (protocol optional).",
)
@optgroup.group("Headers", help="Custom and forwarded headers")
@optgroup.option("-H", "--header", "headers", multiple=True, help="Custom header Key:Value")
@optgroup.option(
    "--forward-headers",
    type=str,
    default=None,
    help="Forward custom headers to target (true/false). Use -H with Spb- prefix for GET.",
)
@optgroup.option(
    "--forward-headers-pure",
    type=str,
    default=None,
    help="Forward only custom headers, no ScrapingBee headers (true/false).",
)
@optgroup.group("Output", help="Response format and chunking")
@optgroup.option(
    "--json-response",
    type=str,
    default=None,
    help="Wrap response in JSON (use with --screenshot to get both HTML and image in one response)",
)
@optgroup.option(
    "--chunk-size",
    "chunk_size",
    type=int,
    default=0,
    help="Split text/markdown output into chunks of N chars for LLM/vector DB pipelines (0 = disabled). Outputs NDJSON.",
)
@optgroup.option(
    "--chunk-overlap",
    "chunk_overlap",
    type=int,
    default=0,
    help="Overlap chars between consecutive chunks (default 0). Only used when --chunk-size > 0.",
)
@optgroup.option(
    "--return-page-source",
    type=str,
    default=None,
    help="Return unaltered HTML from server. Value: true or false (e.g. --return-page-source true). Unnecessary if render_js=false.",
)
@optgroup.option(
    "--return-page-markdown",
    "return_page_markdown",
    type=str,
    default=None,
    help="Return main content as markdown. Value: true or false (e.g. --return-page-markdown true).",
)
@optgroup.option(
    "--return-page-text",
    "return_page_text",
    type=str,
    default=None,
    help="Return main content as plain text. Value: true or false (e.g. --return-page-text true).",
)
@optgroup.group("Screenshot", help="Screenshot capture options")
@optgroup.option(
    "--screenshot",
    type=str,
    default=None,
    help="Capture a screenshot (viewport or use selector/full-page)",
)
@optgroup.option(
    "--screenshot-selector",
    type=str,
    default=None,
    help="CSS selector for screenshot area (cannot be combined with --screenshot-full-page)",
)
@optgroup.option(
    "--screenshot-full-page",
    type=str,
    default=None,
    help="Capture full page screenshot (cannot be combined with --screenshot-selector)",
)
@optgroup.group("Extraction", help="CSS/XPath and AI extraction (+5 credits for AI)")
@optgroup.option(
    "--extract-rules",
    type=str,
    default=None,
    help='CSS/XPath extraction rules as JSON string (e.g. {"title": "h1"}).',
)
@optgroup.option(
    "--ai-query",
    type=str,
    default=None,
    help='Natural language extraction (e.g. "price of the product"). +5 credits.',
)
@optgroup.option(
    "--ai-selector",
    type=str,
    default=None,
    help="CSS selector to focus AI extraction (optional). Speeds up request.",
)
@optgroup.option(
    "--ai-extract-rules",
    type=str,
    default=None,
    help="AI extraction rules as JSON (key: description). +5 credits.",
)
@optgroup.group("Request", help="Session, timeout, cookies, method, and body")
@optgroup.option(
    "--session-id",
    type=int,
    default=None,
    help="Session ID for sticky IP (0-10000000). Same IP for 5 minutes.",
)
@optgroup.option("--timeout", type=int, default=None, help="Timeout in ms (1000-140000).")
@optgroup.option(
    "--cookies", type=str, default=None, help="Custom cookies: name=value,domain=...;name2=value2"
)
@optgroup.option(
    "--device",
    type=click.Choice(DEVICE_DESKTOP_MOBILE, case_sensitive=False),
    default=None,
    help="Device type: desktop or mobile.",
)
@optgroup.option(
    "--custom-google",
    type=str,
    default=None,
    help="Scrape Google domains (true/false). 15 credits.",
)
@optgroup.option(
    "--transparent-status-code",
    type=str,
    default=None,
    help="Return target status/body as-is (true/false). No retry on 500.",
)
@optgroup.option(
    "-X",
    "--method",
    type=click.Choice(["GET", "POST", "PUT"], case_sensitive=False),
    default="GET",
    help="HTTP method: GET, POST, or PUT.",
)
@optgroup.option("-d", "--data", "body", type=str, default=None, help="Request body for POST/PUT.")
@click.option(
    "--escalate-proxy",
    "escalate_proxy",
    is_flag=True,
    default=False,
    help="On 403/429, auto-retry with premium then stealth proxy. Off by default.",
)
@_batch_options
@click.pass_obj
def scrape_cmd(
    obj: dict,
    url: str | None,
    preset: str | None,
    scraping_config: str | None,
    force_extension: str | None,
    render_js: str | None,
    js_scenario: str | None,
    wait: int | None,
    wait_for: str | None,
    wait_browser: str | None,
    block_ads: str | None,
    block_resources: str | None,
    window_width: int | None,
    window_height: int | None,
    premium_proxy: str | None,
    stealth_proxy: str | None,
    country_code: str | None,
    own_proxy: str | None,
    forward_headers: str | None,
    forward_headers_pure: str | None,
    headers: tuple[str, ...],
    json_response: str | None,
    chunk_size: int,
    chunk_overlap: int,
    screenshot: str | None,
    screenshot_selector: str | None,
    screenshot_full_page: str | None,
    return_page_source: str | None,
    return_page_markdown: str | None,
    return_page_text: str | None,
    extract_rules: str | None,
    ai_query: str | None,
    ai_selector: str | None,
    ai_extract_rules: str | None,
    session_id: int | None,
    timeout: int | None,
    cookies: str | None,
    device: str | None,
    custom_google: str | None,
    transparent_status_code: str | None,
    method: str,
    body: str | None,
    escalate_proxy: bool,
    **kwargs,
) -> None:
    """Scrape a web page using the HTML API.

    Usage: scrapingbee scrape [URL] [OPTIONS].     Use --output-file FILE (before or after command) to save output. For batch,
    use global --input-file with one URL per line (before or after command). Use --preset for common option sets
    (e.g. screenshot-and-html, fetch, extract-links, scroll-page). Default response
    is raw HTML (or image if screenshot).
    Use --json-response true to wrap body, headers, and cost in JSON (required when
    combining --screenshot with extraction). See documentation for full parameter list.
    """
    store_common_options(obj, **kwargs)
    input_file = obj.get("input_file")
    if not input_file and not url:
        click.echo("expected one URL argument, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    if url:
        from ..cli_utils import ensure_url_scheme

        url = ensure_url_scheme(url)

    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if preset:
        preset_lower = preset.lower()
        if preset_lower == "screenshot":
            screenshot = screenshot or "true"
            render_js = render_js or "true"
        elif preset_lower == "screenshot-and-html":
            json_response = json_response or "true"
            screenshot = screenshot or "true"
            screenshot_full_page = screenshot_full_page or "true"
            render_js = render_js or "true"
        elif preset_lower == "fetch":
            render_js = render_js or "false"
        elif preset_lower == "extract-links":
            extract_rules = (
                extract_rules or '{"links":{"selector":"a","type":"list","output":"@href"}}'
            )
            # No json_response: API returns raw body = extracted JSON only
        elif preset_lower == "extract-emails":
            extract_rules = extract_rules or json.dumps(
                {
                    "emails": {"selector": 'a[href^="mailto:"]', "output": "@href", "type": "list"},
                }
            )
            # No json_response: API returns raw body = extracted JSON only
        elif preset_lower == "extract-phones":
            extract_rules = extract_rules or json.dumps(
                {
                    "phones": {"selector": 'a[href^="tel:"]', "output": "@href", "type": "list"},
                }
            )
            # No json_response: API returns raw body = extracted JSON only
        elif preset_lower == "scroll-page":
            js_scenario = (
                js_scenario or '{"instructions":[{"infinite_scroll":{"max_count":0,"delay":1000}}]}'
            )
            render_js = render_js or "true"

    try:
        _validate_json_option("--js-scenario", js_scenario)
        _validate_json_option("--extract-rules", extract_rules)

        custom_headers = {}
        for h in headers:
            if ":" not in h:
                click.echo(f'Invalid header format "{h}", expected Key:Value', err=True)
                raise SystemExit(1)
            k, v = h.split(":", 1)
            custom_headers[k.strip()] = v.strip()

        if parse_bool(screenshot) and screenshot_selector and parse_bool(screenshot_full_page):
            click.echo(
                "Cannot use both --screenshot-selector and --screenshot-full-page; choose one.",
                err=True,
            )
            raise SystemExit(1)

        scrape_kwargs = build_scrape_kwargs(
            method=method,
            render_js=render_js,
            js_scenario=js_scenario,
            wait=wait,
            wait_for=wait_for,
            wait_browser=wait_browser,
            block_ads=block_ads,
            block_resources=block_resources,
            window_width=window_width,
            window_height=window_height,
            premium_proxy=premium_proxy,
            stealth_proxy=stealth_proxy,
            country_code=country_code,
            own_proxy=own_proxy,
            forward_headers=forward_headers,
            forward_headers_pure=forward_headers_pure,
            custom_headers=custom_headers or None,
            json_response=json_response,
            screenshot=screenshot,
            screenshot_selector=screenshot_selector,
            screenshot_full_page=screenshot_full_page,
            return_page_source=return_page_source,
            return_page_markdown=return_page_markdown,
            return_page_text=return_page_text,
            extract_rules=extract_rules,
            ai_query=ai_query,
            ai_selector=ai_selector,
            ai_extract_rules=ai_extract_rules,
            session_id=session_id,
            timeout=timeout,
            cookies=cookies,
            device=device,
            custom_google=custom_google,
            transparent_status_code=transparent_status_code,
            body=body,
            scraping_config=scraping_config,
        )
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    scrape_kwargs["retries"] = obj.get("retries", 3) or 3
    scrape_kwargs["backoff"] = obj.get("backoff", 2.0) or 2.0

    _validate_range("session_id", session_id, 0, 10_000_000)
    _validate_range("timeout", timeout, 1000, 140_000, "ms")
    _validate_range("wait", wait, 0, 35_000, "ms")

    client_timeout = (
        (timeout // 1000) + CLIENT_TIMEOUT_BUFFER_SECONDS
        if timeout is not None
        else DEFAULT_CLIENT_TIMEOUT_SECONDS
    )

    if input_file:
        if url:
            click.echo("cannot use both global --input-file and positional URL", err=True)
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

        async def _batch() -> None:
            async with Client(
                key, BASE_URL, connector_limit=concurrency, timeout=client_timeout
            ) as client:

                async def do_one(u: str):
                    try:
                        if escalate_proxy:
                            data, resp_headers, status_code = await scrape_with_escalation(
                                client,
                                u,
                                scrape_kwargs,
                                verbose=obj["verbose"],
                            )
                        else:
                            data, resp_headers, status_code = await client.scrape(
                                u, **scrape_kwargs
                            )
                        if not scrape_kwargs.get("transparent_status_code") and status_code >= 400:
                            return (
                                data,
                                resp_headers,
                                status_code,
                                RuntimeError(f"HTTP {status_code}"),
                                None,
                            )
                        if chunk_size > 0:
                            data = _apply_chunking(u, data, chunk_size, chunk_overlap)
                            return data, resp_headers, status_code, None, "ndjson"
                        return data, resp_headers, status_code, None, None
                    except Exception as e:
                        return b"", {}, 0, e, None

                output_format = obj.get("output_format", "files")
                post_process = obj.get("post_process")

                ndjson_pp = post_process if output_format == "ndjson" else None

                def _ndjson_cb(result):
                    from ..batch import apply_post_process, write_ndjson_line

                    if ndjson_pp and result.body and not result.error:
                        from ..batch import BatchResult

                        body = apply_post_process(result.body, ndjson_pp)
                        result = BatchResult(
                            index=result.index,
                            input=result.input,
                            body=body,
                            headers=result.headers,
                            status_code=result.status_code,
                            error=result.error,
                            expected_extension=result.expected_extension,
                            skipped=result.skipped,
                            fetched_at=result.fetched_at,
                            latency_ms=result.latency_ms,
                        )
                    write_ndjson_line(result)

                on_result_cb = _ndjson_cb if output_format == "ndjson" else None
                results = await run_batch_async(
                    inputs,
                    concurrency,
                    do_one,
                    from_user=obj["concurrency"] > 0,
                    skip_n=skip_n,
                    show_progress=obj.get("progress", True),
                    on_result=on_result_cb,
                )

            if output_format == "ndjson":
                succeeded = sum(1 for r in results if not r.error and not r.skipped)
                failed = sum(1 for r in results if r.error and not r.skipped)
                click.echo(f"Batch complete: {succeeded} succeeded, {failed} failed.", err=True)
            elif output_format == "csv":
                from ..batch import apply_post_process, write_batch_output_csv

                if post_process:
                    for r in results:
                        if r.body and not r.error and not r.skipped:
                            r.body = apply_post_process(r.body, post_process)
                out_path, succeeded, failed = write_batch_output_csv(
                    results,
                    obj.get("output_dir") or None,
                )
                click.echo(
                    f"Batch complete: {succeeded} succeeded, {failed} failed. Output: {out_path}",
                )
            elif obj.get("update_csv") and input_file:
                from ..batch import update_csv_with_results

                out_path, succeeded, failed = update_csv_with_results(
                    input_file,
                    obj.get("input_column"),
                    results,
                    obj.get("output_dir") or None,
                )
                click.echo(
                    f"CSV updated: {succeeded} succeeded, {failed} failed. Output: {out_path}",
                )
            else:
                out_dir, succeeded, failed = write_batch_output_to_dir(
                    results,
                    obj.get("output_dir") or None,
                    obj["verbose"],
                    post_process=post_process,
                )
                click.echo(
                    f"Batch complete: {succeeded} succeeded, {failed} failed. Output: {out_dir}",
                )
                on_complete = obj.get("on_complete")
                if on_complete:
                    from ..cli_utils import run_on_complete

                    run_on_complete(
                        on_complete, output_dir=out_dir, succeeded=succeeded, failed=failed
                    )
            if failed:
                raise SystemExit(1)

        asyncio.run(_batch())
        return

    if not url:
        click.echo("expected one URL argument, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL, timeout=client_timeout) as client:
            if escalate_proxy:
                data, resp_headers, status_code = await scrape_with_escalation(
                    client,
                    url,
                    scrape_kwargs,
                    verbose=obj["verbose"],
                )
            else:
                data, resp_headers, status_code = await client.scrape(url, **scrape_kwargs)
        if not scrape_kwargs.get("transparent_status_code") and status_code >= 400:
            click.echo(f"Error: HTTP {status_code}", err=True)
            try:
                click.echo(pretty_json(data), err=True)
            except Exception:
                click.echo(data.decode("utf-8", errors="replace"), err=True)
            raise SystemExit(1)
        if chunk_size > 0:
            data = _apply_chunking(url, data, chunk_size, chunk_overlap)
            # Force .ndjson extension when chunking
            output_path = obj["output_file"]
            if output_path and "." not in os.path.basename(output_path):
                output_path = output_path.rstrip("/") + ".ndjson"
            write_output(data, resp_headers, status_code, output_path, obj["verbose"])
            return
        output_path = obj["output_file"]
        if output_path:
            if force_extension:
                if "." not in os.path.basename(output_path):
                    output_path = output_path.rstrip("/") + "." + force_extension.lstrip(".")
            else:
                preferred = _preferred_extension_from_scrape_params(scrape_kwargs)
                ext = extension_for_crawl(url, resp_headers, data, preferred)
                if "." not in os.path.basename(output_path):
                    output_path = output_path.rstrip("/") + "." + ext
        write_output(
            data,
            resp_headers,
            status_code,
            output_path,
            obj["verbose"],
            extract_field=obj.get("extract_field"),
            fields=obj.get("fields"),
        )

    asyncio.run(_single())


def register(cli: click.Group) -> None:
    cli.add_command(scrape_cmd, "scrape")
