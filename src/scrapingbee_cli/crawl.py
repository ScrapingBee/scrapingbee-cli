"""Scrapy crawl integration using scrapy-scrapingbee middleware."""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import click
from scrapy import Spider
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response
from scrapy.settings import Settings
from scrapy.utils.project import get_project_settings
from scrapy_scrapingbee import ScrapingBeeRequest

from . import user_agent_headers
from .batch import _batch_subdir_for_extension, extension_for_crawl, extension_from_url_path

if TYPE_CHECKING:
    from scrapy import Request

SCRAPINGBEE_MIDDLEWARE = "scrapy_scrapingbee.ScrapingBeeMiddleware"
MIDDLEWARE_PRIORITY = 725

# 0 means unlimited
DEFAULT_MAX_DEPTH = 0
DEFAULT_MAX_PAGES = 0

# URL extensions that will never contain HTML links — skip discovery re-requests for these.
_NON_HTML_URL_EXTENSIONS = frozenset(
    {
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
        "svg",
        "ico",  # images
        "pdf",
        "zip",  # binary downloads
        "css",
        "js",  # web assets
    }
)


def _normalize_url(url: str) -> str:
    """Strip fragment and trailing slash for deduplication."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}" + (f"?{parsed.query}" if parsed.query else "")


# Markdown link pattern: ](url) — used when response is markdown (e.g. --return-page-markdown true)
_MARKDOWN_LINK_RE = re.compile(rb"\]\s*\(\s*([^)\s]+)\s*\)")


def _param_truthy(params: dict[str, Any], key: str) -> bool:
    """True if params[key] is truthy (True or string 'true'/'1'/'yes')."""
    v = params.get(key)
    return v is True or (isinstance(v, str) and v.lower() in ("true", "1", "yes"))


def _params_for_discovery(params: dict[str, Any]) -> dict[str, Any]:
    """Params that would yield non-HTML or non-link-bearing response stripped
    so the discovery request returns HTML for link extraction."""
    out = dict(params)
    for k in (
        "screenshot",
        "screenshot_selector",
        "screenshot_full_page",
        "return_page_text",
        "json_response",
        "ai_query",
        "ai_selector",
        "ai_extract_rules",
        "extract_rules",
    ):
        out.pop(k, None)
    return out


def _preferred_extension_from_scrape_params(params: dict[str, Any]) -> str | None:
    """Return extension when scrape params force a response type (skip detection).
    Priority: screenshot+json_response -> json; screenshot -> png;
    return_page_markdown -> md; return_page_text -> txt; json_response -> json.
    """
    if _param_truthy(params, "screenshot") and _param_truthy(params, "json_response"):
        return "json"
    if _param_truthy(params, "screenshot"):
        return "png"
    if _param_truthy(params, "return_page_markdown"):
        return "md"
    if _param_truthy(params, "return_page_text"):
        return "txt"
    if _param_truthy(params, "json_response"):
        return "json"
    return None


def _requires_discovery_phase(scrape_params: dict[str, Any]) -> bool:
    """Return True if these scrape params always produce non-HTML responses.

    When True, every crawled page needs an extra HTML-only discovery request to
    find outgoing links, approximately doubling credit usage.  Affected modes:
      - extract_rules / ai_extract_rules / ai_query  → always returns JSON
      - return_page_text                             → always returns plain text
      - screenshot (without json_response)           → always returns raw PNG
    """
    if (
        scrape_params.get("extract_rules")
        or scrape_params.get("ai_extract_rules")
        or scrape_params.get("ai_query")
    ):
        return True
    if _param_truthy(scrape_params, "return_page_text"):
        return True
    # Raw screenshot (no JSON wrapper) → binary PNG, no extractable links.
    if _param_truthy(scrape_params, "screenshot") and not _param_truthy(
        scrape_params, "json_response"
    ):
        return True
    return False


def _body_from_json_response(body: bytes) -> bytes | None:
    """If body is JSON with a 'body' or 'content' field (ScrapingBee
    json_response), return that inner content."""
    if not body or body.lstrip()[:1] != b"{":
        return None
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    inner = data.get("body") or data.get("content")
    if inner is None:
        return None
    if isinstance(inner, str):
        return inner.encode("utf-8", errors="replace")
    if isinstance(inner, bytes):
        return inner
    return None


def _extract_hrefs_from_body(body: bytes) -> list[str]:
    """Extract link URLs from raw body: HTML a[href], then Markdown ](url)."""
    hrefs: list[str] = []
    # Raw bytes: use regex for <a href="..."> and ](url), not response.css
    if body:
        for m in re.finditer(rb'<a\s+[^>]*href\s*=\s*["\']([^"\']+)["\']', body, re.I):
            hrefs.append(m.group(1).decode("utf-8", errors="replace").strip())
        if not hrefs:
            for m in _MARKDOWN_LINK_RE.finditer(body):
                raw = m.group(1).decode("utf-8", errors="replace").strip()
                if raw and not raw.startswith(("#", "mailto:", "javascript:")):
                    hrefs.append(raw)
    return hrefs


def _extract_hrefs_from_response(response: Response) -> list[str]:
    """Extract link URLs from response: HTML a[href], Markdown ](url), or JSON body/content."""
    body = response.body
    # When ScrapingBee returns json_response, content is inside body/content
    inner = _body_from_json_response(body)
    if inner is not None:
        return _extract_hrefs_from_body(inner)
    hrefs: list[str] = []
    try:
        for href in response.css("a[href]::attr(href)").getall():
            if href and isinstance(href, str):
                hrefs.append(href.strip())
    except Exception:
        pass  # Response is binary/non-HTML — CSS selectors may raise any error
    # Markdown links (when body is markdown, e.g. --return-page-markdown true)
    if not hrefs and body:
        for m in _MARKDOWN_LINK_RE.finditer(body):
            raw = m.group(1).decode("utf-8", errors="replace").strip()
            if raw and not raw.startswith(("#", "mailto:", "javascript:")):
                hrefs.append(raw)
    return hrefs


class GenericScrapingBeeSpider(Spider):
    """Spider that crawls from given start URLs through ScrapingBee (follows same-domain links)."""

    name = "scrapingbee_generic"
    custom_settings: dict = {}

    def __init__(
        self,
        start_urls: list[str] | None = None,
        scrape_params: dict[str, Any] | None = None,
        custom_headers: dict[str, str] | None = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_pages: int = DEFAULT_MAX_PAGES,
        output_dir: str | None = None,
        allowed_domains: list[str] | None = None,
        allow_external_domains: bool = False,
        name: str | None = None,
        pre_seen_urls: set[str] | None = None,
        initial_write_counter: int = 0,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        save_pattern: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name=name, **kwargs)
        self.start_urls = start_urls or []
        self.scrape_params = scrape_params or {}
        self.custom_headers = custom_headers
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.output_dir = output_dir
        self.allow_external_domains = allow_external_domains
        # None = derive from start_urls (same-domain); else only these netlocs
        # Note: do NOT use self.allowed_domains — Scrapy's OffsiteMiddleware
        # would filter ScrapingBee proxy requests (app.scrapingbee.com ≠ target domain).
        self._cli_allowed_domains = allowed_domains
        self._allowed_netlocs: set[str] | None = None  # set when first request runs
        self.seen_urls: set[str] = set(pre_seen_urls) if pre_seen_urls else set()
        self._write_lock = threading.Lock()
        self._write_counter = initial_write_counter
        # Maps response URL → {file, fetched_at, http_status}; written to manifest.json on close.
        self._url_file_map: dict[str, Any] = {}
        self._include_re = re.compile(include_pattern) if include_pattern else None
        self._exclude_re = re.compile(exclude_pattern) if exclude_pattern else None
        self._save_re = re.compile(save_pattern) if save_pattern else None
        self._save_count = 0
        self._fetch_count = 0

    def _allowed_netlocs_set(self) -> set[str]:
        if self._allowed_netlocs is not None:
            return self._allowed_netlocs
        if self.allow_external_domains:
            self._allowed_netlocs = set()  # empty = allow all
            return self._allowed_netlocs
        if self._cli_allowed_domains:
            self._allowed_netlocs = {d.lower().strip() for d in self._cli_allowed_domains if d}
            return self._allowed_netlocs
        self._allowed_netlocs = {urlparse(u).netloc.lower() for u in self.start_urls}
        return self._allowed_netlocs

    def _url_allowed(self, url: str) -> bool:
        if self.allow_external_domains:
            return True
        netloc = urlparse(url).netloc.lower()
        allowed = self._allowed_netlocs_set()
        return not allowed or netloc in allowed

    def start_requests(self) -> Iterator[Request]:
        for url in self.start_urls:
            normalized = _normalize_url(url)
            if normalized in self.seen_urls:
                continue
            if self.max_pages != 0 and self._fetch_count >= self.max_pages:
                continue
            self.seen_urls.add(normalized)
            # When --save-pattern is set, use discovery params for initial crawl
            # (HTML for link finding). Full params only for save-worthy pages.
            if self._save_re:
                params = _params_for_discovery(self.scrape_params)
                callback = self._parse_crawl_and_save
            else:
                params = dict(self.scrape_params)
                callback = self.parse
            yield ScrapingBeeRequest(
                url,
                params=params,
                headers=self.custom_headers,
                meta={"depth": 0},
                callback=callback,
            )

    def _response_headers_dict(self, response: Response) -> dict:
        """Build a str -> str headers dict from Scrapy response for extension_for_scrape."""
        out: dict[str, str] = {}
        for k, v in response.headers.items():
            key = k.decode("utf-8", errors="replace") if isinstance(k, bytes) else str(k)
            val = v[0] if isinstance(v, (list, tuple)) and v else v
            val = val.decode("utf-8", errors="replace") if isinstance(val, bytes) else str(val)
            out[key] = val
        return out

    def _save_response(self, response: Response) -> None:
        """Write response body to output_dir (one file per response)."""
        if not self.output_dir:
            return
        headers = self._response_headers_dict(response)
        preferred = _preferred_extension_from_scrape_params(self.scrape_params)
        ext = extension_for_crawl(response.url, headers, response.body, preferred)
        subdir = _batch_subdir_for_extension(ext)
        # Extract Spb-Cost header for credits_used.
        credits_used: int | None = None
        for k, v in headers.items():
            if k.lower() == "spb-cost" and v:
                try:
                    credits_used = int(v)
                except (ValueError, TypeError):
                    pass
                break
        # Scrapy records download_latency in response.meta (seconds).
        latency_ms: int | None = None
        download_latency = response.meta.get("download_latency")
        if download_latency is not None:
            try:
                latency_ms = int(float(download_latency) * 1000)
            except (ValueError, TypeError):
                pass
        with self._write_lock:
            n = self._write_counter
            self._write_counter += 1
            filename = f"{n + 1}.{ext}"
            rel = f"{subdir}/{filename}" if subdir else filename
            self._url_file_map[response.url] = {
                "file": rel,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "http_status": response.status,
                "credits_used": credits_used,
                "latency_ms": latency_ms,
            }
        out_path = Path(self.output_dir).resolve()
        if subdir:
            out_path = out_path / subdir
        out_path.mkdir(parents=True, exist_ok=True)
        out_path = out_path / f"{n + 1}.{ext}"
        out_path.write_bytes(response.body)

    def closed(self, reason: str) -> None:
        """Write manifest.json (URL → relative filename) when the crawl ends."""
        if not self.output_dir or not self._url_file_map:
            return
        abs_dir = str(Path(self.output_dir).resolve())
        manifest_path = Path(abs_dir) / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(self._url_file_map, f, indent=2, ensure_ascii=False)
        from .batch import _save_batch_meta

        _save_batch_meta(abs_dir, len(self._url_file_map), len(self._url_file_map), 0)

    def _iter_follow_requests(
        self,
        response: Response,
        params: dict[str, Any],
        callback: Any,
    ) -> Any:
        """Yield ScrapingBeeRequests for allowed, same-domain
        (or allowed-domains) links from response."""
        depth = response.meta.get("depth", 0)
        if self.max_depth != 0 and depth >= self.max_depth:
            return
        # max_pages = max pages fetched from API (credits spent)
        if self.max_pages != 0 and self._fetch_count >= self.max_pages:
            return
        for href in _extract_hrefs_from_response(response):
            if not href or href.startswith(("#", "mailto:", "javascript:")):
                continue
            full_url = response.urljoin(href)
            parsed = urlparse(full_url)
            if parsed.scheme not in ("http", "https"):
                continue
            if not self._url_allowed(full_url):
                continue
            if self._include_re and not self._include_re.search(full_url):
                continue
            if self._exclude_re and self._exclude_re.search(full_url):
                continue
            normalized = _normalize_url(full_url)
            if normalized in self.seen_urls:
                continue
            self.seen_urls.add(normalized)
            yield ScrapingBeeRequest(
                full_url,
                params=params,
                headers=self.custom_headers,
                meta={"depth": depth + 1},
                callback=callback,
            )

    def parse(self, response: Response, **kwargs: object) -> Any:
        """Save response, then yield follow requests. If no links found in response,
        yield a discovery request (same URL with HTML-only params) to extract links."""
        self._fetch_count += 1
        self.logger.info("Fetched %s (%d bytes)", response.url, len(response.body))
        # Only save if URL matches --save-pattern (or no pattern set)
        if not self._save_re or self._save_re.search(response.url):
            try:
                self._save_response(response)
            except Exception as e:
                self.logger.warning("Failed to save %s: %s", response.url, e)
        try:
            hrefs = _extract_hrefs_from_response(response)
        except Exception:
            hrefs = []
        if hrefs:
            yield from self._iter_follow_requests(response, dict(self.scrape_params), self.parse)
        else:
            # Skip discovery re-request for URLs that are clearly binary/non-HTML resources
            # (images, PDFs, CSS, JS, etc.) — they will never contain <a href> links.
            url_ext = extension_from_url_path(response.url)
            if url_ext in _NON_HTML_URL_EXTENSIONS:
                return
            discovery_params = _params_for_discovery(self.scrape_params)
            yield ScrapingBeeRequest(
                response.url,
                params=discovery_params,
                headers=self.custom_headers,
                meta=response.meta,
                callback=self._parse_discovery_links_only,
                dont_filter=True,
            )

    def _parse_crawl_and_save(self, response: Response, **kwargs: object) -> Any:
        """Used when --save-pattern is set. Receives HTML (discovery params),
        extracts links, follows them, and fires a save request for matching pages."""
        self._fetch_count += 1
        self.logger.info("Fetched %s (%d bytes) [crawl]", response.url, len(response.body))
        # If this page matches --save-pattern, fire a separate request with full params to save
        if self._save_re and self._save_re.search(response.url):
            yield ScrapingBeeRequest(
                response.url,
                params=dict(self.scrape_params),
                headers=self.custom_headers,
                meta=response.meta,
                callback=self._parse_save_only,
                dont_filter=True,
            )
        # Extract links from HTML and follow them
        try:
            hrefs = _extract_hrefs_from_response(response)
        except Exception:
            hrefs = []
        if hrefs:
            yield from self._iter_follow_requests(
                response,
                _params_for_discovery(self.scrape_params),
                self._parse_crawl_and_save,
            )

    def _parse_save_only(self, response: Response, **kwargs: object) -> Any:
        """Save the response (fetched with full params). No link following."""
        self.logger.info("Fetched %s (%d bytes) [save]", response.url, len(response.body))
        try:
            self._save_response(response)
            self._save_count += 1
        except Exception as e:
            self.logger.warning("Failed to save %s: %s", response.url, e)

    def _parse_discovery_links_only(self, response: Response, **kwargs: object) -> Any:
        """Handle HTML response from discovery request: extract links and follow (no save)."""
        self.logger.info("Fetched %s (%d bytes) [discovery]", response.url, len(response.body))
        try:
            yield from self._iter_follow_requests(response, dict(self.scrape_params), self.parse)
        except Exception as e:
            self.logger.warning("Discovery failed for %s: %s", response.url, e)


def _fetch_sitemap_urls(url: str, *, api_key: str | None = None, depth: int = 0) -> list[str]:
    """Fetch a sitemap URL and return all page URLs it contains.

    Handles sitemap indexes recursively (up to depth 2).  When *api_key* is
    provided the sitemap is fetched through the ScrapingBee API (with
    ``render_js=false`` — 1 credit) so proxies and bot-protection handling
    apply.  Falls back to stdlib ``urllib`` when no key is given.
    """
    import asyncio as _asyncio
    from xml.etree import ElementTree as ET

    from .client import Client
    from .config import BASE_URL

    if depth > 2:
        return []
    if not url.startswith(("http://", "https://")):
        click.echo(f"Warning: skipping sitemap URL with unsupported scheme: {url}", err=True)
        return []

    if api_key:

        async def _fetch() -> bytes:
            async with Client(api_key, BASE_URL, timeout=60) as client:
                body, _headers, status = await client.scrape(
                    url,
                    render_js=False,
                    retries=2,
                    backoff=2.0,
                )
                if status >= 400:
                    raise RuntimeError(f"HTTP {status}")
                return body

        try:
            data = _asyncio.run(_fetch())
        except Exception as e:
            click.echo(f"Warning: could not fetch sitemap {url}: {e}", err=True)
            return []
    else:
        import urllib.request

        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
                data = resp.read()
        except Exception as e:
            click.echo(f"Warning: could not fetch sitemap {url}: {e}", err=True)
            return []
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        click.echo(f"Warning: could not parse sitemap {url}: {e}", err=True)
        return []
    # Strip namespace for tag matching
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    if tag == "sitemapindex":
        child_locs = [
            loc.text.strip()
            for loc in root.findall(".//sm:sitemap/sm:loc", ns)
            if loc.text and loc.text.strip()
        ] or [
            loc.text.strip()
            for loc in root.findall(".//sitemap/loc")
            if loc.text and loc.text.strip()
        ]
        all_urls: list[str] = []
        for child_url in child_locs:
            all_urls.extend(_fetch_sitemap_urls(child_url, api_key=api_key, depth=depth + 1))
        return all_urls
    # Regular urlset
    return [
        loc.text.strip()
        for loc in root.findall(".//sm:url/sm:loc", ns)
        if loc.text and loc.text.strip()
    ] or [loc.text.strip() for loc in root.findall(".//url/loc") if loc.text and loc.text.strip()]


USER_AGENT_CLI = user_agent_headers()["User-Agent"]


def default_crawl_output_dir() -> str:
    """Default folder name for crawl output (crawl_<timestamp>)."""
    return "crawl_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _settings_with_scrapingbee(
    api_key: str,
    base_settings: dict | Settings | None = None,
    concurrency: int = 16,
    download_delay: float | None = None,
    autothrottle_enabled: bool | None = None,
) -> Settings:
    """Build Scrapy settings with ScrapingBee middleware, API key, and concurrency."""
    settings = Settings(base_settings) if base_settings else Settings()
    settings.set("SCRAPINGBEE_API_KEY", api_key)
    settings.set("USER_AGENT", USER_AGENT_CLI)
    settings.set("ROBOTSTXT_OBEY", False)  # ScrapingBee handles robots.txt compliance
    # Cap crawl concurrency — unlike batch, all requests go to one domain via ScrapingBee.
    # High concurrency causes massive overshoot on --max-pages since requests queue before checks run.
    capped = min(max(1, concurrency), 50)
    settings.set("CONCURRENT_REQUESTS", capped)
    settings.set("CONCURRENT_REQUESTS_PER_DOMAIN", capped)
    if download_delay is not None:
        settings.set("DOWNLOAD_DELAY", download_delay)
    if autothrottle_enabled is not None:
        settings.set("AUTOTHROTTLE_ENABLED", autothrottle_enabled)
    middlewares = dict(settings.get("DOWNLOADER_MIDDLEWARES", {}))
    middlewares[SCRAPINGBEE_MIDDLEWARE] = MIDDLEWARE_PRIORITY
    settings.set("DOWNLOADER_MIDDLEWARES", middlewares)
    # Disable Scrapy's DepthMiddleware — we track depth manually in meta.
    # The built-in middleware increments depth on every yielded request, which
    # causes discovery re-fetches (same URL, HTML-only) to consume a depth
    # level and break --max-depth for non-HTML modes (--ai-query, etc.).
    spider_mw = dict(settings.get("SPIDER_MIDDLEWARES", {}))
    spider_mw["scrapy.spidermiddlewares.depth.DepthMiddleware"] = None
    settings.set("SPIDER_MIDDLEWARES", spider_mw)
    return settings


def run_project_spider(
    spider_name: str,
    api_key: str,
    project_path: str | Path | None = None,
    concurrency: int = 16,
    download_delay: float | None = None,
    autothrottle_enabled: bool | None = None,
) -> None:
    """Run a Scrapy project spider with ScrapingBee middleware and API key injected.
    Concurrency is controlled by --concurrency (or usage API when 0)."""
    project_path = Path(project_path or os.getcwd()).resolve()
    scrapy_cfg = project_path / "scrapy.cfg"
    if not scrapy_cfg.is_file():
        raise FileNotFoundError(
            f"No Scrapy project found in {project_path} (missing scrapy.cfg). "
            "Run from a Scrapy project directory or pass --project /path/to/project."
        )
    orig_cwd = os.getcwd()
    try:
        os.chdir(project_path)
        base_settings = get_project_settings()
        settings = _settings_with_scrapingbee(
            api_key,
            base_settings,
            concurrency=concurrency,
            download_delay=download_delay,
            autothrottle_enabled=autothrottle_enabled,
        )
        process = CrawlerProcess(settings)
        process.crawl(spider_name)
        process.start()
    finally:
        os.chdir(orig_cwd)


def run_urls_spider(
    urls: list[str],
    api_key: str,
    scrape_params: dict[str, Any] | None = None,
    custom_headers: dict[str, str] | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
    concurrency: int = 16,
    output_dir: str | None = None,
    allowed_domains: list[str] | None = None,
    allow_external_domains: bool = False,
    download_delay: float | None = None,
    autothrottle_enabled: bool | None = None,
    resume: bool = False,
    include_pattern: str | None = None,
    exclude_pattern: str | None = None,
    save_pattern: str | None = None,
) -> None:
    """Run the built-in generic spider: start from URLs and follow links.
    By default only same-domain links are followed; use allowed_domains or
    allow_external_domains to change. If output_dir is set, each response
    is saved as a separate file.

    When resume=True and output_dir has a manifest.json, pre-populate seen_urls
    and write_counter from the previous run so already-crawled URLs are skipped.
    """
    if not urls:
        raise ValueError("At least one URL is required")
    pre_seen_urls: set[str] | None = None
    initial_write_counter = 0
    if resume and output_dir:
        manifest_path = Path(output_dir).resolve() / "manifest.json"
        if manifest_path.is_file():
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    existing_map: dict[str, Any] = json.load(f)
                pre_seen_urls = set(existing_map.keys())
                initial_write_counter = len(existing_map)
                click.echo(
                    f"Resume: skipping {len(pre_seen_urls)} already-crawled URLs.",
                    err=True,
                )
            except Exception as e:
                click.echo(f"Warning: could not load manifest for resume: {e}", err=True)
    # Cap concurrency at max_pages to prevent overshoot — Scrapy queues up to
    # CONCURRENT_REQUESTS before any response arrives to trigger the limit check.
    effective_concurrency = concurrency
    if max_pages > 0:
        effective_concurrency = min(concurrency, max_pages)
    settings = _settings_with_scrapingbee(
        api_key,
        concurrency=effective_concurrency,
        download_delay=download_delay,
        autothrottle_enabled=autothrottle_enabled,
    )
    settings.set("LOG_LEVEL", "WARNING")
    if max_pages > 0:
        settings.set("CLOSESPIDER_PAGECOUNT", max_pages)
    process = CrawlerProcess(settings)
    process.crawl(
        GenericScrapingBeeSpider,
        start_urls=urls,
        scrape_params=scrape_params or {},
        custom_headers=custom_headers,
        max_depth=max_depth,
        max_pages=max_pages,
        output_dir=output_dir,
        allowed_domains=allowed_domains,
        allow_external_domains=allow_external_domains,
        pre_seen_urls=pre_seen_urls,
        initial_write_counter=initial_write_counter,
        include_pattern=include_pattern,
        exclude_pattern=exclude_pattern,
        save_pattern=save_pattern,
    )
    process.start()
