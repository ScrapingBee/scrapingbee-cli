"""HTTP client for ScrapingBee API (async, aiohttp)."""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from .config import BASE_URL


def _clean_params(params: dict) -> dict:
    """Drop None and empty string values for API query/body params."""
    return {k: v for k, v in params.items() if v is not None and v != ""}


class Client:
    """ScrapingBee API client (async, use as context manager)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = BASE_URL,
        timeout: int = 150,
        connector_limit: int | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._connector_limit = connector_limit
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> Client:
        connector = (
            aiohttp.TCPConnector(limit=self._connector_limit)
            if self._connector_limit is not None
            else None
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": "ScrapingBee/CLI"},
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("Client must be used as async with Client(...) as client")
        return self._session

    async def _get(
        self,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict, int]:
        params = _clean_params(params)
        params.setdefault("api_key", self.api_key)
        url = f"{self.base_url}{path}" if path else self.base_url
        session = self._ensure_session()
        req_kwargs: dict[str, Any] = {"params": params}
        if headers:
            req_kwargs["headers"] = headers
        async with session.get(url, **req_kwargs) as resp:
            body = await resp.read()
            out_headers = dict(resp.headers)
            return body, out_headers, resp.status

    async def _request(
        self,
        method: str,
        path: str,
        params: dict,
        data: str | None = None,
        content_type: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict, int]:
        params = _clean_params(params)
        params.setdefault("api_key", self.api_key)
        url = f"{self.base_url}{path}" if path else self.base_url
        session = self._ensure_session()
        req_kwargs: dict[str, Any] = {"params": params}
        if headers:
            req_kwargs["headers"] = headers
        if data is not None:
            req_kwargs["data"] = data
            if content_type:
                existing = req_kwargs.get("headers")
                req_kwargs["headers"] = (
                    {**existing, "Content-Type": content_type}
                    if isinstance(existing, dict)
                    else {"Content-Type": content_type}
                )
        async with session.request(method, url, **req_kwargs) as resp:
            body = await resp.read()
            return body, dict(resp.headers), resp.status

    @staticmethod
    def _bool(val: bool | None) -> str | None:
        if val is None:
            return None
        return "true" if val else "false"

    async def scrape(
        self,
        url: str,
        method: str = "GET",
        render_js: bool | None = None,
        js_scenario: str | None = None,
        wait: int | None = None,
        wait_for: str | None = None,
        wait_browser: str | None = None,
        block_ads: bool | None = None,
        block_resources: bool | None = None,
        window_width: int | None = None,
        window_height: int | None = None,
        premium_proxy: bool | None = None,
        stealth_proxy: bool | None = None,
        country_code: str | None = None,
        own_proxy: str | None = None,
        forward_headers: bool | None = None,
        forward_headers_pure: bool | None = None,
        custom_headers: dict[str, str] | None = None,
        json_response: bool | None = None,
        screenshot: bool | None = None,
        screenshot_selector: str | None = None,
        screenshot_full_page: bool | None = None,
        return_page_source: bool | None = None,
        return_page_markdown: bool | None = None,
        return_page_text: bool | None = None,
        extract_rules: str | None = None,
        ai_query: str | None = None,
        ai_selector: str | None = None,
        ai_extract_rules: str | None = None,
        session_id: int | None = None,
        timeout: int | None = None,
        cookies: str | None = None,
        device: str | None = None,
        custom_google: bool | None = None,
        transparent_status_code: bool | None = None,
        scraping_config: str | None = None,
        body: str | None = None,
        content_type: str | None = None,
        **kwargs: Any,
    ) -> tuple[bytes, dict, int]:
        params = {"url": url}
        if method and method.upper() != "GET":
            params["method"] = method.upper()
        for k, v in [
            ("render_js", self._bool(render_js)),
            ("js_scenario", js_scenario),
            ("wait", wait if wait else None),
            ("wait_for", wait_for),
            ("wait_browser", wait_browser),
            ("block_ads", self._bool(block_ads)),
            ("block_resources", self._bool(block_resources)),
            ("window_width", window_width if window_width else None),
            ("window_height", window_height if window_height else None),
            ("premium_proxy", self._bool(premium_proxy)),
            ("stealth_proxy", self._bool(stealth_proxy)),
            ("country_code", country_code),
            ("own_proxy", own_proxy),
            ("forward_headers", self._bool(forward_headers)),
            ("forward_headers_pure", self._bool(forward_headers_pure)),
            ("json_response", self._bool(json_response)),
            ("screenshot", self._bool(screenshot)),
            ("screenshot_selector", screenshot_selector),
            ("screenshot_full_page", self._bool(screenshot_full_page)),
            ("return_page_source", self._bool(return_page_source)),
            ("return_page_markdown", self._bool(return_page_markdown)),
            ("return_page_text", self._bool(return_page_text)),
            ("extract_rules", extract_rules),
            ("ai_query", ai_query),
            ("ai_selector", ai_selector),
            ("ai_extract_rules", ai_extract_rules),
            ("session_id", session_id if session_id else None),
            ("timeout", timeout if timeout else None),
            ("cookies", cookies),
            ("device", device),
            ("custom_google", self._bool(custom_google)),
            ("transparent_status_code", self._bool(transparent_status_code)),
            ("scraping_config", scraping_config),
        ]:
            if v is not None:
                params[k] = str(v) if not isinstance(v, str) else v
        req_headers = None
        if custom_headers:
            req_headers = {f"Spb-{k}": v for k, v in custom_headers.items()}
        method_upper = (method or "GET").upper()
        if method_upper == "GET":
            return await self._get("", params, headers=req_headers)
        params = _clean_params(params)
        params["api_key"] = self.api_key
        req_headers_merged = dict(req_headers) if req_headers else {}
        if body is not None and content_type:
            req_headers_merged["Content-Type"] = content_type
        return await self._request(
            method_upper,
            "",
            params,
            data=body,
            content_type=None,
            headers=req_headers_merged or None,
        )

    async def usage(self) -> tuple[bytes, dict, int]:
        return await self._get("/usage", {"api_key": self.api_key})

    async def google_search(
        self,
        search: str,
        search_type: str | None = None,
        country_code: str | None = None,
        device: str | None = None,
        page: int | None = None,
        language: str | None = None,
        nfpr: bool | None = None,
        extra_params: str | None = None,
        add_html: bool | None = None,
        light_request: bool | None = None,
    ) -> tuple[bytes, dict, int]:
        params = {
            "search": search,
            "search_type": search_type,
            "country_code": country_code,
            "device": device,
            "page": page if page else None,
            "language": language,
            "nfpr": self._bool(nfpr),
            "extra_params": extra_params,
            "add_html": self._bool(add_html),
            "light_request": self._bool(light_request),
        }
        return await self._get("/google", params)

    async def fast_search(
        self,
        search: str,
        page: int | None = None,
        country_code: str | None = None,
        language: str | None = None,
    ) -> tuple[bytes, dict, int]:
        params = {
            "search": search,
            "page": page if page else None,
            "country_code": country_code,
            "language": language,
        }
        return await self._get("/fast_search", params)

    async def amazon_product(
        self,
        query: str,
        device: str | None = None,
        domain: str | None = None,
        country: str | None = None,
        zip_code: str | None = None,
        language: str | None = None,
        currency: str | None = None,
        add_html: bool | None = None,
        light_request: bool | None = None,
        screenshot: bool | None = None,
    ) -> tuple[bytes, dict, int]:
        params = {
            "query": query,
            "device": device,
            "domain": domain,
            "country": country,
            "zip_code": zip_code,
            "language": language,
            "currency": currency,
            "add_html": self._bool(add_html),
            "light_request": self._bool(light_request),
            "screenshot": self._bool(screenshot),
        }
        return await self._get("/amazon/product", params)

    async def amazon_search(
        self,
        query: str,
        start_page: int | None = None,
        pages: int | None = None,
        sort_by: str | None = None,
        device: str | None = None,
        domain: str | None = None,
        country: str | None = None,
        zip_code: str | None = None,
        language: str | None = None,
        currency: str | None = None,
        category_id: str | None = None,
        merchant_id: str | None = None,
        autoselect_variant: bool | None = None,
        add_html: bool | None = None,
        light_request: bool | None = None,
        screenshot: bool | None = None,
    ) -> tuple[bytes, dict, int]:
        params = {
            "query": query,
            "start_page": start_page if start_page else None,
            "pages": pages if pages else None,
            "sort_by": sort_by,
            "device": device,
            "domain": domain,
            "country": country,
            "zip_code": zip_code,
            "language": language,
            "currency": currency,
            "category_id": category_id,
            "merchant_id": merchant_id,
            "autoselect_variant": self._bool(autoselect_variant),
            "add_html": self._bool(add_html),
            "light_request": self._bool(light_request),
            "screenshot": self._bool(screenshot),
        }
        return await self._get("/amazon/search", params)

    async def walmart_search(
        self,
        query: str,
        min_price: int | None = None,
        max_price: int | None = None,
        sort_by: str | None = None,
        device: str | None = None,
        domain: str | None = None,
        fulfillment_speed: str | None = None,
        fulfillment_type: str | None = None,
        delivery_zip: str | None = None,
        store_id: str | None = None,
        add_html: bool | None = None,
        light_request: bool | None = None,
        screenshot: bool | None = None,
    ) -> tuple[bytes, dict, int]:
        params = {
            "query": query,
            "min_price": min_price if min_price else None,
            "max_price": max_price if max_price else None,
            "sort_by": sort_by,
            "device": device,
            "domain": domain,
            "fulfillment_speed": fulfillment_speed,
            "fulfillment_type": fulfillment_type,
            "delivery_zip": delivery_zip,
            "store_id": store_id,
            "add_html": self._bool(add_html),
            "light_request": self._bool(light_request),
            "screenshot": self._bool(screenshot),
        }
        return await self._get("/walmart/search", params)

    async def walmart_product(
        self,
        product_id: str,
        domain: str | None = None,
        delivery_zip: str | None = None,
        store_id: str | None = None,
        add_html: bool | None = None,
        light_request: bool | None = None,
        screenshot: bool | None = None,
    ) -> tuple[bytes, dict, int]:
        params = {
            "product_id": product_id,
            "domain": domain,
            "delivery_zip": delivery_zip,
            "store_id": store_id,
            "add_html": self._bool(add_html),
            "light_request": self._bool(light_request),
            "screenshot": self._bool(screenshot),
        }
        return await self._get("/walmart/product", params)

    async def youtube_search(
        self,
        search: str,
        upload_date: str | None = None,
        type: str | None = None,
        duration: str | None = None,
        sort_by: str | None = None,
        hd: bool | None = None,
        is_4k: bool | None = None,
        subtitles: bool | None = None,
        creative_commons: bool | None = None,
        live: bool | None = None,
        is_360: bool | None = None,
        is_3d: bool | None = None,
        hdr: bool | None = None,
        location: bool | None = None,
        vr180: bool | None = None,
    ) -> tuple[bytes, dict, int]:
        params = {
            "search": search,
            "upload_date": upload_date,
            "type": type,
            "duration": duration,
            "sort_by": sort_by,
            "hd": self._bool(hd),
            "4k": self._bool(is_4k),
            "subtitles": self._bool(subtitles),
            "creative_commons": self._bool(creative_commons),
            "live": self._bool(live),
            "360": self._bool(is_360),
            "3d": self._bool(is_3d),
            "hdr": self._bool(hdr),
            "location": self._bool(location),
            "vr180": self._bool(vr180),
        }
        return await self._get("/youtube/search", params)

    async def youtube_metadata(self, video_id: str) -> tuple[bytes, dict, int]:
        return await self._get("/youtube/metadata", {"video_id": video_id})

    async def youtube_transcript(
        self,
        video_id: str,
        language: str | None = None,
        transcript_origin: str | None = None,
    ) -> tuple[bytes, dict, int]:
        params = {
            "video_id": video_id,
            "language": language,
            "transcript_origin": transcript_origin,
        }
        return await self._get("/youtube/transcript", params)

    async def youtube_trainability(self, video_id: str) -> tuple[bytes, dict, int]:
        return await self._get("/youtube/trainability", {"video_id": video_id})

    async def chatgpt(self, prompt: str) -> tuple[bytes, dict, int]:
        return await self._get("/chatgpt", {"prompt": prompt})


def parse_usage(body: bytes) -> dict:
    """Extract max_concurrency and credits from usage API response."""
    out = {"max_concurrency": 5, "credits": 0}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return out
    for key in (
        "max_concurrency",
        "max_concurrent_requests",
        "concurrent_request_limit",
        "concurrency",
        "concurrent_requests",
    ):
        value = data.get(key)
        if value is not None and isinstance(value, (int, float)) and 0 < value <= 10000:
            out["max_concurrency"] = int(value)
            break
    for key in (
        "credits",
        "available_credits",
        "credit_balance",
        "balance",
        "credits_remaining",
        "remaining_credits",
    ):
        value = data.get(key)
        if value is not None and isinstance(value, (int, float)) and value >= 0:
            out["credits"] = int(value)
            return out
    max_credit = data.get("max_api_credit")
    used_credit = data.get("used_api_credit")
    if isinstance(max_credit, (int, float)) and isinstance(used_credit, (int, float)):
        avail = int(max_credit) - int(used_credit)
        if avail >= 0:
            out["credits"] = avail
    return out


def pretty_json(data: bytes) -> str:
    """Pretty-print JSON or return raw string."""
    try:
        obj = json.loads(data)
        return json.dumps(obj, indent=2)
    except (json.JSONDecodeError, TypeError):
        return data.decode("utf-8", errors="replace")
