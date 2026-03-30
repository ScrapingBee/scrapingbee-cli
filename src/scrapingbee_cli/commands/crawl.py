"""Crawl command (Scrapy project spider and quick-crawl URLs)."""

from __future__ import annotations

import click
from click_option_group import optgroup

from ..batch import get_batch_usage, resolve_batch_concurrency
from ..cli_utils import (
    DEVICE_DESKTOP_MOBILE,
    WAIT_BROWSER_HELP,
    _output_options,
    _validate_json_option,
    _validate_range,
    build_scrape_kwargs,
    scrape_kwargs_to_api_params,
    store_common_options,
)
from ..config import get_api_key
from ..crawl import (
    _fetch_sitemap_urls,
    default_crawl_output_dir,
    run_project_spider,
    run_urls_spider,
)


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
    scraping_config: str | None = None,
) -> dict[str, str]:
    """Build ScrapingBee API params dict from crawl options (quick-crawl URL mode)."""
    kwargs = build_scrape_kwargs(
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
        body=None,
        scraping_config=scraping_config,
    )
    return scrape_kwargs_to_api_params(kwargs)


@click.command()
@click.argument("target", nargs=-1, required=False)
@click.option(
    "--from-sitemap",
    "from_sitemap",
    type=str,
    default=None,
    help="Fetch URLs from a sitemap.xml and crawl them (URL or path to sitemap).",
)
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, file_okay=False, path_type=str),
    default=None,
    help="Path to Scrapy project. Spider mode only.",
)
@click.option(
    "--scraping-config",
    type=str,
    default=None,
    help="Apply a pre-saved scraping configuration by name. Create configs in the ScrapingBee dashboard. Inline options override config settings.",
)
@optgroup.group("Rendering", help="JavaScript rendering and viewport options")
@optgroup.option(
    "--render-js",
    type=str,
    default=None,
    help="Enable/disable JS rendering (true/false). When omitted, parameter is not sent (API default may apply).",
)
@optgroup.option(
    "--js-scenario",
    type=str,
    default=None,
    help="JSON JavaScript scenario (e.g. click, wait, scroll).",
)
@optgroup.option(
    "--wait", type=int, default=None, help="Wait time in ms (0-35000) before returning HTML."
)
@optgroup.option(
    "--wait-for", type=str, default=None, help="CSS or XPath selector to wait for before returning."
)
@optgroup.option("--wait-browser", type=str, default=None, help=WAIT_BROWSER_HELP)
@optgroup.option("--block-ads", type=str, default=None, help="Block ads (true/false).")
@optgroup.option(
    "--block-resources", type=str, default=None, help="Block images and CSS (true/false)."
)
@optgroup.option("--window-width", type=int, default=None, help="Viewport width in pixels.")
@optgroup.option("--window-height", type=int, default=None, help="Viewport height in pixels.")
@optgroup.group("Proxy", help="Proxy and geo options")
@optgroup.option(
    "--premium-proxy", type=str, default=None, help="Use premium/residential proxies (true/false)."
)
@optgroup.option(
    "--stealth-proxy", type=str, default=None, help="Use stealth proxies (true/false). 75 credits."
)
@optgroup.option("--country-code", type=str, default=None, help="Proxy country code (ISO 3166-1).")
@optgroup.option("--own-proxy", type=str, default=None, help="Your proxy: user:pass@host:port.")
@optgroup.group("Headers", help="Custom and forwarded headers")
@optgroup.option(
    "-H", "--header", "headers", multiple=True, help="Custom header Key:Value (repeatable)."
)
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
    help="Forward only custom headers (true/false).",
)
@optgroup.group("Output", help="Response format")
@optgroup.option(
    "--json-response", type=str, default=None, help="Wrap response in JSON (true/false)."
)
@optgroup.option(
    "--return-page-source",
    type=str,
    default=None,
    help="Return unaltered HTML. Value: true or false (e.g. --return-page-source true).",
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
    help="Capture screenshot (true/false). Requires render_js=true.",
)
@optgroup.option(
    "--screenshot-selector", type=str, default=None, help="CSS selector for screenshot area."
)
@optgroup.option(
    "--screenshot-full-page", type=str, default=None, help="Full page screenshot (true/false)."
)
@optgroup.group("Extraction", help="CSS/XPath and AI extraction (+5 credits for AI)")
@optgroup.option(
    "--extract-rules", type=str, default=None, help="CSS/XPath extraction rules as JSON."
)
@optgroup.option(
    "--ai-query", type=str, default=None, help="Natural language extraction query. +5 credits."
)
@optgroup.option(
    "--ai-selector", type=str, default=None, help="CSS selector to focus AI extraction."
)
@optgroup.option(
    "--ai-extract-rules", type=str, default=None, help="AI extraction rules as JSON. +5 credits."
)
@optgroup.group("Request", help="Session, timeout, cookies, device")
@optgroup.option(
    "--session-id", type=int, default=None, help="Session ID for sticky IP (0-10000000)."
)
@optgroup.option("--timeout", type=int, default=None, help="Timeout in ms (1000-140000).")
@optgroup.option("--cookies", type=str, default=None, help="Custom cookies string.")
@optgroup.option(
    "--device",
    type=click.Choice(DEVICE_DESKTOP_MOBILE, case_sensitive=False),
    default=None,
    help="Device: desktop or mobile.",
)
@optgroup.option(
    "--custom-google", type=str, default=None, help="Scrape Google domains (true/false)."
)
@optgroup.option(
    "--transparent-status-code",
    type=str,
    default=None,
    help="Return target status as-is (true/false).",
)
@optgroup.group("Crawl", help="Quick-crawl: depth, pages, output, throttling")
@optgroup.option(
    "--max-depth",
    type=int,
    default=0,
    help="Max link depth when following same-domain links (0 = unlimited). Quick-crawl only.",
)
@optgroup.option(
    "--max-pages",
    type=int,
    default=0,
    help="Max pages to fetch from API (0 = unlimited). Each page costs credits.",
)
@optgroup.option(
    "--allowed-domains",
    type=str,
    default=None,
    help=(
        "Comma-separated list of domains to crawl "
        "(default: same domain as start URL(s)). Quick-crawl only."
    ),
)
@optgroup.option(
    "--allow-external-domains",
    is_flag=True,
    default=False,
    help="Follow links to any domain (default: same domain only). Quick-crawl only.",
)
@optgroup.option(
    "--include-pattern",
    type=str,
    default=None,
    help="Regex: only follow URLs matching this pattern.",
)
@optgroup.option(
    "--exclude-pattern",
    type=str,
    default=None,
    help="Regex: skip URLs matching this pattern.",
)
@optgroup.option(
    "--save-pattern",
    type=str,
    default=None,
    help="Regex: only save pages matching this pattern. Other pages are visited for link discovery but not saved.",
)
@optgroup.option(
    "--download-delay",
    type=float,
    default=None,
    help="Delay in seconds between requests (Scrapy DOWNLOAD_DELAY).",
)
@optgroup.option(
    "--autothrottle",
    is_flag=True,
    default=False,
    help="Enable Scrapy AutoThrottle to adapt request rate.",
)
@click.option(
    "--output-dir",
    "output_dir",
    default=None,
    help="Crawl output folder (default: crawl_<timestamp>).",
)
@click.option(
    "--concurrency", type=int, default=0, help="Max concurrent requests (0 = auto from plan)."
)
@click.option(
    "--resume", is_flag=True, default=False, help="Skip already-crawled URLs from previous run."
)
@click.option(
    "--on-complete",
    "on_complete",
    type=str,
    default=None,
    help="[Advanced] Shell command to run after crawl completes. Requires unsafe mode.",
)
@_output_options
@click.pass_obj
def crawl_cmd(
    obj: dict,
    target: tuple[str, ...],
    from_sitemap: str | None,
    project: str | None,
    scraping_config: str | None,
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
    max_depth: int,
    max_pages: int,
    allowed_domains: str | None,
    allow_external_domains: bool,
    include_pattern: str | None,
    exclude_pattern: str | None,
    save_pattern: str | None,
    download_delay: float | None,
    autothrottle: bool,
    output_dir: str | None,
    concurrency: int,
    resume: bool,
    on_complete: str | None,
    **kwargs,
) -> None:
    """Run a Scrapy spider with ScrapingBee.

    Three modes:

    \b
    1. Project spider: scrapingbee crawl SPIDER_NAME [--project /path]
       Runs the named spider from a Scrapy project. Concurrency is controlled
       by --concurrency (or usage API when 0). Pass params in your spider.

    2. Quick crawl: scrapingbee crawl URL [URL ...] [options]
       Starts from the given URL(s), follows same-domain links (0 = unlimited).
       Concurrency from --concurrency or usage API. Same options as scrape.

    3. Sitemap crawl: scrapingbee crawl --from-sitemap https://example.com/sitemap.xml
       Fetches all URLs from the sitemap and crawls them.

    See https://www.scrapingbee.com/documentation/ for parameter details.
    """
    store_common_options(obj, **kwargs)
    obj["output_dir"] = output_dir or ""
    obj["concurrency"] = concurrency or 0
    obj["resume"] = resume
    obj["on_complete"] = on_complete
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)
    # Resolve URLs: either from --from-sitemap or positional target arguments
    if from_sitemap:
        from ..cli_utils import ensure_url_scheme

        from_sitemap = ensure_url_scheme(from_sitemap)
        click.echo(f"Fetching sitemap: {from_sitemap}", err=True)
        sitemap_urls = _fetch_sitemap_urls(from_sitemap, api_key=key)
        if not sitemap_urls:
            click.echo("No URLs found in sitemap.", err=True)
            raise SystemExit(1)
        click.echo(f"Found {len(sitemap_urls)} URLs in sitemap.", err=True)
        target = tuple(sitemap_urls)
    if not target:
        click.echo("Provide a spider name, one or more URLs, or --from-sitemap URL.", err=True)
        raise SystemExit(1)
    try:
        usage_info = get_batch_usage(None)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, 1)
        from_concurrency = obj["concurrency"] > 0
    except Exception:
        concurrency = 16
        from_concurrency = False
    from ..cli_utils import ensure_url_scheme

    first = target[0]
    if first.startswith("http://") or first.startswith("https://") or "." in first:
        urls = [ensure_url_scheme(t) for t in target]
        display_concurrency = min(concurrency, max_pages) if max_pages > 0 else min(concurrency, 50)
        if from_concurrency:
            click.echo(f"Crawl: concurrency {display_concurrency} (from --concurrency)", err=True)
        else:
            click.echo(f"Crawl: concurrency {display_concurrency} (from usage API)", err=True)
        try:
            _validate_json_option("--js-scenario", js_scenario)
            _validate_json_option("--extract-rules", extract_rules)
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
                scraping_config=scraping_config,
            )
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        _validate_range("session_id", session_id, 0, 10_000_000)
        _validate_range("timeout", timeout, 1000, 140_000, "ms")
        _validate_range("wait", wait, 0, 35_000, "ms")
        custom_headers = {}
        for h in headers:
            if ":" not in h:
                click.echo(f'Invalid header format "{h}", expected Key:Value', err=True)
                raise SystemExit(1)
            k, _, v = h.partition(":")
            custom_headers[k.strip()] = v.strip()
        out_dir = (obj.get("output_dir") or "").strip() or None
        out_dir = out_dir or default_crawl_output_dir()
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
                download_delay=download_delay,
                autothrottle_enabled=autothrottle or None,
                resume=obj.get("resume", False),
                include_pattern=include_pattern,
                exclude_pattern=exclude_pattern,
                save_pattern=save_pattern,
            )
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        click.echo(f"Saved to {out_dir}", err=True)
        on_complete = obj.get("on_complete")
        if on_complete:
            from ..cli_utils import run_on_complete

            run_on_complete(on_complete, output_dir=out_dir)
    else:
        if len(target) > 1:
            click.echo(
                "Spider name must be a single argument. For multiple URLs use: "
                "scrapingbee crawl URL [URL ...]",
                err=True,
            )
            raise SystemExit(1)
        try:
            run_project_spider(
                first,
                key,
                project_path=project,
                concurrency=concurrency,
                download_delay=download_delay,
                autothrottle_enabled=autothrottle or None,
            )
        except FileNotFoundError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)


def register(cli: click.Group) -> None:
    cli.add_command(crawl_cmd, "crawl")
