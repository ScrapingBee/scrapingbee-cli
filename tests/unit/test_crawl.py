"""Unit tests for crawl module."""

from __future__ import annotations

from scrapingbee_cli.crawl import (
    _body_from_json_response,
    _extract_hrefs_from_body,
    _extract_hrefs_from_response,
    _normalize_url,
    _param_truthy,
    _params_for_discovery,
    _preferred_extension_from_scrape_params,
    default_crawl_output_dir,
)


class TestNormalizeUrl:
    """Tests for _normalize_url()."""

    def test_strips_fragment(self):
        assert _normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_strips_trailing_slash(self):
        assert _normalize_url("https://example.com/") == "https://example.com/"

    def test_preserves_query(self):
        # Path is normalized to / when empty, so query attaches after /
        assert _normalize_url("https://example.com?a=1") == "https://example.com/?a=1"


class TestParamTruthy:
    """Tests for _param_truthy()."""

    def test_true_value(self):
        assert _param_truthy({"a": True}, "a") is True
        assert _param_truthy({"a": "true"}, "a") is True
        assert _param_truthy({"a": "True"}, "a") is True  # case-insensitive
        assert _param_truthy({"a": "1"}, "a") is True
        assert _param_truthy({"a": "yes"}, "a") is True

    def test_false_value(self):
        assert _param_truthy({"a": False}, "a") is False
        assert _param_truthy({"a": "false"}, "a") is False
        assert _param_truthy({"a": None}, "a") is False
        assert _param_truthy({}, "a") is False


class TestParamsForDiscovery:
    """Tests for _params_for_discovery()."""

    def test_strips_screenshot_and_return_text(self):
        params = {"screenshot": True, "return_page_text": True, "render_js": True}
        out = _params_for_discovery(params)
        assert "screenshot" not in out
        assert "return_page_text" not in out
        assert out.get("render_js") is True

    def test_strips_json_response(self):
        params = {"json_response": True, "wait": 1000}
        out = _params_for_discovery(params)
        assert "json_response" not in out
        assert out.get("wait") == 1000

    def test_strips_ai_params(self):
        params = {
            "ai_query": "extract links",
            "ai_selector": "a",
            "ai_extract_rules": "{}",
            "wait": 500,
        }
        out = _params_for_discovery(params)
        assert "ai_query" not in out
        assert "ai_selector" not in out
        assert "ai_extract_rules" not in out
        assert out.get("wait") == 500

    def test_strips_extract_rules(self):
        params = {"extract_rules": '{"title": "h1"}', "render_js": True}
        out = _params_for_discovery(params)
        assert "extract_rules" not in out
        assert out.get("render_js") is True


class TestPreferredExtensionFromScrapeParams:
    """Tests for _preferred_extension_from_scrape_params()."""

    def test_screenshot_and_json_response(self):
        assert (
            _preferred_extension_from_scrape_params({"screenshot": True, "json_response": True})
            == "json"
        )

    def test_screenshot_only(self):
        assert _preferred_extension_from_scrape_params({"screenshot": True}) == "png"

    def test_return_markdown(self):
        assert _preferred_extension_from_scrape_params({"return_page_markdown": True}) == "md"

    def test_return_text(self):
        assert _preferred_extension_from_scrape_params({"return_page_text": True}) == "txt"

    def test_json_response_only(self):
        assert _preferred_extension_from_scrape_params({"json_response": True}) == "json"

    def test_none_when_no_match(self):
        assert _preferred_extension_from_scrape_params({}) is None


class TestBodyFromJsonResponse:
    """Tests for _body_from_json_response()."""

    def test_returns_body_field(self):
        body = b'{"body": "<html>hi</html>", "other": 1}'
        assert _body_from_json_response(body) == b"<html>hi</html>"

    def test_returns_content_field_when_no_body(self):
        body = b'{"content": "markdown here"}'
        assert _body_from_json_response(body) == b"markdown here"

    def test_returns_none_for_non_json(self):
        assert _body_from_json_response(b"<html/>") is None
        assert _body_from_json_response(b"[Crawler](/)") is None

    def test_returns_none_for_empty(self):
        assert _body_from_json_response(b"") is None


class TestExtractHrefsFromBody:
    """Tests for _extract_hrefs_from_body()."""

    def test_html_href(self):
        body = b'<a href="/page">link</a>'
        assert _extract_hrefs_from_body(body) == ["/page"]

    def test_markdown_links(self):
        body = b"[text](/path) and [other](https://example.com/other)"
        assert "/path" in _extract_hrefs_from_body(body)
        assert "https://example.com/other" in _extract_hrefs_from_body(body)

    def test_extracts_mailto_and_anchor_hrefs(self):
        # _extract_hrefs_from_body returns all hrefs; spider filters #/mailto:/javascript: later
        body = b'<a href="mailto:x@y.com">m</a><a href="#anchor">a</a>'
        hrefs = _extract_hrefs_from_body(body)
        assert "mailto:x@y.com" in hrefs
        assert "#anchor" in hrefs


class TestExtractHrefsFromResponse:
    """Tests for _extract_hrefs_from_response()."""

    def test_json_body_extraction(self):
        from scrapy.http import HtmlResponse

        # Response with JSON body containing HTML in "body" field
        body = b'{"body": "<a href=\\"https://example.com/page\\">link</a>"}'
        response = HtmlResponse("https://example.com", body=body)
        hrefs = _extract_hrefs_from_response(response)
        assert "https://example.com/page" in hrefs or "/page" in hrefs

    def test_html_links_via_css(self):
        from scrapy.http import HtmlResponse

        body = b'<html><a href="/foo">x</a><a href="https://other.com/b">y</a></html>'
        response = HtmlResponse("https://example.com", body=body)
        hrefs = _extract_hrefs_from_response(response)
        assert "/foo" in hrefs
        assert "https://other.com/b" in hrefs


class TestSpiderDiscovery:
    """Tests for the double-fetch discovery mechanism in GenericScrapingBeeSpider."""

    def _make_response(self, url: str, body: bytes, depth: int = 0):
        """Create a Scrapy HtmlResponse with request meta attached."""
        from scrapy.http import HtmlResponse, Request

        response = HtmlResponse(url, body=body, encoding="utf-8")
        response.request = Request(url, meta={"depth": depth})
        return response

    def test_parse_yields_discovery_request_when_no_links(self):
        """parse() must yield exactly one discovery request when the body has no links."""
        from scrapy_scrapingbee import ScrapingBeeRequest

        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={"return_page_text": True},
            output_dir=None,
        )
        response = self._make_response("https://example.com/page", b"Plain text, no links")
        requests = list(spider.parse(response))

        assert len(requests) == 1
        assert isinstance(requests[0], ScrapingBeeRequest)
        assert requests[0].callback == spider._parse_discovery_links_only
        assert requests[0].dont_filter is True

    def test_parse_does_not_yield_discovery_when_links_found(self):
        """parse() must not yield a discovery request when the body already has links."""
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={},
            output_dir=None,
        )
        spider.seen_urls.add("https://example.com")

        response = self._make_response(
            "https://example.com",
            b'<a href="/page1">link1</a><a href="/page2">link2</a>',
        )
        requests = list(spider.parse(response))

        # No request should target the discovery callback
        for req in requests:
            assert req.callback != spider._parse_discovery_links_only

    def test_parse_discovery_links_only_follows_links_but_does_not_save(self, tmp_path):
        """_parse_discovery_links_only must yield follow requests but never write files."""
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={"return_page_text": True},
            output_dir=str(tmp_path),
        )
        spider.seen_urls.add("https://example.com")

        response = self._make_response(
            "https://example.com",
            b'<a href="/page1">p1</a><a href="/page2">p2</a>',
        )
        requests = list(spider._parse_discovery_links_only(response))

        # Should yield follow requests (not empty)
        assert len(requests) > 0
        # Each follow request must use the main parse callback (not discovery again)
        for req in requests:
            assert req.callback == spider.parse
        # Nothing written — discovery does not save
        assert list(tmp_path.iterdir()) == []


class TestSpiderSaveResponse:
    """Tests for _save_response manifest field extraction."""

    def _make_spider(self, tmp_path):
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        return GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={},
            output_dir=str(tmp_path),
        )

    def _make_response(self, url, body, headers=None, meta=None):
        import scrapy

        return scrapy.http.TextResponse(
            url=url,
            body=body,
            encoding="utf-8",
            headers=headers or {},
            request=scrapy.Request(url, meta=meta or {}),
        )

    def test_save_response_extracts_credits_used(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
            headers={"Spb-Cost": "5"},
        )
        spider._save_response(response)
        entry = spider._url_file_map["https://example.com/page"]
        assert entry["credits_used"] == 5

    def test_save_response_credits_none_when_no_header(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
        )
        spider._save_response(response)
        entry = spider._url_file_map["https://example.com/page"]
        assert entry["credits_used"] is None

    def test_save_response_extracts_latency_ms(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
            meta={"download_latency": 1.5},
        )
        spider._save_response(response)
        entry = spider._url_file_map["https://example.com/page"]
        assert entry["latency_ms"] == 1500

    def test_save_response_latency_none_when_no_meta(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
        )
        spider._save_response(response)
        entry = spider._url_file_map["https://example.com/page"]
        assert entry["latency_ms"] is None

    def test_save_response_writes_file(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
        )
        spider._save_response(response)
        assert (tmp_path / "1.html").exists()
        assert (tmp_path / "1.html").read_bytes() == b"<html>test</html>"

    def test_save_response_manifest_has_required_fields(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
            headers={"Spb-Cost": "10"},
            meta={"download_latency": 0.5},
        )
        spider._save_response(response)
        entry = spider._url_file_map["https://example.com/page"]
        for field in ("file", "fetched_at", "http_status", "credits_used", "latency_ms"):
            assert field in entry, f"Missing field {field!r}"


class TestDefaultCrawlOutputDir:
    """Tests for default_crawl_output_dir()."""

    def test_format(self):
        name = default_crawl_output_dir()
        assert name.startswith("crawl_")
        rest = name.replace("crawl_", "")
        assert len(rest) == 15  # YYYYMMDD_HHMMSS
        assert rest[8] == "_"
