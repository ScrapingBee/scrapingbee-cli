"""ScrapingBee CLI - click entrypoint and commands."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import click

from . import __version__
from .crawl import (
    default_crawl_output_dir,
    _preferred_extension_from_scrape_params,
    run_project_spider,
    run_urls_spider,
)
from .batch import (
    extension_for_crawl,
    get_batch_usage,
    read_input_file,
    resolve_batch_concurrency,
    run_batch_async,
    validate_batch_run,
    write_batch_output_to_dir,
)
from .client import Client, pretty_json
from .config import BASE_URL, get_api_key


def _parse_bool(val: str | None) -> bool | None:
    if not val:
        return None
    return val.lower() in ("true", "1", "yes")


def _build_scrape_kwargs(
    *,
    method: str = "GET",
    render_js: str | None = None,
    js_scenario: str | None = None,
    wait: int | None = None,
    wait_for: str | None = None,
    wait_browser: str | None = None,
    block_ads: str | None = None,
    block_resources: str | None = None,
    window_width: int | None = None,
    window_height: int | None = None,
    premium_proxy: str | None = None,
    stealth_proxy: str | None = None,
    country_code: str | None = None,
    own_proxy: str | None = None,
    forward_headers: str | None = None,
    forward_headers_pure: str | None = None,
    custom_headers: dict[str, str] | None = None,
    json_response: str | None = None,
    screenshot: str | None = None,
    screenshot_selector: str | None = None,
    screenshot_full_page: str | None = None,
    return_page_source: str | None = None,
    return_markdown: str | None = None,
    return_text: str | None = None,
    extract_rules: str | None = None,
    ai_query: str | None = None,
    ai_selector: str | None = None,
    ai_extract_rules: str | None = None,
    session_id: int | None = None,
    timeout: int | None = None,
    cookies: str | None = None,
    device: str | None = None,
    custom_google: str | None = None,
    transparent_status_code: str | None = None,
    scraping_config: str | None = None,
    body: str | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    """Build kwargs for Client.scrape() from scrape command options. Single source of _parse_bool for bool-like opts."""
    return {
        "method": method,
        "render_js": _parse_bool(render_js),
        "js_scenario": js_scenario,
        "wait": wait,
        "wait_for": wait_for,
        "wait_browser": wait_browser,
        "block_ads": _parse_bool(block_ads),
        "block_resources": _parse_bool(block_resources),
        "window_width": window_width,
        "window_height": window_height,
        "premium_proxy": _parse_bool(premium_proxy),
        "stealth_proxy": _parse_bool(stealth_proxy),
        "country_code": country_code,
        "own_proxy": own_proxy,
        "forward_headers": _parse_bool(forward_headers),
        "forward_headers_pure": _parse_bool(forward_headers_pure),
        "custom_headers": custom_headers,
        "json_response": _parse_bool(json_response),
        "screenshot": _parse_bool(screenshot),
        "screenshot_selector": screenshot_selector,
        "screenshot_full_page": _parse_bool(screenshot_full_page),
        "return_page_source": _parse_bool(return_page_source),
        "return_page_markdown": _parse_bool(return_markdown),
        "return_page_text": _parse_bool(return_text),
        "extract_rules": extract_rules,
        "ai_query": ai_query,
        "ai_selector": ai_selector,
        "ai_extract_rules": ai_extract_rules,
        "session_id": session_id,
        "timeout": timeout,
        "cookies": cookies,
        "device": device,
        "custom_google": _parse_bool(custom_google),
        "transparent_status_code": _parse_bool(transparent_status_code),
        "scraping_config": scraping_config,
        "body": body,
        "content_type": content_type,
    }


def _scrape_kwargs_to_api_params(kwargs: dict[str, Any]) -> dict[str, str]:
    """Convert _build_scrape_kwargs output to ScrapingBee API params dict (str values; omit None/empty)."""
    skip_keys = frozenset(("method", "body", "content_type", "custom_headers"))
    out: dict[str, str] = {}
    for k, v in kwargs.items():
        if k in skip_keys or v is None or v == "":
            continue
        if isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, int):
            out[k] = str(v)
        elif isinstance(v, str):
            out[k] = v
    return out


def _check_api_response(data: bytes, status_code: int, err_prefix: str = "Error") -> None:
    """Exit with 1 on HTTP 4xx/5xx (per ScrapingBee docs).
    No special cases except scrape+transparent_status_code."""
    if status_code >= 400:
        click.echo(f"{err_prefix}: HTTP {status_code}", err=True)
        try:
            click.echo(pretty_json(data), err=True)
        except Exception:
            click.echo(data.decode("utf-8", errors="replace"), err=True)
        raise SystemExit(1)


def _write_output(
    data: bytes,
    headers: dict,
    status_code: int,
    output_path: str | None,
    verbose: bool,
) -> None:
    if verbose:
        click.echo(f"HTTP Status: {status_code}", err=True)
        headers_lower = {k.lower(): (k, v) for k, v in headers.items()}
        for key, label in [
            ("spb-cost", "Credit Cost"),
            ("spb-resolved-url", "Resolved URL"),
            ("spb-initial-status-code", "Initial Status Code"),
        ]:
            if key in headers_lower:
                _, val = headers_lower[key]
                if val:
                    click.echo(f"{label}: {val}", err=True)
        click.echo("---", err=True)
    if output_path:
        with open(output_path, "wb") as f:
            f.write(data)
    else:
        sys.stdout.buffer.write(data)
        if not data.endswith(b"\n"):
            click.echo()


# --- Global options (stored in context.obj) ---
def _global_options(f: Any) -> Any:
    f = click.option(
        "--api-key",
        envvar="SCRAPINGBEE_API_KEY",
        default=None,
        help="ScrapingBee API key (or set SCRAPINGBEE_API_KEY)",
    )(f)
    f = click.option(
        "-o",
        "--output",
        "output_file",
        type=click.Path(),
        default=None,
        help="Write output to file instead of stdout",
    )(f)
    f = click.option(
        "-v",
        "--verbose",
        is_flag=True,
        default=False,
        help="Show response headers and status code",
    )(f)
    f = click.option(
        "--batch-output-dir",
        default=None,
        help="Batch mode: folder for output files (default: batch_<timestamp>)",
    )(f)
    f = click.option(
        "--concurrency",
        type=int,
        default=0,
        help="Batch mode: max concurrent requests (0 = use limit from usage API)",
    )(f)
    return f


@click.group()
@click.version_option(version=__version__)
@_global_options
@click.pass_context
def cli(
    ctx: click.Context,
    api_key: str | None,
    output_file: str | None,
    verbose: bool,
    batch_output_dir: str | None,
    concurrency: int,
) -> None:
    """ScrapingBee CLI - Web scraping API client.

    Commands: scrape (single or batch), crawl (Scrapy/quick-crawl), usage,
    Google Search, Fast Search, Amazon, Walmart, YouTube, and ChatGPT.

    Set your API key via --api-key or SCRAPINGBEE_API_KEY.
    """
    ctx.ensure_object(dict)
    ctx.obj["api_key"] = api_key
    ctx.obj["output_file"] = output_file
    ctx.obj["verbose"] = verbose
    ctx.obj["batch_output_dir"] = batch_output_dir or ""
    ctx.obj["concurrency"] = concurrency or 0


# --- usage ---
@cli.command()
@click.pass_obj
def usage(obj: dict) -> None:
    """Check API credit usage and concurrency."""

    async def _run() -> None:
        async with Client(key, BASE_URL) as client:
            data, _, status_code = await client.usage()
            if status_code != 200:
                click.echo(f"API returned status {status_code}: {data.decode()}", err=True)
                raise SystemExit(1)
            click.echo(pretty_json(data))

    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
    asyncio.run(_run())


# --- scrape ---
@cli.command()
@click.argument("url", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one URL per line")
@click.option("--render-js", type=str, default=None)
@click.option("--js-scenario", type=str, default=None)
@click.option("--wait", type=int, default=None)
@click.option("--wait-for", type=str, default=None)
@click.option("--wait-browser", type=str, default=None)
@click.option("--block-ads", type=str, default=None)
@click.option("--block-resources", type=str, default=None)
@click.option("--window-width", type=int, default=None)
@click.option("--window-height", type=int, default=None)
@click.option("--premium-proxy", type=str, default=None)
@click.option("--stealth-proxy", type=str, default=None)
@click.option("--country-code", type=str, default=None)
@click.option("--own-proxy", type=str, default=None)
@click.option("--forward-headers", type=str, default=None)
@click.option("--forward-headers-pure", type=str, default=None)
@click.option("-H", "--header", "headers", multiple=True, help="Custom header Key:Value")
@click.option(
    "--json-response",
    type=str,
    default=None,
    help="Wrap response in JSON (use with --screenshot to get both HTML and image in one response)",
)
@click.option(
    "--screenshot",
    type=str,
    default=None,
    help="Capture a screenshot (viewport or use selector/full-page)",
)
@click.option(
    "--screenshot-selector",
    type=str,
    default=None,
    help="CSS selector for screenshot area (cannot be combined with --screenshot-full-page)",
)
@click.option(
    "--screenshot-full-page",
    type=str,
    default=None,
    help="Capture full page screenshot (cannot be combined with --screenshot-selector)",
)
@click.option("--return-page-source", type=str, default=None)
@click.option("--return-markdown", type=str, default=None)
@click.option("--return-text", type=str, default=None)
@click.option("--extract-rules", type=str, default=None)
@click.option("--ai-query", type=str, default=None)
@click.option("--ai-selector", type=str, default=None)
@click.option("--ai-extract-rules", type=str, default=None)
@click.option("--session-id", type=int, default=None)
@click.option("--timeout", type=int, default=None)
@click.option("--cookies", type=str, default=None)
@click.option("--device", type=str, default=None)
@click.option("--custom-google", type=str, default=None)
@click.option("--transparent-status-code", type=str, default=None)
@click.option("--scraping-config", type=str, default=None)
@click.option("-X", "--method", type=str, default="GET")
@click.option("-d", "--data", "body", type=str, default=None)
@click.option("--content-type", type=str, default=None)
@click.pass_obj
def scrape(
    obj: dict,
    url: str | None,
    input_file: str | None,
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
    screenshot: str | None,
    screenshot_selector: str | None,
    screenshot_full_page: str | None,
    return_page_source: str | None,
    return_markdown: str | None,
    return_text: str | None,
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
    scraping_config: str | None,
    method: str,
    body: str | None,
    content_type: str | None,
) -> None:
    """Scrape a web page using the HTML API."""
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    custom_headers = {}
    for h in headers:
        if ":" not in h:
            click.echo(f'Invalid header format "{h}", expected Key:Value', err=True)
            raise SystemExit(1)
        k, v = h.split(":", 1)
        custom_headers[k.strip()] = v.strip()

    # Screenshot options: selector and full-page are mutually exclusive (per API behavior).
    if _parse_bool(screenshot):
        if screenshot_selector and _parse_bool(screenshot_full_page):
            click.echo(
                "Cannot use both --screenshot-selector and --screenshot-full-page; choose one.",
                err=True,
            )
            raise SystemExit(1)
    elif screenshot_selector or _parse_bool(screenshot_full_page):
        click.echo(
            "Note: --screenshot-selector and --screenshot-full-page have no effect "
            "without --screenshot=true.",
            err=True,
        )

    scrape_kwargs = _build_scrape_kwargs(
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
        return_markdown=return_markdown,
        return_text=return_text,
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
        scraping_config=scraping_config,
        body=body,
        content_type=content_type,
    )

    if input_file:
        if url:
            click.echo("cannot use both --input-file and positional URL", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(u: str):
                    try:
                        data, resp_headers, status_code = await client.scrape(u, **scrape_kwargs)
                        if not scrape_kwargs.get("transparent_status_code") and status_code >= 400:
                            return (
                                data,
                                resp_headers,
                                status_code,
                                RuntimeError(f"HTTP {status_code}"),
                                None,
                            )
                        return data, resp_headers, status_code, None, None
                    except Exception as e:
                        return b"", {}, 0, e, None

                results = await run_batch_async(
                    inputs, concurrency, do_one, from_user=obj["concurrency"] > 0
                )
            out_dir = write_batch_output_to_dir(
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not url:
        click.echo("expected one URL argument, or use --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, resp_headers, status_code = await client.scrape(url, **scrape_kwargs)
        if not scrape_kwargs.get("transparent_status_code") and status_code >= 400:
            click.echo(f"Error: HTTP {status_code}", err=True)
            try:
                click.echo(pretty_json(data), err=True)
            except Exception:
                click.echo(data.decode("utf-8", errors="replace"), err=True)
            raise SystemExit(1)
        output_path = obj["output_file"]
        if output_path:
            # Same extension logic as crawl/batch: preferred → URL path → body/Content-Type
            preferred = _preferred_extension_from_scrape_params(scrape_kwargs)
            ext = extension_for_crawl(url, resp_headers, data, preferred)
            if "." not in os.path.basename(output_path):
                output_path = output_path.rstrip("/") + "." + ext
        _write_output(data, resp_headers, status_code, output_path, obj["verbose"])

    asyncio.run(_single())


# --- crawl ---
def _crawl_build_params(
    *,
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
    json_response: str | None,
    screenshot: str | None,
    screenshot_selector: str | None,
    screenshot_full_page: str | None,
    return_page_source: str | None,
    return_markdown: str | None,
    return_text: str | None,
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
    scraping_config: str | None,
) -> dict[str, str]:
    """Build ScrapingBee API params dict from crawl options (quick-crawl URL mode)."""
    kwargs = _build_scrape_kwargs(
        method="GET",
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
        custom_headers=None,
        json_response=json_response,
        screenshot=screenshot,
        screenshot_selector=screenshot_selector,
        screenshot_full_page=screenshot_full_page,
        return_page_source=return_page_source,
        return_markdown=return_markdown,
        return_text=return_text,
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
        scraping_config=scraping_config,
        body=None,
        content_type=None,
    )
    return _scrape_kwargs_to_api_params(kwargs)


@cli.command()
@click.argument("target", nargs=-1, required=True)
@click.option("--project", "-p", type=click.Path(exists=True, file_okay=False, path_type=str), default=None)
@click.option("--render-js", type=str, default=None)
@click.option("--js-scenario", type=str, default=None)
@click.option("--wait", type=int, default=None)
@click.option("--wait-for", type=str, default=None)
@click.option("--wait-browser", type=str, default=None)
@click.option("--block-ads", type=str, default=None)
@click.option("--block-resources", type=str, default=None)
@click.option("--window-width", type=int, default=None)
@click.option("--window-height", type=int, default=None)
@click.option("--premium-proxy", type=str, default=None)
@click.option("--stealth-proxy", type=str, default=None)
@click.option("--country-code", type=str, default=None)
@click.option("--own-proxy", type=str, default=None)
@click.option("--forward-headers", type=str, default=None)
@click.option("--forward-headers-pure", type=str, default=None)
@click.option("-H", "--header", "headers", multiple=True)
@click.option("--json-response", type=str, default=None)
@click.option("--screenshot", type=str, default=None)
@click.option("--screenshot-selector", type=str, default=None)
@click.option("--screenshot-full-page", type=str, default=None)
@click.option("--return-page-source", type=str, default=None)
@click.option("--return-markdown", type=str, default=None)
@click.option("--return-text", type=str, default=None)
@click.option("--extract-rules", type=str, default=None)
@click.option("--ai-query", type=str, default=None)
@click.option("--ai-selector", type=str, default=None)
@click.option("--ai-extract-rules", type=str, default=None)
@click.option("--session-id", type=int, default=None)
@click.option("--timeout", type=int, default=None)
@click.option("--cookies", type=str, default=None)
@click.option("--device", type=str, default=None)
@click.option("--custom-google", type=str, default=None)
@click.option("--transparent-status-code", type=str, default=None)
@click.option("--scraping-config", type=str, default=None)
@click.option(
    "--max-depth",
    type=int,
    default=0,
    help="Max link depth when following same-domain links (0 = unlimited). Quick-crawl only.",
)
@click.option(
    "--max-pages",
    type=int,
    default=0,
    help="Max number of pages to fetch (0 = unlimited). Quick-crawl only.",
)
@click.option(
    "--output-dir",
    type=str,
    default=None,
    help="Directory to save crawled pages (one file per page). Quick-crawl only. Default: crawl_<timestamp>.",
)
@click.option(
    "--allowed-domains",
    type=str,
    default=None,
    help="Comma-separated list of domains to crawl (default: same domain as start URL(s)). Quick-crawl only.",
)
@click.option(
    "--allow-external-domains",
    is_flag=True,
    default=False,
    help="Follow links to any domain (default: same domain only). Quick-crawl only.",
)
@click.pass_obj
def crawl(
    obj: dict,
    target: tuple[str, ...],
    project: str | None,
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
    screenshot: str | None,
    screenshot_selector: str | None,
    screenshot_full_page: str | None,
    return_page_source: str | None,
    return_markdown: str | None,
    return_text: str | None,
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
    scraping_config: str | None,
    max_depth: int,
    max_pages: int,
    output_dir: str | None,
    allowed_domains: str | None,
    allow_external_domains: bool,
) -> None:
    """Run a Scrapy spider with ScrapingBee.

    Two modes:

    \b
    1. Project spider: scrapingbee crawl SPIDER_NAME [--project /path]
       Runs the named spider from a Scrapy project. Pass params in your spider.

    2. Quick crawl: scrapingbee crawl URL [URL ...] [options]
       Starts from the given URL(s), follows same-domain links (0 = unlimited).
       Concurrency from --concurrency or usage API. Same options as scrape.
    """
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
    if not target:
        click.echo("Provide a spider name or one or more URLs.", err=True)
        raise SystemExit(1)
    # Resolve concurrency: --concurrency or usage API (same as batch)
    try:
        from .batch import get_batch_usage, resolve_batch_concurrency

        usage_info = get_batch_usage(obj["api_key"])
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, 1)
        from_concurrency = obj["concurrency"] > 0
    except Exception:
        concurrency = 16
        from_concurrency = False
    first = target[0]
    if first.startswith("http://") or first.startswith("https://"):
        urls = list(target)
        if from_concurrency:
            click.echo(f"Crawl: concurrency {concurrency} (from --concurrency)", err=True)
        else:
            click.echo(f"Crawl: concurrency {concurrency} (from usage API)", err=True)
        scrape_params = _crawl_build_params(
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
            json_response=json_response,
            screenshot=screenshot,
            screenshot_selector=screenshot_selector,
            screenshot_full_page=screenshot_full_page,
            return_page_source=return_page_source,
            return_markdown=return_markdown,
            return_text=return_text,
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
            scraping_config=scraping_config,
        )
        custom_headers = {}
        for h in headers:
            if ":" in h:
                k, _, v = h.partition(":")
                custom_headers[k.strip()] = v.strip()
        out_dir = output_dir or default_crawl_output_dir()
        allowed_list: list[str] | None = None
        if allowed_domains:
            allowed_list = [d.strip() for d in allowed_domains.split(",") if d.strip()]
        try:
            run_urls_spider(
                urls,
                key,
                scrape_params=scrape_params or None,
                custom_headers=custom_headers or None,
                max_depth=max_depth,
                max_pages=max_pages,
                concurrency=concurrency,
                output_dir=out_dir,
                allowed_domains=allowed_list,
                allow_external_domains=allow_external_domains,
            )
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        click.echo(f"Saved to {out_dir}", err=True)
    else:
        if len(target) > 1:
            click.echo(
                "Spider name must be a single argument. For multiple URLs use: "
                "scrapingbee crawl URL [URL ...]",
                err=True,
            )
            raise SystemExit(1)
        try:
            run_project_spider(first, key, project_path=project, concurrency=concurrency)
        except FileNotFoundError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)


# --- google ---
@cli.command()
@click.argument("query", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one query per line")
@click.option("--search-type", type=str, default=None)
@click.option("--country-code", type=str, default=None)
@click.option("--device", type=str, default=None)
@click.option("--page", type=int, default=None)
@click.option("--language", type=str, default=None)
@click.option("--nfpr", type=str, default=None)
@click.option("--extra-params", type=str, default=None)
@click.option("--add-html", type=str, default=None)
@click.option("--light-request", type=str, default=None)
@click.pass_obj
def google(
    obj: dict,
    query: str | None,
    input_file: str | None,
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
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if query:
            click.echo("cannot use both --input-file and positional query", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
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
                            nfpr=_parse_bool(nfpr),
                            extra_params=extra_params,
                            add_html=_parse_bool(add_html),
                            light_request=_parse_bool(light_request),
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not query:
        click.echo("expected one search query, or use --input-file for batch", err=True)
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
                nfpr=_parse_bool(nfpr),
                extra_params=extra_params,
                add_html=_parse_bool(add_html),
                light_request=_parse_bool(light_request),
            )
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


# --- fast-search ---
@cli.command("fast-search")
@click.argument("query", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one query per line")
@click.option("--page", type=int, default=None)
@click.option("--country-code", type=str, default=None)
@click.option("--language", type=str, default=None)
@click.pass_obj
def fast_search(
    obj: dict,
    query: str | None,
    input_file: str | None,
    page: int | None,
    country_code: str | None,
    language: str | None,
) -> None:
    """Search using the Fast Search API (sub-second results)."""
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if query:
            click.echo("cannot use both --input-file and positional query", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(q: str):
                    try:
                        data, headers, status_code = await client.fast_search(
                            q, page=page, country_code=country_code, language=language
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not query:
        click.echo("expected one search query, or use --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.fast_search(
                query, page=page, country_code=country_code, language=language
            )
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


# --- amazon-product ---
@cli.command("amazon-product")
@click.argument("asin", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one ASIN per line")
@click.option("--device", type=str, default=None)
@click.option("--domain", type=str, default=None)
@click.option("--country", type=str, default=None)
@click.option("--zip-code", type=str, default=None)
@click.option("--language", type=str, default=None)
@click.option("--currency", type=str, default=None)
@click.option("--add-html", type=str, default=None)
@click.option("--light-request", type=str, default=None)
@click.option("--screenshot", type=str, default=None)
@click.pass_obj
def amazon_product(
    obj: dict,
    asin: str | None,
    input_file: str | None,
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
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if asin:
            click.echo("cannot use both --input-file and positional ASIN", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
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
                            add_html=_parse_bool(add_html),
                            light_request=_parse_bool(light_request),
                            screenshot=_parse_bool(screenshot),
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not asin:
        click.echo("expected one ASIN, or use --input-file for batch", err=True)
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
                add_html=_parse_bool(add_html),
                light_request=_parse_bool(light_request),
                screenshot=_parse_bool(screenshot),
            )
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


# --- amazon-search ---
@cli.command("amazon-search")
@click.argument("query", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one query per line")
@click.option("--start-page", type=int, default=None)
@click.option("--pages", type=int, default=None)
@click.option("--sort-by", type=str, default=None)
@click.option("--device", type=str, default=None)
@click.option("--domain", type=str, default=None)
@click.option("--country", type=str, default=None)
@click.option("--zip-code", type=str, default=None)
@click.option("--language", type=str, default=None)
@click.option("--currency", type=str, default=None)
@click.option("--category-id", type=str, default=None)
@click.option("--merchant-id", type=str, default=None)
@click.option("--autoselect-variant", type=str, default=None)
@click.option("--add-html", type=str, default=None)
@click.option("--light-request", type=str, default=None)
@click.option("--screenshot", type=str, default=None)
@click.pass_obj
def amazon_search(
    obj: dict,
    query: str | None,
    input_file: str | None,
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
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if query:
            click.echo("cannot use both --input-file and positional query", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
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
                            autoselect_variant=_parse_bool(autoselect_variant),
                            add_html=_parse_bool(add_html),
                            light_request=_parse_bool(light_request),
                            screenshot=_parse_bool(screenshot),
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not query:
        click.echo("expected one search query, or use --input-file for batch", err=True)
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
                autoselect_variant=_parse_bool(autoselect_variant),
                add_html=_parse_bool(add_html),
                light_request=_parse_bool(light_request),
                screenshot=_parse_bool(screenshot),
            )
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


# --- walmart-search ---
@cli.command("walmart-search")
@click.argument("query", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one query per line")
@click.option("--min-price", type=int, default=None)
@click.option("--max-price", type=int, default=None)
@click.option("--sort-by", type=str, default=None)
@click.option("--device", type=str, default=None)
@click.option("--domain", type=str, default=None)
@click.option("--fulfillment-speed", type=str, default=None)
@click.option("--fulfillment-type", type=str, default=None)
@click.option("--delivery-zip", type=str, default=None)
@click.option("--store-id", type=str, default=None)
@click.option("--add-html", type=str, default=None)
@click.option("--light-request", type=str, default=None)
@click.option("--screenshot", type=str, default=None)
@click.pass_obj
def walmart_search(
    obj: dict,
    query: str | None,
    input_file: str | None,
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
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if query:
            click.echo("cannot use both --input-file and positional query", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
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
                            add_html=_parse_bool(add_html),
                            light_request=_parse_bool(light_request),
                            screenshot=_parse_bool(screenshot),
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not query:
        click.echo("expected one search query, or use --input-file for batch", err=True)
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
                add_html=_parse_bool(add_html),
                light_request=_parse_bool(light_request),
                screenshot=_parse_bool(screenshot),
            )
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


# --- walmart-product ---
@cli.command("walmart-product")
@click.argument("product_id", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one product ID per line")
@click.option("--domain", type=str, default=None)
@click.option("--delivery-zip", type=str, default=None)
@click.option("--store-id", type=str, default=None)
@click.option("--add-html", type=str, default=None)
@click.option("--light-request", type=str, default=None)
@click.option("--screenshot", type=str, default=None)
@click.pass_obj
def walmart_product(
    obj: dict,
    product_id: str | None,
    input_file: str | None,
    domain: str | None,
    delivery_zip: str | None,
    store_id: str | None,
    add_html: str | None,
    light_request: str | None,
    screenshot: str | None,
) -> None:
    """Fetch Walmart product details by product ID."""
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if product_id:
            click.echo("cannot use both --input-file and positional product-id", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
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
                            add_html=_parse_bool(add_html),
                            light_request=_parse_bool(light_request),
                            screenshot=_parse_bool(screenshot),
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not product_id:
        click.echo("expected one product ID, or use --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.walmart_product(
                product_id,
                domain=domain,
                delivery_zip=delivery_zip,
                store_id=store_id,
                add_html=_parse_bool(add_html),
                light_request=_parse_bool(light_request),
                screenshot=_parse_bool(screenshot),
            )
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


# --- youtube-search ---
@cli.command("youtube-search")
@click.argument("query", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one query per line")
@click.option("--upload-date", type=str, default=None)
@click.option("--type", "type_", type=str, default=None)
@click.option("--duration", type=str, default=None)
@click.option("--sort-by", type=str, default=None)
@click.option("--hd", type=str, default=None)
@click.option("--4k", "is_4k", type=str, default=None)
@click.option("--subtitles", type=str, default=None)
@click.option("--creative-commons", type=str, default=None)
@click.option("--live", type=str, default=None)
@click.option("--360", "is_360", type=str, default=None)
@click.option("--3d", "is_3d", type=str, default=None)
@click.option("--hdr", type=str, default=None)
@click.option("--location", type=str, default=None)
@click.option("--vr180", type=str, default=None)
@click.pass_obj
def youtube_search(
    obj: dict,
    query: str | None,
    input_file: str | None,
    upload_date: str | None,
    type_: str | None,
    duration: str | None,
    sort_by: str | None,
    hd: str | None,
    is_4k: str | None,
    subtitles: str | None,
    creative_commons: str | None,
    live: str | None,
    is_360: str | None,
    is_3d: str | None,
    hdr: str | None,
    location: str | None,
    vr180: str | None,
) -> None:
    """Search YouTube videos."""
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if query:
            click.echo("cannot use both --input-file and positional query", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(q: str):
                    try:
                        data, headers, status_code = await client.youtube_search(
                            q,
                            upload_date=upload_date,
                            type=type_,
                            duration=duration,
                            sort_by=sort_by,
                            hd=_parse_bool(hd),
                            is_4k=_parse_bool(is_4k),
                            subtitles=_parse_bool(subtitles),
                            creative_commons=_parse_bool(creative_commons),
                            live=_parse_bool(live),
                            is_360=_parse_bool(is_360),
                            is_3d=_parse_bool(is_3d),
                            hdr=_parse_bool(hdr),
                            location=_parse_bool(location),
                            vr180=_parse_bool(vr180),
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not query:
        click.echo("expected one search query, or use --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.youtube_search(
                query,
                upload_date=upload_date,
                type=type_,
                duration=duration,
                sort_by=sort_by,
                hd=_parse_bool(hd),
                is_4k=_parse_bool(is_4k),
                subtitles=_parse_bool(subtitles),
                creative_commons=_parse_bool(creative_commons),
                live=_parse_bool(live),
                is_360=_parse_bool(is_360),
                is_3d=_parse_bool(is_3d),
                hdr=_parse_bool(hdr),
                location=_parse_bool(location),
                vr180=_parse_bool(vr180),
            )
        _check_api_response(data, status_code)
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


# --- youtube-metadata ---
@cli.command("youtube-metadata")
@click.argument("video_id", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one video ID per line")
@click.pass_obj
def youtube_metadata(
    obj: dict,
    video_id: str | None,
    input_file: str | None,
) -> None:
    """Fetch YouTube video metadata."""
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if video_id:
            click.echo("cannot use both --input-file and positional video-id", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(vid: str):
                    try:
                        data, headers, status_code = await client.youtube_metadata(vid)
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not video_id:
        click.echo("expected one video ID, or use --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.youtube_metadata(video_id)
        _check_api_response(data, status_code)
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


# --- youtube-transcript ---
@cli.command("youtube-transcript")
@click.argument("video_id", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one video ID per line")
@click.option("--language", type=str, default=None)
@click.option("--transcript-origin", type=str, default=None)
@click.pass_obj
def youtube_transcript(
    obj: dict,
    video_id: str | None,
    input_file: str | None,
    language: str | None,
    transcript_origin: str | None,
) -> None:
    """Fetch YouTube video transcript/captions."""
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if video_id:
            click.echo("cannot use both --input-file and positional video-id", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(vid: str):
                    try:
                        data, headers, status_code = await client.youtube_transcript(
                            vid,
                            language=language,
                            transcript_origin=transcript_origin,
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not video_id:
        click.echo("expected one video ID, or use --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.youtube_transcript(
                video_id,
                language=language,
                transcript_origin=transcript_origin,
            )
        _check_api_response(data, status_code)
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


# --- youtube-trainability ---
@cli.command("youtube-trainability")
@click.argument("video_id", required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one video ID per line")
@click.pass_obj
def youtube_trainability(
    obj: dict,
    video_id: str | None,
    input_file: str | None,
) -> None:
    """Check if a YouTube video transcript is available for training."""
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if video_id:
            click.echo("cannot use both --input-file and positional video-id", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(vid: str):
                    try:
                        data, headers, status_code = await client.youtube_trainability(vid)
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not video_id:
        click.echo("expected one video ID, or use --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.youtube_trainability(video_id)
        _check_api_response(data, status_code)
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


# --- chatgpt ---
@cli.command()
@click.argument("prompt", nargs=-1, required=False)
@click.option("--input-file", type=click.Path(exists=True), help="Batch: one prompt per line")
@click.pass_obj
def chatgpt(
    obj: dict,
    prompt: tuple[str, ...],
    input_file: str | None,
) -> None:
    """Send a prompt to the ChatGPT API."""
    try:
        key = get_api_key(obj["api_key"])
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if prompt:
            click.echo("cannot use both --input-file and positional prompt", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(obj["api_key"])
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(p: str):
                    try:
                        data, headers, status_code = await client.chatgpt(p)
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
                results, obj["batch_output_dir"] or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not prompt:
        click.echo("expected at least one prompt argument, or use --input-file for batch", err=True)
        raise SystemExit(1)

    prompt_str = " ".join(prompt)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.chatgpt(prompt_str)
        _write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


def main() -> None:
    """Entry point for scrapingbee console script."""
    cli()


if __name__ == "__main__":
    main()
