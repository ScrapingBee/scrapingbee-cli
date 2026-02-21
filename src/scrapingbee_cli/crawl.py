"""Scrapy crawl integration using scrapy-scrapingbee middleware."""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

from scrapy import Spider
from scrapy.crawler import CrawlerProcess
from scrapy.http import Response
from scrapy.utils.project import get_project_settings

from scrapy_scrapingbee import ScrapingBeeRequest

from .batch import _batch_subdir_for_extension, extension_for_crawl

if TYPE_CHECKING:
    from scrapy import Request

SCRAPINGBEE_MIDDLEWARE = "scrapy_scrapingbee.ScrapingBeeMiddleware"
MIDDLEWARE_PRIORITY = 725

# 0 means unlimited
DEFAULT_MAX_DEPTH = 0
DEFAULT_MAX_PAGES = 0


def _normalize_url(url: str) -> str:
    """Strip fragment and trailing slash for deduplication."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}" + (
        f"?{parsed.query}" if parsed.query else ""
    )


# Markdown link pattern: ](url) — used when response is markdown (e.g. --return-markdown=true)
_MARKDOWN_LINK_RE = re.compile(rb"\]\s*\(\s*([^)\s]+)\s*\)")


def _param_truthy(params: dict[str, Any], key: str) -> bool:
    """True if params[key] is truthy (True or string 'true'/'1'/'yes')."""
    v = params.get(key)
    return v is True or (isinstance(v, str) and v.lower() in ("true", "1", "yes"))


def _needs_discovery_phase(params: dict[str, Any]) -> bool:
    """True when we must fetch HTML first to get links because the save response won't contain any.
    - return_page_text: response is plain text, no links -> discovery.
    - screenshot without json_response: response is image only, no links -> discovery.
    - screenshot + json_response: HTML is in JSON body -> crawl normally, no discovery.
    """
    if _param_truthy(params, "return_page_text"):
        return True
    if _param_truthy(params, "screenshot") and not _param_truthy(params, "json_response"):
        return True
    return False


def _params_for_discovery(params: dict[str, Any]) -> dict[str, Any]:
    """Params with screenshot, return_page_text, json_response stripped so API returns HTML for link extraction."""
    out = dict(params)
    for k in ("screenshot", "screenshot_selector", "screenshot_full_page", "return_page_text", "json_response"):
        out.pop(k, None)
    return out


def _preferred_extension_from_scrape_params(params: dict[str, Any]) -> str | None:
    """Return extension when scrape params force a response type (skip detection).
    Priority: screenshot+json_response -> json; screenshot -> png; return_page_markdown -> md;
    return_page_text -> txt; json_response -> json.
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


def _body_from_json_response(body: bytes) -> bytes | None:
    """If body is JSON with a 'body' or 'content' field (ScrapingBee json_response), return that inner content."""
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
    # We can't use response.css on raw bytes; use regex for <a href="..."> and ](url)
    if body:
        # HTML: href="..." or href='...'
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
    # HTML links (when body is HTML)
    for href in response.css("a[href]::attr(href)").getall():
        if href and isinstance(href, str):
            hrefs.append(href.strip())
    # Markdown links (when body is markdown, e.g. --return-markdown=true)
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
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.start_urls = start_urls or []
        self.scrape_params = scrape_params or {}
        self.custom_headers = custom_headers
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.output_dir = output_dir
        self.allow_external_domains = allow_external_domains
        # None = derive from start_urls (same-domain); else only these netlocs
        self.allowed_domains = allowed_domains
        self._allowed_netlocs: set[str] | None = None  # set when first request runs
        self._discovery_params: dict[str, Any] | None = None  # cached when _needs_discovery_phase, avoid repeated dict copy
        self.seen_urls: set[str] = set()
        self._write_lock = threading.Lock()
        self._write_counter = 0

    def _allowed_netlocs_set(self) -> set[str]:
        if self._allowed_netlocs is not None:
            return self._allowed_netlocs
        if self.allow_external_domains:
            self._allowed_netlocs = set()  # empty = allow all
            return self._allowed_netlocs
        if self.allowed_domains:
            self._allowed_netlocs = {d.lower().strip() for d in self.allowed_domains if d}
            return self._allowed_netlocs
        self._allowed_netlocs = {urlparse(u).netloc.lower() for u in self.start_urls}
        return self._allowed_netlocs

    def _url_allowed(self, url: str) -> bool:
        if self.allow_external_domains:
            return True
        netloc = urlparse(url).netloc.lower()
        allowed = self._allowed_netlocs_set()
        return not allowed or netloc in allowed

    def start_requests(self) -> list[Request]:
        use_discovery = _needs_discovery_phase(self.scrape_params)
        if use_discovery:
            self._discovery_params = _params_for_discovery(self.scrape_params)
        params = self._discovery_params if use_discovery else dict(self.scrape_params)
        callback = self.parse_discovery if use_discovery else self.parse
        for url in self.start_urls:
            normalized = _normalize_url(url)
            if normalized in self.seen_urls:
                continue
            if self.max_pages != 0 and len(self.seen_urls) >= self.max_pages:
                continue
            self.seen_urls.add(normalized)
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
        with self._write_lock:
            n = self._write_counter
            self._write_counter += 1
        out_path = Path(self.output_dir).resolve()
        if subdir:
            out_path = out_path / subdir
        out_path.mkdir(parents=True, exist_ok=True)
        out_path = out_path / f"{n + 1}.{ext}"
        out_path.write_bytes(response.body)

    def _iter_follow_requests(
        self,
        response: Response,
        params: dict[str, Any],
        callback: Any,
    ) -> Any:
        """Yield ScrapingBeeRequests for allowed, same-domain (or allowed-domains) links from response."""
        depth = response.meta.get("depth", 0)
        if self.max_depth != 0 and depth >= self.max_depth:
            return
        if self.max_pages != 0 and len(self.seen_urls) >= self.max_pages:
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
            normalized = _normalize_url(full_url)
            if normalized in self.seen_urls:
                continue
            if self.max_pages != 0 and len(self.seen_urls) >= self.max_pages:
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
        """Log the page, optionally save to output_dir, and yield ScrapingBeeRequests for same-domain links."""
        self.logger.info("Fetched %s (%d bytes)", response.url, len(response.body))
        self._save_response(response)
        yield from self._iter_follow_requests(
            response, dict(self.scrape_params), self.parse
        )

    def parse_discovery(self, response: Response, **kwargs: object) -> Any:
        """Called when we fetched HTML for link discovery. Yield save request for this URL, then discovery for links."""
        self.logger.info("Fetched %s (%d bytes) [discovery]", response.url, len(response.body))
        # Schedule save request for this URL (screenshot/return_text). dont_filter=True: same URL already requested for discovery.
        yield ScrapingBeeRequest(
            response.url,
            params=dict(self.scrape_params),
            headers=self.custom_headers,
            meta=response.meta,
            callback=self.parse_save_only,
            dont_filter=True,
        )
        discovery_params = self._discovery_params or _params_for_discovery(self.scrape_params)
        yield from self._iter_follow_requests(response, discovery_params, self.parse_discovery)

    def parse_save_only(self, response: Response, **kwargs: object) -> Any:
        """Save response (screenshot/return_text) only; no link extraction."""
        self.logger.info("Fetched %s (%d bytes) [save]", response.url, len(response.body))
        self._save_response(response)


USER_AGENT_CLI = "ScrapingBee/CLI"


def default_crawl_output_dir() -> str:
    """Default folder name for crawl output (crawl_<timestamp>)."""
    return "crawl_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _settings_with_scrapingbee(
    api_key: str,
    base_settings: dict | None = None,
    concurrency: int = 16,
) -> dict:
    """Build Scrapy settings with ScrapingBee middleware, API key, and concurrency."""
    from scrapy.settings import Settings

    settings = Settings(base_settings) if base_settings else Settings()
    settings.set("SCRAPINGBEE_API_KEY", api_key)
    settings.set("USER_AGENT", USER_AGENT_CLI)
    settings.set("CONCURRENT_REQUESTS", max(1, concurrency))
    middlewares = dict(settings.get("DOWNLOADER_MIDDLEWARES", {}))
    middlewares[SCRAPINGBEE_MIDDLEWARE] = MIDDLEWARE_PRIORITY
    settings.set("DOWNLOADER_MIDDLEWARES", middlewares)
    return settings


def run_project_spider(
    spider_name: str,
    api_key: str,
    project_path: str | Path | None = None,
    concurrency: int = 16,
) -> None:
    """Run a Scrapy project spider with ScrapingBee middleware and API key injected."""
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
        settings = _settings_with_scrapingbee(api_key, base_settings, concurrency=concurrency)
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
) -> None:
    """Run the built-in generic spider: start from URLs and follow links.
    By default only same-domain links are followed; use allowed_domains or allow_external_domains to change.
    If output_dir is set, each response is saved as a separate file.
    """
    if not urls:
        raise ValueError("At least one URL is required")
    settings = _settings_with_scrapingbee(api_key, concurrency=concurrency)
    settings.set("LOG_LEVEL", "INFO")
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
    )
    process.start()
