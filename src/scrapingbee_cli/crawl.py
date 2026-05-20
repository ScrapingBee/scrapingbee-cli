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
from .batch import _batch_subdir_for_extension, extension_for_crawl

if TYPE_CHECKING:
    from scrapy import Request

SCRAPINGBEE_MIDDLEWARE = "scrapy_scrapingbee.ScrapingBeeMiddleware"
MIDDLEWARE_PRIORITY = 725


class _CrawlerReactorAlreadyUsedError(RuntimeError):
    """Raised when Twisted's reactor has already been started + stopped
    in this Python process and can't be re-used for another crawl. The
    REPL surfaces a friendly message asking the user to restart the
    session, rather than letting Scrapy's raw error bubble up.
    """


def stop_running_reactor() -> bool:
    """Thread-safely stop the running Twisted reactor if it's currently
    running a crawl. Returns True if a stop was scheduled, False if no
    reactor is currently running (so the caller can fall through to its
    other Ctrl+C paths).

    Used by the REPL's Ctrl+C handler — the Twisted reactor in the
    worker thread is blocked in a C-level ``epoll``/``kqueue``/``select``
    waiting on sockets, so neither ``PyThreadState_SetAsyncExc`` nor
    ``asyncio.Task.cancel`` reaches it. ``reactor.callFromThread`` is
    the blessed cross-thread escape hatch: it wakes the selector via
    the reactor's self-pipe and schedules the callback on the reactor
    thread, where ``reactor.stop()`` can run safely.
    """
    try:
        from twisted.internet import reactor
    except Exception:
        return False
    if not getattr(reactor, "running", False):
        return False
    try:
        # ``callFromThread`` / ``stop`` are populated dynamically when
        # the reactor is installed; the static module stub doesn't
        # carry them. ``getattr`` keeps the type checker quiet without
        # rerouting the runtime hot path.
        cft = getattr(reactor, "callFromThread", None)
        stop = getattr(reactor, "stop", None)
        if cft is None or stop is None:
            return False
        cft(stop)
        return True
    except Exception:
        return False


def _ensure_reactor_usable() -> None:
    """Sanity check before we hand a new crawl to Twisted.

    Twisted's reactor is a process-wide singleton — once ``reactor.run()``
    returns (either naturally or because the user cancelled the crawl)
    the reactor's ``_startedBefore`` flag stays True, and calling
    ``run()`` again raises ``ReactorNotRestartable``. The REPL invokes
    ``run_urls_spider`` / ``run_project_spider`` in a worker thread per
    command, so the second crawl in a REPL session always trips this.

    We INSPECT the reactor via ``sys.modules`` rather than importing
    ``twisted.internet.reactor`` ourselves — a bare import triggers the
    default reactor (SelectReactor on macOS) to install eagerly, which
    then conflicts with Scrapy's ``TWISTED_REACTOR`` setting that wants
    ``AsyncioSelectorReactor``. The result was every crawl failing
    immediately with ``RuntimeError: The installed reactor … does not
    match`` before any signal could fire.

    Detect the dead-reactor state early and raise a clean error the
    REPL can render as "Restart the REPL to crawl again" instead of a
    multi-line Twisted traceback. (A true fix would spawn each crawl
    in a subprocess; that's a follow-up.)
    """
    import sys as _sys
    reactor = _sys.modules.get("twisted.internet.reactor")
    if reactor is None:
        return  # No reactor has been installed yet, nothing to check.
    if getattr(reactor, "_startedBefore", False):
        raise _CrawlerReactorAlreadyUsedError(
            "Crawls in this REPL session have ended. Twisted's reactor "
            "is single-shot per process — please run ``:q`` and relaunch "
            "scrapingbee to crawl again."
        )


def _target_url_from_request(request) -> str:
    """Extract the user-facing target URL from a Scrapy request.

    ``scrapy-scrapingbee`` rewrites outgoing requests so they hit
    ``app.scrapingbee.com/api/v1/?api_key=…&url=…``. Stick that URL in
    the REPL's live status line and the user sees their API key in
    plain text plus a totally unhelpful host — they want their own
    target URL. The request's ``meta["scrapingbee"]["url"]`` (set by
    the middleware before it rewrites the request) is the cleanest
    source; if that's missing we fall back to decoding the ``url``
    query param from ``request.url``, and to ``request.url`` itself if
    even that fails (so the line stays populated rather than going
    blank).

    Output is always a clean printable string — non-printable bytes
    that sometimes show up in target URLs (e.g. screenshot-mode pages
    with binary blobs in the path) are stripped so the status widget
    never renders mojibake.
    """
    raw = ""
    try:
        meta_url = (request.meta or {}).get("scrapingbee_target_url")
        if meta_url:
            raw = meta_url
    except Exception:
        pass
    if not raw:
        raw = getattr(request, "url", "") or ""
        if "app.scrapingbee.com" in raw and "url=" in raw:
            try:
                from urllib.parse import parse_qs, unquote, urlparse
                qs = parse_qs(urlparse(raw).query)
                target = qs.get("url", [None])[0]
                if target:
                    raw = unquote(target, errors="replace")
            except Exception:
                pass
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    # Keep only ASCII printable code points (32–126). URLs are
    # supposed to be 7-bit ASCII with %-encoding for everything
    # else; anything outside that range here is decoded garbage
    # (sites like crawler-test.com host pages with deliberate
    # binary blobs in their paths for scraper-stress-testing).
    # ``isprintable()`` alone passes too much through — combining
    # marks, zero-width chars, exotic whitespace all render weird
    # in the status widget.
    return "".join(ch for ch in raw if 32 <= ord(ch) <= 126)


def _install_signal_handlers() -> bool:
    """Whether Scrapy / Twisted should install Unix signal handlers.

    Returns False when running inside the REPL — there we run crawl in a
    worker thread (to avoid asyncio.run conflicting with prompt_toolkit's
    main-thread loop), and ``signal.signal()`` is restricted to the main
    thread, so any attempt to install handlers raises ``ValueError:
    signal only works in main thread of the main interpreter``. The REPL
    provides its own Ctrl+C handling that injects ``KeyboardInterrupt``
    into the worker thread, so we don't need Scrapy's handlers there.

    Returns True for direct ``scrapingbee crawl ...`` invocations — those
    run on the main thread and benefit from Twisted's graceful shutdown.
    """
    try:
        from .theme import is_repl_mode
        return not is_repl_mode()
    except Exception:
        return True


def _maybe_set_repl_log_file(settings) -> str | None:
    """In REPL mode (or a REPL-spawned subprocess), pipe the full Scrapy
    log to a file on disk and silence the noisy ``py.warnings`` logger
    so the in-flight crawl UI isn't drowned in deprecation tracebacks.

    The REPL's virtual scrollback caps at ~10K lines and drops the
    oldest 10% when full, so long crawls would otherwise lose their
    history. ``LOG_FILE`` mirrors everything Scrapy emits (at the
    configured ``LOG_LEVEL``) to ``~/.cache/scrapingbee-cli/crawl.log``;
    the user can open it any time with ``:view crawl``.

    ``py.warnings`` is the logger Scrapy uses to forward Python
    ``warnings.warn`` calls. Multi-line deprecation tracebacks (Scrapy
    nagging about old middleware APIs etc.) belong in the file, not on
    screen — we raise THAT specific logger to ERROR so those entries
    stop reaching the terminal stream while the rest of Scrapy's
    routine logging continues at its configured level.
    """
    try:
        from .theme import is_repl_mode
        in_repl = is_repl_mode() or os.environ.get("SCRAPINGBEE_FROM_REPL") == "1"
        if not in_repl:
            return None
        log_dir = Path.home() / ".cache" / "scrapingbee-cli"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "crawl.log"
        settings.set("LOG_FILE", str(log_path))
        settings.set("LOG_FILE_APPEND", False)  # fresh log per run
        try:
            import logging as _logging
            _logging.getLogger("py.warnings").setLevel(_logging.ERROR)
        except Exception:
            pass
        return str(log_path)
    except Exception:
        return None

# 0 means unlimited
DEFAULT_MAX_DEPTH = 0
DEFAULT_MAX_PAGES = 0

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
    return_page_markdown -> md; return_page_text -> txt;
    json_response / extract_rules / ai_extract_rules / ai_query -> json.
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
    # extract_rules, ai_extract_rules, ai_query always return JSON regardless of URL.
    # Without this, URLs ending in .html would be saved as .html despite JSON body
    # (the URL-path heuristic in extension_for_crawl wins before body sniff).
    if params.get("extract_rules") or params.get("ai_extract_rules") or params.get("ai_query"):
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
    # All three screenshot params produce PNG output unless wrapped in JSON.
    screenshot_requested = (
        _param_truthy(scrape_params, "screenshot")
        or _param_truthy(scrape_params, "screenshot_full_page")
        or scrape_params.get("screenshot_selector")
    )
    if screenshot_requested and not _param_truthy(scrape_params, "json_response"):
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
        known_total: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name=name, **kwargs)
        # Optional: when the caller knows up front how many pages will be
        # fetched (e.g. sitemap mode), we surface a batch-style honeycomb
        # progress bar in the REPL. Left None for open-ended crawls.
        self._known_total: int | None = (
            int(known_total) if known_total and known_total > 0 else None
        )
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
        # Save requests that have been dispatched but not yet completed.
        # Used together with ``_save_count`` to enforce ``max_pages``
        # tightly even when several discovery callbacks fire saves
        # before the first save completes (without this we overshoot
        # the cap by ``concurrency``).
        self._save_pending = 0
        # Pool-based discovery for binary modes (screenshot / extract /
        # ai / return_page_text). Discovery callbacks accumulate URLs
        # into ``_save_queue`` without firing a save per page; once the
        # queue contains >= ``max_pages`` candidates we flip
        # ``_discovery_done`` and dispatch all save requests in one go,
        # then drop any further discoveries that come back late. This
        # avoids paying for an HTML discovery per saved page when a
        # handful of pages already expose more URLs than the cap.
        # ``_save_queue_next`` is the index of the next un-dispatched
        # URL in ``_save_queue`` — used by ``_on_save_error`` to backfill
        # from the remainder of the pool when a dispatched save fails,
        # so a few errors don't leave the user with < max_pages files
        # despite there being more candidates available.
        self._save_queue: list[str] = []
        self._save_queue_set: set[str] = set()
        self._save_queue_next: int = 0
        self._discovery_done: bool = False
        self._fetch_count = 0
        # Live-status counters surfaced to the REPL via theme._crawl_status.
        # Only populated under REPL mode; the signal handlers below early-
        # exit otherwise so the standalone CLI path stays unchanged.
        self._queued_count = 0
        # Counted at signal time (response_received), independent of the
        # parse callbacks that increment ``_fetch_count`` later in the
        # pipeline. Used for the dim-row "X fetched" indicator and the
        # honeycomb progress widget so the count advances the instant a
        # response lands, not when its body is parsed.
        self._response_count = 0

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        """Standard Scrapy hook — instantiate the spider AND wire signal
        handlers that push live status into ``theme._crawl_status`` so
        the REPL's dim row can show the current URL + fetched count
        in real time. Outside REPL mode the handlers are no-ops.
        """
        spider = super().from_crawler(crawler, *args, **kwargs)
        try:
            from scrapy import signals as _scrapy_signals

            from .theme import is_repl_mode

            # Stash the crawler so signal handlers can dispatch new
            # requests via ``crawler.engine.crawl`` (needed from
            # ``spider_idle`` to flush the pool when discovery exhausts
            # without saturating). ``Spider`` doesn't declare this slot
            # so we use ``setattr`` to keep the type checker happy.
            setattr(spider, "_crawler", crawler)

            # The pool-based discovery flow needs to flush queued URLs
            # at spider_idle (when discovery exhausts before reaching
            # ``max_pages``). Wire this regardless of REPL mode — it's
            # a credit-saving optimisation, not a UI feature.
            crawler.signals.connect(
                spider._on_spider_idle, signal=_scrapy_signals.spider_idle
            )

            # Register signal handlers when running inside the REPL
            # (legacy in-process path) OR when the parent REPL spawned
            # us as a subprocess and set the status-file env var (the
            # new subprocess-per-crawl path). The handlers themselves
            # call ``update_crawl_status`` which atomically mirrors
            # state to the file if the env var is set.
            _want_status = is_repl_mode() or bool(
                os.environ.get("SCRAPINGBEE_CRAWL_STATUS_FILE")
            )
            if _want_status:
                crawler.signals.connect(
                    spider._on_spider_opened, signal=_scrapy_signals.spider_opened
                )
                crawler.signals.connect(
                    spider._on_request_scheduled,
                    signal=_scrapy_signals.request_scheduled,
                )
                crawler.signals.connect(
                    spider._on_request_reached,
                    signal=_scrapy_signals.request_reached_downloader,
                )
                crawler.signals.connect(
                    spider._on_response_received,
                    signal=_scrapy_signals.response_received,
                )
                crawler.signals.connect(
                    spider._on_spider_closed, signal=_scrapy_signals.spider_closed
                )
        except Exception:
            pass
        return spider

    # ── Live-status signal handlers (REPL mode only) ──────────────────────
    def _on_spider_opened(self, spider) -> None:
        try:
            from .theme import update_crawl_status, update_progress_state
            update_crawl_status(
                current_url=None, fetched=0, queued=0, saved=0, phase="discovering",
            )
            # If we already know the total (sitemap mode), seed the
            # progress widget at 0/total so the user sees the bar from
            # frame one.
            if self._known_total is not None and self._known_total > 0:
                update_progress_state(0, self._known_total)
        except Exception:
            pass

    def _on_request_scheduled(self, request, spider) -> None:
        try:
            self._queued_count += 1
            from .theme import update_crawl_status
            update_crawl_status(queued=self._queued_count)
        except Exception:
            pass

    def _on_request_reached(self, request, spider) -> None:
        try:
            from .theme import update_crawl_status
            # Scrapy sees the outgoing proxy URL
            # (``app.scrapingbee.com/api/v1/?api_key=…&url=…``) — that's
            # leaky (API key) and not what the user thinks of as "their"
            # URL. Pull the target out of the ``url`` query param so the
            # status widget reads naturally: ``fetching: https://example.com``.
            display_url = _target_url_from_request(request)
            update_crawl_status(current_url=display_url)
        except Exception:
            pass

    def _on_response_received(self, response, request, spider) -> None:
        try:
            self._response_count += 1
            from .theme import update_crawl_status, update_progress_state
            update_crawl_status(
                fetched=self._response_count,
                saved=self._save_count,
                phase="fetching",
            )
            if self._known_total is not None and self._known_total > 0:
                update_progress_state(
                    min(self._response_count, self._known_total),
                    self._known_total,
                )
        except Exception:
            pass

    def _on_spider_closed(self, spider, reason) -> None:
        try:
            from .theme import clear_crawl_status, clear_progress_state
            clear_crawl_status()
            clear_progress_state()
        except Exception:
            pass

    def _on_spider_idle(self, spider) -> None:
        """Flush the pool when discovery exhausts before saturation.

        Pool-based binary mode only dispatches saves once the queue
        reaches ``max_pages``. If the site is smaller than the cap (or
        ``max_pages`` is 0 / unlimited), the queue never reaches the
        threshold and would never trigger save dispatch — the spider
        would close with the pool full and zero files saved.

        ``spider_idle`` fires when the scheduler is empty and no
        requests are in flight. We use it to commit whatever URLs we
        gathered: dispatch save requests for every queued URL (capped
        at ``max_pages`` if set), then raise ``DontCloseSpider`` so
        Scrapy waits for the saves to complete before shutting down.

        Only relevant for binary-mode crawls (the same-mode and
        HTML-save-pattern flows save in place, no pool involved).
        """
        if self._discovery_done:
            return
        if not _requires_discovery_phase(self.scrape_params):
            return
        if not self._save_queue:
            return
        # Resolve the engine BEFORE latching ``_discovery_done`` — if
        # the engine isn't available (very unlikely by the time
        # spider_idle fires, but worth being defensive), bail without
        # leaving the flag set, so a later idle tick gets another
        # chance instead of permanently skipping flush.
        engine = getattr(getattr(self, "_crawler", None), "engine", None)
        if engine is None:
            return
        self._discovery_done = True
        budget = (
            min(self.max_pages, len(self._save_queue))
            if self.max_pages
            else len(self._save_queue)
        )
        for url in self._save_queue[:budget]:
            self._save_pending += 1
            self._save_queue_next += 1
            try:
                engine.crawl(self._make_save_request(url), spider)
            except Exception:
                if self._save_pending > 0:
                    self._save_pending -= 1
        from scrapy.exceptions import DontCloseSpider
        raise DontCloseSpider

    def _push_saved_status(self) -> None:
        """Re-push the live ``saved`` count after a successful save,
        and tear the spider down once we've hit ``max_pages``.

        ``_on_response_received`` (Scrapy signal) fires BEFORE the
        ``parse``/``_parse_save_only`` callback writes the file, so the
        widget's ``saved`` count always lags by one until the next
        response arrives. With ``--max-pages N`` the spider closes
        before that next response, leaving a stale ``N fetched
        N-1 saved`` reading on screen until ``_on_spider_closed``
        clears the widget. Calling this right after the save commits
        keeps the display honest.

        Once the cap is reached we also raise ``CloseSpider`` so the
        engine drops anything still queued (e.g. the ~N follow-up
        discoveries that the seed callback already yielded). Without
        this the spider would happily keep fetching no-op pages until
        the framework safety cap ``CLOSESPIDER_PAGECOUNT`` kicks in —
        burning credits the user expects ``--max-pages`` to bound.
        """
        try:
            from .theme import update_crawl_status
            update_crawl_status(saved=self._save_count)
        except Exception:
            pass
        if self.max_pages != 0 and self._save_count >= self.max_pages:
            from scrapy.exceptions import CloseSpider
            raise CloseSpider("max_pages")

    def _on_request_error(self, failure) -> None:
        """Swallow request-level errors so one bad URL doesn't kill the
        whole crawl. ``scrapy_scrapingbee`` ships an errback that
        crashes on binary error responses (``response.text`` raises
        ``AttributeError`` when the body isn't decodable as text —
        which happens any time the API returns a non-200 in screenshot
        mode). Attaching our own errback to every request short-
        circuits that and just logs the failure.
        """
        try:
            req = getattr(failure, "request", None)
            url = getattr(req, "url", "?") if req is not None else "?"
            exc = type(failure.value).__name__ if hasattr(failure, "value") else "error"
            self.logger.warning("Skipped %s (%s)", url, exc)
        except Exception:
            pass
        return None

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
        # Two flows:
        #   1. "Same-mode": one request per page; the response is both saved
        #      and parsed for outgoing links. Works only when scrape_params
        #      yield HTML/JSON-with-body (no screenshot/extract/etc).
        #   2. "Discovery-first": fetch each page in HTML mode for link
        #      extraction, and (if it should be saved) fire a SECOND
        #      request with the user's full scrape_params to obtain the
        #      saved artifact (PNG, extract-rules JSON, etc).
        # Discovery-first is required whenever the user asks for binary or
        # non-link-bearing output, AND whenever --save-pattern is set
        # (so the cheap HTML pass can find links without spending the full
        # per-page cost on every crawled URL).
        use_discovery_flow = self._save_re is not None or _requires_discovery_phase(
            self.scrape_params
        )
        for url in self.start_urls:
            normalized = _normalize_url(url)
            if normalized in self.seen_urls:
                continue
            if self.max_pages != 0 and self._save_count >= self.max_pages:
                continue
            self.seen_urls.add(normalized)
            if use_discovery_flow:
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
                errback=self._on_request_error,
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

    def _iter_follow_urls(self, response: Response) -> Any:
        """Yield ``(url, next_depth)`` for each link in ``response`` that
        passes the spider's URL filters (scheme, ASCII, domain
        allow-list, include/exclude regex, dedup). Centralised so the
        same filter chain is used by both the request-yielding flow
        (``_iter_follow_requests``) and the pool-based discovery flow
        (``_parse_crawl_and_save`` for binary modes).
        """
        depth = response.meta.get("depth", 0)
        if self.max_depth != 0 and depth >= self.max_depth:
            return
        from urllib.parse import unquote as _unquote
        for href in _extract_hrefs_from_response(response):
            if not href or href.startswith(("#", "mailto:", "javascript:")):
                continue
            full_url = response.urljoin(href)
            parsed = urlparse(full_url)
            if parsed.scheme not in ("http", "https"):
                continue
            # Skip URLs whose decoded path/query carries non-printable
            # or non-ASCII bytes. Such URLs (common on the
            # crawler-test.com fixture pages) trip a known
            # ``scrapy_scrapingbee`` bug: when ScrapingBee's API
            # returns 500 for the malformed URL, the library's errback
            # tries to format the error using ``response.text`` —
            # which raises ``AttributeError`` on a binary
            # screenshot-mode response and kills the whole spider.
            # Filtering them out keeps the crawl going.
            try:
                _path_tail = _unquote(
                    (parsed.path or "") + (parsed.query or ""),
                    errors="replace",
                )
                if not all(32 <= ord(ch) <= 126 for ch in _path_tail):
                    continue
            except Exception:
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
            yield full_url, depth + 1

    def _iter_follow_requests(
        self,
        response: Response,
        params: dict[str, Any],
        callback: Any,
    ) -> Any:
        """Yield ScrapingBeeRequests for allowed links from response.
        Used by the same-mode ``parse()`` flow (HTML crawl) and by the
        HTML-save-pattern branch of ``_parse_crawl_and_save``.
        """
        # max_pages = max saved pages. Stop queueing follow-ups once
        # the budget (already-saved + in-flight saves) is committed.
        if (
            self.max_pages != 0
            and self._save_count + self._save_pending >= self.max_pages
        ):
            return
        for full_url, next_depth in self._iter_follow_urls(response):
            yield ScrapingBeeRequest(
                full_url,
                params=params,
                headers=self.custom_headers,
                meta={"depth": next_depth},
                callback=callback,
                errback=self._on_request_error,
            )

    def _make_save_request(self, url: str) -> ScrapingBeeRequest:
        """Build a save request (full ``scrape_params``) for ``url``.
        Used in the pool-based discovery flow once we've accumulated
        enough candidate URLs. Caller is responsible for incrementing
        ``_save_pending`` before yielding.
        """
        return ScrapingBeeRequest(
            url,
            params=dict(self.scrape_params),
            headers=self.custom_headers,
            callback=self._parse_save_only,
            errback=self._on_save_error,
            dont_filter=True,
            priority=10,
        )

    def parse(self, response: Response, **kwargs: object) -> Any:
        """Same-mode callback: the response is both saved and parsed for
        outgoing links. Only used when scrape_params return HTML or
        json_response with a parseable body — binary/extract modes are
        routed through ``_parse_crawl_and_save`` from ``start_requests``.
        """
        from scrapy.exceptions import CloseSpider

        self._fetch_count += 1
        self.logger.info("Fetched %s (%d bytes)", response.url, len(response.body))
        try:
            self._save_response(response)
            self._save_count += 1
            self._push_saved_status()
        except CloseSpider:
            # The cap-reached signal from _push_saved_status MUST
            # propagate to Scrapy's engine — catching it as a generic
            # exception below would silence the shutdown and let the
            # already-queued follow requests keep firing.
            raise
        except Exception as e:
            self.logger.warning("Failed to save %s: %s", response.url, e)
        try:
            hrefs = _extract_hrefs_from_response(response)
        except Exception:
            hrefs = []
        if hrefs:
            yield from self._iter_follow_requests(
                response, dict(self.scrape_params), self.parse
            )

    def _parse_crawl_and_save(self, response: Response, **kwargs: object) -> Any:
        """Discovery-first callback. Two flows live here:

        * **Binary / extract modes** (``_requires_discovery_phase``):
          POOL-BASED. Each discovery response contributes its own URL
          and its outbound links to ``_save_queue``. We do NOT fire a
          save per page. Once the queue reaches ``max_pages`` we flip
          ``_discovery_done``, dispatch one save request per queued
          URL up to the cap, and stop discovering. Save credits paid
          per pre-cap discovery: 0. Compare the old "save+follow each
          page" flow, which paid one full-param fetch per saved page
          PLUS one HTML discovery per saved page — roughly 2× credits.

        * **HTML save-pattern mode**: SAVE-IN-PLACE. The response IS
          the HTML we want to save (the user's ``scrape_params``
          already yield HTML), so we write it directly and follow
          links. No separate save request needed.
        """
        from scrapy.exceptions import CloseSpider as _CloseSpider

        self._fetch_count += 1
        self.logger.info("Fetched %s (%d bytes) [crawl]", response.url, len(response.body))
        binary_mode = _requires_discovery_phase(self.scrape_params)

        if not binary_mode:
            # ── HTML save-pattern flow (unchanged) ───────────────────
            save_this = (self._save_re is None) or bool(
                self._save_re.search(response.url)
            )
            within_cap = (
                self.max_pages == 0
                or self._save_count + self._save_pending < self.max_pages
            )
            if save_this and within_cap:
                try:
                    self._save_response(response)
                    self._save_count += 1
                    self._push_saved_status()
                except _CloseSpider:
                    raise
                except Exception as e:
                    self.logger.warning("Failed to save %s: %s", response.url, e)
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
            return

        # ── Binary / extract mode: pool-based discovery ──────────────
        if self._discovery_done:
            # A late-arriving discovery response after saturation. The
            # save dispatches for the first ``max_pages`` URLs are
            # already in flight; this page contributes nothing new.
            return

        # Add the current URL to the save queue (if it passes the
        # save filter) so the seed and every successfully-discovered
        # page becomes a save candidate. ``seen_urls`` and the pool
        # both dedup on the normalized form so a trailing-slash
        # difference between the seed and an extracted link doesn't
        # produce two entries for the same logical page.
        if (self._save_re is None) or bool(self._save_re.search(response.url)):
            norm = _normalize_url(response.url)
            if norm not in self._save_queue_set:
                self._save_queue.append(response.url)
                self._save_queue_set.add(norm)

        # Extract links from this page and grow both queues.
        new_discovery_targets: list[tuple[str, int]] = []
        for full_url, next_depth in self._iter_follow_urls(response):
            new_discovery_targets.append((full_url, next_depth))
            if (self._save_re is None) or bool(self._save_re.search(full_url)):
                norm = _normalize_url(full_url)
                if norm not in self._save_queue_set:
                    self._save_queue.append(full_url)
                    self._save_queue_set.add(norm)

        # Saturation: pool has enough candidates → stop discovery,
        # dispatch saves for the first ``max_pages`` URLs in queue
        # order (seed first, then breadth-first by discovery). The
        # remaining URLs stay in the queue as reserves — ``_on_save_error``
        # pulls from them if a dispatched save fails.
        if self.max_pages and len(self._save_queue) >= self.max_pages:
            self._discovery_done = True
            for url in self._save_queue[: self.max_pages]:
                self._save_pending += 1
                self._save_queue_next += 1
                yield self._make_save_request(url)
            return

        # Still hungry — yield discoveries for the newly-extracted URLs.
        discovery_params = _params_for_discovery(self.scrape_params)
        for full_url, next_depth in new_discovery_targets:
            yield ScrapingBeeRequest(
                full_url,
                params=discovery_params,
                headers=self.custom_headers,
                meta={"depth": next_depth},
                callback=self._parse_crawl_and_save,
                errback=self._on_request_error,
            )

    def _parse_save_only(self, response: Response, **kwargs: object) -> Any:
        """Save the response (fetched with full params). No link following."""
        from scrapy.exceptions import CloseSpider

        self.logger.info("Fetched %s (%d bytes) [save]", response.url, len(response.body))
        try:
            self._save_response(response)
            self._save_count += 1
            self._push_saved_status()
        except CloseSpider:
            raise
        except Exception as e:
            self.logger.warning("Failed to save %s: %s", response.url, e)
        finally:
            # ``finally`` runs even when CloseSpider is re-raised, so the
            # pending counter is still decremented cleanly during shutdown.
            if self._save_pending > 0:
                self._save_pending -= 1

    def _on_save_error(self, failure) -> None:
        """Errback for save requests — decrement the pending counter,
        log, and backfill from the pool if the user's cap isn't yet
        committed. Without backfill, a handful of network failures
        would silently shrink the user's effective ``max_pages``.
        """
        if self._save_pending > 0:
            self._save_pending -= 1
        # If we have reserves in ``_save_queue`` AND the cap (already-
        # saved + still-in-flight) hasn't been committed yet, dispatch
        # a replacement save. Only relevant when discovery is done
        # (i.e. we've already started flushing the queue).
        try:
            if (
                self._discovery_done
                and self.max_pages
                and self._save_queue_next < len(self._save_queue)
                and self._save_count + self._save_pending < self.max_pages
            ):
                engine = getattr(
                    getattr(self, "_crawler", None), "engine", None
                )
                if engine is not None:
                    url = self._save_queue[self._save_queue_next]
                    self._save_queue_next += 1
                    self._save_pending += 1
                    try:
                        engine.crawl(self._make_save_request(url), self)
                    except Exception:
                        if self._save_pending > 0:
                            self._save_pending -= 1
        except Exception:
            pass
        return self._on_request_error(failure)


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
        from .theme import is_repl_mode as _is_repl_mode
        _repl_log_active = _is_repl_mode() or os.environ.get("SCRAPINGBEE_FROM_REPL") == "1"
        if _repl_log_active:
            # Verbose file log, quiet stream — see run_urls_spider for why.
            settings.set("LOG_LEVEL", "INFO")
        log_path = _maybe_set_repl_log_file(settings)
        if log_path:
            click.echo(
                f"REPL mode: full crawl log → {log_path}  "
                f"(use `:view crawl` to scroll through it)",
                err=True,
            )
        _ensure_reactor_usable()
        process = CrawlerProcess(settings)
        if _repl_log_active:
            import logging as _logging
            for _h in _logging.getLogger().handlers:
                if isinstance(_h, _logging.FileHandler):
                    continue
                if isinstance(_h, _logging.StreamHandler):
                    _h.setLevel(_logging.WARNING)
        process.crawl(spider_name)
        process.start(install_signal_handlers=_install_signal_handlers())
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
    known_total: int | None = None,
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
    # In REPL mode we want the *file* log to be verbose (so ``:view crawl``
    # is actually useful) while keeping the *stream* output quiet (so the
    # REPL scrollback isn't drowned in per-request INFO chatter). We do
    # that by raising LOG_LEVEL to INFO globally and then bumping ONLY
    # the StreamHandler back up to WARNING after CrawlerProcess wires up
    # the handlers (see below). Outside REPL there's no file log, so the
    # stream handler picks up LOG_LEVEL directly — keep that at WARNING.
    from .theme import is_repl_mode as _is_repl_mode
    _repl_log_active = _is_repl_mode() or os.environ.get("SCRAPINGBEE_FROM_REPL") == "1"
    settings.set("LOG_LEVEL", "INFO" if _repl_log_active else "WARNING")
    if max_pages > 0:
        # The authoritative cap is the spider's ``_save_count >=
        # max_pages`` check (in both ``_iter_follow_requests`` and the
        # per-page save dispatch in ``_parse_crawl_and_save``). Scrapy's
        # ``CLOSESPIDER_PAGECOUNT`` counts EVERY response — in the
        # discovery-flow modes that fire one HTML pass plus one save
        # request per page, the response count can easily reach
        # ``max_pages × N`` where N depends on how many hrefs a typical
        # page exposes. Set the framework cap to a generous multiple
        # so it never fires before the spider's own cap stops queuing.
        use_discovery_flow = bool(save_pattern) or _requires_discovery_phase(
            scrape_params or {}
        )
        framework_cap = max_pages * 20 if use_discovery_flow else max_pages
        settings.set("CLOSESPIDER_PAGECOUNT", framework_cap)
    log_path = _maybe_set_repl_log_file(settings)
    if log_path:
        click.echo(
            f"REPL mode: full crawl log → {log_path}  "
            f"(use `:view crawl` to scroll through it)",
            err=True,
        )
    _ensure_reactor_usable()
    process = CrawlerProcess(settings)
    # CrawlerProcess just configured the root logger with handlers
    # honouring LOG_LEVEL. In REPL mode we asked for INFO so the file
    # captures everything, but the StreamHandler also got INFO and
    # would spam the REPL scrollback. Demote ONLY the StreamHandler
    # (not the FileHandler, which is a StreamHandler subclass) so the
    # file stays verbose while stderr stays clean.
    if _repl_log_active:
        import logging as _logging
        for _h in _logging.getLogger().handlers:
            if isinstance(_h, _logging.FileHandler):
                continue
            if isinstance(_h, _logging.StreamHandler):
                _h.setLevel(_logging.WARNING)
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
        known_total=known_total,
    )
    process.start(install_signal_handlers=_install_signal_handlers())
