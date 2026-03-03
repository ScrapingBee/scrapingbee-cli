"""Unit tests for CLI helpers: validation, constants."""

from __future__ import annotations

import sys

import pytest

from scrapingbee_cli.cli import _reject_equals_syntax, _reorder_global_options
from scrapingbee_cli.cli_utils import (
    WAIT_BROWSER_HELP,
    _extract_field_values,
    _filter_fields,
    _validate_json_option,
    _validate_page,
    _validate_price_range,
    _validate_range,
)
from scrapingbee_cli.commands.youtube import (
    _DURATION_ALIAS,
    YOUTUBE_DURATION,
    YOUTUBE_SORT_BY,
    YOUTUBE_TYPE,
    YOUTUBE_UPLOAD_DATE,
    _extract_video_id,
    _normalize_youtube_search,
)


class TestRejectEqualsSyntax:
    """_reject_equals_syntax() rejects --option=value and exits with message."""

    def test_equals_syntax_exits_with_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        old_argv = sys.argv
        try:
            sys.argv = ["scrapingbee", "scrape", "https://example.com", "--render-js=false"]
            with pytest.raises(SystemExit) as exc_info:
                _reject_equals_syntax()
            assert exc_info.value.code == 2
            err = capsys.readouterr().err
            assert "Use space-separated values" in err
            assert "render-js" in err
        finally:
            sys.argv = old_argv

    def test_space_separated_not_rejected(self) -> None:
        """Space-separated options do not trigger rejection (no exit)."""
        old_argv = sys.argv
        try:
            sys.argv = ["scrapingbee", "scrape", "https://example.com", "--render-js", "false"]
            _reject_equals_syntax()  # does not raise
        finally:
            sys.argv = old_argv


class TestWaitBrowserHelp:
    """WAIT_BROWSER_HELP constant."""

    def test_contains_browser_wait_options(self):
        assert "domcontentloaded" in WAIT_BROWSER_HELP
        assert "networkidle0" in WAIT_BROWSER_HELP


class TestValidateRange:
    """Tests for _validate_range()."""

    def test_none_passes(self):
        _validate_range("x", None, 0, 10)

    def test_in_range_passes(self):
        _validate_range("x", 5, 0, 10)
        _validate_range("x", 0, 0, 10)
        _validate_range("x", 10, 0, 10)

    def test_below_min_exits(self):
        with pytest.raises(SystemExit):
            _validate_range("x", -1, 0, 10)

    def test_above_max_exits(self):
        with pytest.raises(SystemExit):
            _validate_range("x", 11, 0, 10)


class TestValidatePage:
    """Tests for _validate_page()."""

    def test_none_passes(self):
        _validate_page(None)
        _validate_page(None, "start_page")

    def test_positive_passes(self):
        _validate_page(1)
        _validate_page(100, "pages")

    def test_zero_exits(self):
        with pytest.raises(SystemExit):
            _validate_page(0)
        with pytest.raises(SystemExit):
            _validate_page(0, "pages")

    def test_negative_exits(self):
        with pytest.raises(SystemExit):
            _validate_page(-1)


class TestValidatePriceRange:
    """Tests for _validate_price_range()."""

    def test_none_both_passes(self):
        _validate_price_range(None, None)

    def test_valid_range_passes(self):
        _validate_price_range(0, 100)
        _validate_price_range(10, 10)

    def test_min_negative_exits(self):
        with pytest.raises(SystemExit):
            _validate_price_range(-1, 100)

    def test_max_negative_exits(self):
        with pytest.raises(SystemExit):
            _validate_price_range(0, -1)

    def test_min_gt_max_exits(self):
        with pytest.raises(SystemExit):
            _validate_price_range(100, 50)


class TestValidateJsonOption:
    """Tests for _validate_json_option()."""

    def test_none_passes(self):
        _validate_json_option("--opt", None)

    def test_empty_string_passes(self):
        _validate_json_option("--opt", "")
        _validate_json_option("--opt", "   ")

    def test_valid_json_passes(self):
        _validate_json_option("--opt", "{}")
        _validate_json_option("--opt", '{"a": 1}')

    def test_invalid_json_exits(self):
        with pytest.raises(SystemExit):
            _validate_json_option("--opt", "not json")
        with pytest.raises(SystemExit):
            _validate_json_option("--opt", "{invalid}")


class TestPresetAndJsScenarioCli:
    """CLI behaviour for --preset and --js-scenario (via subprocess help)."""

    def test_scrape_help_shows_preset(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["scrape", "--help"])
        assert code == 0
        assert "--preset" in out
        for name in (
            "screenshot",
            "screenshot-and-html",
            "fetch",
            "extract-links",
            "extract-emails",
            "extract-phones",
            "scroll-page",
        ):
            assert name in out, f"preset {name!r} should appear in scrape --help"

    def test_scrape_help_shows_js_scenario(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["scrape", "--help"])
        assert code == 0
        assert "--js-scenario" in out

    def test_force_extension_in_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["scrape", "--help"])
        assert code == 0
        assert "force-extension" in out

    def test_scrape_help_shows_option_groups(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["scrape", "--help"])
        assert code == 0
        assert "Rendering:" in out
        assert "Proxy:" in out
        assert "Output:" in out

    def test_amazon_search_help_shows_option_groups(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["amazon-search", "--help"])
        assert code == 0
        assert "Pagination & sort" in out or "Filters" in out

    def test_google_search_type_choice(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["google", "--help"])
        assert code == 0
        assert "classic" in out and "news" in out

    def test_docs_command_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["docs", "--help"])
        assert code == 0
        assert "open" in out or "documentation" in out.lower()

    def test_auth_show_in_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["auth", "--help"])
        assert code == 0
        assert "--show" in out

    def test_global_retries_backoff_in_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["--help"])
        assert code == 0
        assert "retries" in out and "backoff" in out

    def test_global_extract_field_in_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["--help"])
        assert code == 0
        assert "extract-field" in out

    def test_global_fields_in_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["--help"])
        assert code == 0
        assert "--fields" in out

    def test_google_search_type_includes_ai_mode(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["google", "--help"])
        assert code == 0
        assert "ai-mode" in out


class TestExtractFieldValues:
    """Tests for _extract_field_values()."""

    def test_array_subkey_extraction(self):
        data = b'{"organic_results": [{"url": "https://a.com"}, {"url": "https://b.com"}]}'
        result = _extract_field_values(data, "organic_results.url")
        assert result == b"https://a.com\nhttps://b.com\n"

    def test_top_level_scalar(self):
        data = b'{"title": "Widget"}'
        result = _extract_field_values(data, "title")
        assert result == b"Widget\n"

    def test_top_level_list(self):
        data = b'{"asins": ["B001", "B002"]}'
        result = _extract_field_values(data, "asins")
        assert result == b"B001\nB002\n"

    def test_missing_key_returns_empty(self):
        data = b'{"other": "value"}'
        result = _extract_field_values(data, "title")
        assert result == b""

    def test_invalid_json_returns_data_unchanged(self):
        data = b"not json"
        result = _extract_field_values(data, "title")
        assert result == data

    def test_array_subkey_skips_missing_values(self):
        data = b'{"results": [{"url": "https://a.com"}, {"title": "no url"}]}'
        result = _extract_field_values(data, "results.url")
        assert result == b"https://a.com\n"

    def test_empty_array_returns_empty(self):
        data = b'{"results": []}'
        result = _extract_field_values(data, "results.url")
        assert result == b""


class TestFilterFields:
    """Tests for _filter_fields()."""

    def test_filters_top_level_keys(self):
        import json

        data = b'{"title": "Widget", "price": 9.99, "description": "long text"}'
        result = _filter_fields(data, "title,price")
        obj = json.loads(result)
        assert set(obj.keys()) == {"title", "price"}
        assert obj["title"] == "Widget"

    def test_ignores_nonexistent_keys(self):
        import json

        data = b'{"title": "Widget"}'
        result = _filter_fields(data, "title,nonexistent")
        obj = json.loads(result)
        assert set(obj.keys()) == {"title"}

    def test_empty_fields_returns_data_unchanged(self):
        data = b'{"title": "Widget"}'
        result = _filter_fields(data, "")
        assert result == data

    def test_invalid_json_returns_data_unchanged(self):
        data = b"not json"
        result = _filter_fields(data, "title")
        assert result == data

    def test_list_input_filters_each_dict(self):
        import json

        data = b'[{"title": "A", "price": 1}, {"title": "B", "price": 2}]'
        result = _filter_fields(data, "title")
        objs = json.loads(result)
        assert len(objs) == 2
        assert all(set(o.keys()) == {"title"} for o in objs)


class TestExtractVideoId:
    """Tests for youtube._extract_video_id()."""

    def test_bare_id_passthrough(self):
        assert _extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self):
        assert (
            _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s") == "dQw4w9WgXcQ"
        )

    def test_short_url(self):
        assert _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert _extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert _extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_unknown_string_passthrough(self):
        assert _extract_video_id("notaurl") == "notaurl"


class TestNormalizeYoutubeSearch:
    """Tests for youtube._normalize_youtube_search()."""

    def _raw_item(
        self, video_id: str, title: str = "Test Title", channel: str = "Test Channel"
    ) -> dict:
        return {
            "videoId": video_id,
            "title": {"runs": [{"text": title}]},
            "longBylineText": {"runs": [{"text": channel}]},
            "viewCountText": {"simpleText": "1,000 views"},
            "publishedTimeText": {"simpleText": "1 year ago"},
            "lengthText": {"simpleText": "10:00"},
        }

    def test_results_string_becomes_array(self):
        import json

        items = [self._raw_item("dQw4w9WgXcQ", "Never Gonna Give You Up", "Rick Astley")]
        raw = json.dumps({"results": json.dumps(items), "search": "never gonna"}).encode()
        out = _normalize_youtube_search(raw)
        d = json.loads(out)
        assert isinstance(d["results"], list)

    def test_link_field_constructed_from_video_id(self):
        import json

        items = [self._raw_item("dQw4w9WgXcQ")]
        raw = json.dumps({"results": json.dumps(items)}).encode()
        d = json.loads(_normalize_youtube_search(raw))
        assert d["results"][0]["link"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_title_and_channel_extracted(self):
        import json

        items = [self._raw_item("abc1234defg", "My Title", "My Channel")]
        raw = json.dumps({"results": json.dumps(items)}).encode()
        d = json.loads(_normalize_youtube_search(raw))
        r = d["results"][0]
        assert r["title"] == "My Title"
        assert r["channel"] == "My Channel"

    def test_video_id_in_output(self):
        import json

        items = [self._raw_item("abc1234defg")]
        raw = json.dumps({"results": json.dumps(items)}).encode()
        d = json.loads(_normalize_youtube_search(raw))
        assert d["results"][0]["video_id"] == "abc1234defg"

    def test_items_without_video_id_skipped(self):
        import json

        items = [{"title": {"runs": [{"text": "No ID"}]}}, self._raw_item("abc1234defg")]
        raw = json.dumps({"results": json.dumps(items)}).encode()
        d = json.loads(_normalize_youtube_search(raw))
        assert len(d["results"]) == 1
        assert d["results"][0]["video_id"] == "abc1234defg"

    def test_already_array_returns_unchanged(self):
        import json

        # If results is already a list (not a string), return data unchanged
        raw = json.dumps({"results": [{"link": "https://x.com"}]}).encode()
        out = _normalize_youtube_search(raw)
        assert out == raw

    def test_invalid_json_returns_data_unchanged(self):
        data = b"not json"
        assert _normalize_youtube_search(data) == data

    def test_other_fields_preserved(self):
        import json

        items = [self._raw_item("dQw4w9WgXcQ")]
        raw = json.dumps({"results": json.dumps(items), "search": "rick"}).encode()
        d = json.loads(_normalize_youtube_search(raw))
        assert d["search"] == "rick"


class TestYouTubeDurationAlias:
    """Tests for shell-safe duration aliases (short/medium/long)."""

    def test_alias_mapping_short(self):
        assert _DURATION_ALIAS["short"] == "<4"

    def test_alias_mapping_medium(self):
        assert _DURATION_ALIAS["medium"] == "4-20"

    def test_alias_mapping_long(self):
        assert _DURATION_ALIAS["long"] == ">20"

    def test_aliases_in_choices(self):
        for alias in ("short", "medium", "long"):
            assert alias in YOUTUBE_DURATION

    def test_raw_values_still_in_choices(self):
        for raw in ("<4", "4-20", ">20"):
            assert raw in YOUTUBE_DURATION


class TestReorderGlobalOptions:
    """Tests for _reorder_global_options()."""

    def test_empty_argv(self):
        assert _reorder_global_options([]) == []

    def test_no_subcommand_returns_unchanged(self):
        argv = ["--help"]
        assert _reorder_global_options(argv) == ["--help"]

    def test_version_returns_unchanged(self):
        argv = ["--version"]
        assert _reorder_global_options(argv) == ["--version"]

    def test_already_before_subcommand(self):
        argv = ["--verbose", "google", "test query"]
        assert _reorder_global_options(argv) == ["--verbose", "google", "test query"]

    def test_flag_moved_before_subcommand(self):
        argv = ["google", "--verbose", "test query"]
        assert _reorder_global_options(argv) == ["--verbose", "google", "test query"]

    def test_option_with_value_moved(self):
        argv = ["scrape", "--output-file", "/tmp/out.json", "https://example.com"]
        assert _reorder_global_options(argv) == [
            "--output-file",
            "/tmp/out.json",
            "scrape",
            "https://example.com",
        ]

    def test_multiple_globals_moved(self):
        argv = ["google", "--verbose", "--output-file", "out.json", "query"]
        assert _reorder_global_options(argv) == [
            "--verbose",
            "--output-file",
            "out.json",
            "google",
            "query",
        ]

    def test_mixed_global_and_local_options(self):
        argv = ["scrape", "--verbose", "--render-js", "false", "https://example.com"]
        result = _reorder_global_options(argv)
        assert result == [
            "--verbose",
            "scrape",
            "--render-js",
            "false",
            "https://example.com",
        ]

    def test_schedule_skipped(self):
        argv = ["schedule", "--every", "1h", "--verbose", "scrape", "URL"]
        assert _reorder_global_options(argv) == argv

    def test_export_collision_diff_dir_stays(self):
        """--diff-dir stays with export (it has its own --diff-dir option)."""
        argv = ["export", "--diff-dir", "old/", "--input-dir", "new/"]
        assert _reorder_global_options(argv) == argv

    def test_google_no_collision_diff_dir_moved(self):
        """--diff-dir is moved for google (no collision)."""
        argv = ["--input-file", "q.txt", "google", "--diff-dir", "old/"]
        assert _reorder_global_options(argv) == [
            "--input-file",
            "q.txt",
            "--diff-dir",
            "old/",
            "google",
        ]

    def test_value_matching_subcommand_name(self):
        """--output-file scrape scrape URL — Phase 1 skips the value 'scrape'."""
        argv = ["--output-file", "scrape", "scrape", "https://example.com"]
        assert _reorder_global_options(argv) == [
            "--output-file",
            "scrape",
            "scrape",
            "https://example.com",
        ]

    def test_subcommand_specific_option_not_moved(self):
        """A subcommand option like --render-js is not a global option, so stays."""
        argv = ["scrape", "--render-js", "false", "URL"]
        result = _reorder_global_options(argv)
        assert result == ["scrape", "--render-js", "false", "URL"]

    def test_globals_before_and_after(self):
        """Some globals before, some after — all end up before."""
        argv = ["--verbose", "google", "--output-file", "out.json", "query"]
        assert _reorder_global_options(argv) == [
            "--verbose",
            "--output-file",
            "out.json",
            "google",
            "query",
        ]

    def test_every_global_option_recognized(self):
        """Each global option is moved when placed after a subcommand."""
        from scrapingbee_cli.cli import _GLOBAL_OPTION_SPECS

        for opt, takes_value in _GLOBAL_OPTION_SPECS.items():
            argv = ["google", opt] + (["VAL"] if takes_value else []) + ["query"]
            result = _reorder_global_options(argv)
            assert result[0] == opt, f"{opt} should be moved before the subcommand"


class TestYouTubeChoiceConstants:
    """Tests verifying YouTube filter choice constants."""

    def test_upload_date_values(self):
        assert YOUTUBE_UPLOAD_DATE == ["today", "last-hour", "this-week", "this-month", "this-year"]

    def test_type_values(self):
        assert YOUTUBE_TYPE == ["video", "channel", "playlist", "movie"]

    def test_sort_by_values(self):
        assert YOUTUBE_SORT_BY == ["relevance", "rating", "view-count", "upload-date"]

    def test_duration_includes_aliases_and_raw(self):
        assert YOUTUBE_DURATION == ["short", "medium", "long", "<4", "4-20", ">20"]


class TestCommandHelpOutput:
    """Verify --help output includes key params for every command."""

    def test_youtube_search_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["youtube-search", "--help"])
        assert code == 0
        for param in ("--upload-date", "--type", "--duration", "--sort-by"):
            assert param in out, f"{param} should appear in youtube-search --help"
        # Duration aliases visible
        assert "short" in out
        assert "medium" in out
        assert "long" in out
        # Boolean filters
        for flag in (
            "--hd",
            "--4k",
            "--subtitles",
            "--creative-commons",
            "--live",
            "--hdr",
            "--location",
            "--vr180",
        ):
            assert flag in out, f"{flag} should appear in youtube-search --help"
        # Option groups
        assert "Filters" in out
        assert "Quality" in out or "features" in out

    def test_youtube_metadata_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["youtube-metadata", "--help"])
        assert code == 0
        assert "VIDEO_ID" in out or "video" in out.lower()

    def test_walmart_search_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["walmart-search", "--help"])
        assert code == 0
        for param in (
            "--min-price",
            "--max-price",
            "--sort-by",
            "--device",
            "--domain",
            "--delivery-zip",
        ):
            assert param in out, f"{param} should appear in walmart-search --help"
        assert "best-match" in out
        assert "price-low" in out

    def test_walmart_product_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["walmart-product", "--help"])
        assert code == 0
        for param in ("--domain", "--delivery-zip", "--store-id", "--add-html", "--screenshot"):
            assert param in out, f"{param} should appear in walmart-product --help"

    def test_amazon_product_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["amazon-product", "--help"])
        assert code == 0
        for param in (
            "--device",
            "--domain",
            "--country",
            "--language",
            "--currency",
            "--add-html",
            "--screenshot",
        ):
            assert param in out, f"{param} should appear in amazon-product --help"

    def test_amazon_search_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["amazon-search", "--help"])
        assert code == 0
        for param in (
            "--start-page",
            "--pages",
            "--sort-by",
            "--device",
            "--domain",
            "--category-id",
        ):
            assert param in out, f"{param} should appear in amazon-search --help"
        assert "price-low-to-high" in out

    def test_fast_search_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["fast-search", "--help"])
        assert code == 0
        for param in ("--page", "--country-code", "--language"):
            assert param in out, f"{param} should appear in fast-search --help"

    def test_chatgpt_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["chatgpt", "--help"])
        assert code == 0
        assert "PROMPT" in out or "prompt" in out.lower()

    def test_crawl_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["crawl", "--help"])
        assert code == 0
        for param in (
            "--from-sitemap",
            "--max-depth",
            "--max-pages",
            "--render-js",
            "--premium-proxy",
            "--ai-query",
            "--return-page-markdown",
            "--allowed-domains",
        ):
            assert param in out, f"{param} should appear in crawl --help"

    def test_export_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["export", "--help"])
        assert code == 0
        for param in ("--input-dir", "--format", "--diff-dir"):
            assert param in out, f"{param} should appear in export --help"
        assert "ndjson" in out
        assert "csv" in out

    def test_schedule_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["schedule", "--help"])
        assert code == 0
        for param in ("--every", "--auto-diff"):
            assert param in out, f"{param} should appear in schedule --help"

    def test_usage_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["usage", "--help"])
        assert code == 0
        assert "credit" in out.lower() or "usage" in out.lower()

    def test_scrape_help_all_option_groups(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["scrape", "--help"])
        assert code == 0
        for param in (
            "--render-js",
            "--wait",
            "--premium-proxy",
            "--country-code",
            "--json-response",
            "--return-page-markdown",
            "--return-page-text",
            "--screenshot",
            "--extract-rules",
            "--ai-query",
            "--chunk-size",
            "--chunk-overlap",
            "--device",
            "--method",
            "--data",
            "--session-id",
        ):
            assert param in out, f"{param} should appear in scrape --help"

    def test_google_help_all_params(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["google", "--help"])
        assert code == 0
        for param in (
            "--search-type",
            "--country-code",
            "--device",
            "--page",
            "--language",
            "--add-html",
        ):
            assert param in out, f"{param} should appear in google --help"
        for search_type in ("classic", "news", "maps", "shopping", "images", "ai-mode"):
            assert search_type in out, f"search type {search_type!r} should appear in google --help"

    def test_global_help_all_options(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["--help"])
        assert code == 0
        for param in (
            "--output-file",
            "--verbose",
            "--output-dir",
            "--input-file",
            "--concurrency",
            "--retries",
            "--backoff",
            "--resume",
            "--no-progress",
            "--extract-field",
            "--fields",
            "--diff-dir",
        ):
            assert param in out, f"{param} should appear in global --help"

    def test_global_help_lists_all_commands(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["--help"])
        assert code == 0
        for cmd in (
            "scrape",
            "crawl",
            "google",
            "fast-search",
            "amazon-product",
            "amazon-search",
            "walmart-search",
            "walmart-product",
            "youtube-search",
            "youtube-metadata",
            "chatgpt",
            "export",
            "schedule",
            "usage",
            "auth",
            "docs",
        ):
            assert cmd in out, f"command {cmd!r} should appear in global --help"
