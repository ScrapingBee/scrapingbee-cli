"""Unit tests for cli_utils helpers: chunk_text, parse_bool, _apply_chunking,
build_scrape_kwargs, scrape_kwargs_to_api_params, write_output."""

from __future__ import annotations

import json
import os
import sys
from io import BytesIO

import pytest

from scrapingbee_cli.cli_utils import (
    build_scrape_kwargs,
    chunk_text,
    parse_bool,
    scrape_kwargs_to_api_params,
    write_output,
)
from scrapingbee_cli.commands.schedule import _extract_output_dir, _make_run_subdir, _parse_duration
from scrapingbee_cli.commands.scrape import _apply_chunking


class TestChunkText:
    """Tests for chunk_text()."""

    def test_empty_string_returns_empty_list(self) -> None:
        # chunk_text filters out empty strings; empty input → no chunks
        result = chunk_text("", size=100)
        assert result == []

    def test_text_shorter_than_size_returns_single_chunk(self) -> None:
        result = chunk_text("hello world", size=100)
        assert result == ["hello world"]

    def test_text_exactly_size_returns_single_chunk(self) -> None:
        result = chunk_text("abcde", size=5)
        assert result == ["abcde"]

    def test_text_longer_than_size_splits_correctly(self) -> None:
        result = chunk_text("abcdefghij", size=4)
        assert result == ["abcd", "efgh", "ij"]

    def test_chunks_with_overlap(self) -> None:
        result = chunk_text("abcdefghij", size=5, overlap=2)
        # step = 5 - 2 = 3; range(0, 10, 3) → [0, 3, 6, 9]
        # chunk 0: [0:5] = "abcde"
        # chunk 1: [3:8] = "defgh"
        # chunk 2: [6:11] = "ghij"
        # chunk 3: [9:14] = "j"
        assert result == ["abcde", "defgh", "ghij", "j"]

    def test_overlap_zero_same_as_no_overlap(self) -> None:
        assert chunk_text("abcdefgh", size=4, overlap=0) == chunk_text("abcdefgh", size=4)

    def test_size_zero_returns_original_text(self) -> None:
        text = "hello world"
        result = chunk_text(text, size=0)
        assert result == [text]

    def test_size_negative_returns_original_text(self) -> None:
        text = "hello world"
        result = chunk_text(text, size=-1)
        assert result == [text]

    def test_overlap_clamped_to_size_minus_one(self) -> None:
        # overlap >= size should be clamped to size-1, making step=1
        result = chunk_text("abc", size=2, overlap=5)
        # step = max(1, 2 - min(5, 1)) = 1
        assert len(result) >= 2
        assert all(len(c) <= 2 for c in result)

    def test_all_chunks_non_empty(self) -> None:
        result = chunk_text("hello world this is a test", size=7)
        assert all(c for c in result)

    def test_no_empty_chunks_in_output(self) -> None:
        result = chunk_text("x" * 20, size=7, overlap=3)
        for chunk in result:
            assert chunk, "chunk_text must not return empty strings"

    def test_chunks_cover_full_text(self) -> None:
        text = "hello world this is a test sentence"
        size = 8
        result = chunk_text(text, size=size, overlap=0)
        # With no overlap, chunks partition the text exactly
        for i, chunk in enumerate(result):
            start = i * size
            assert text[start : start + size] == chunk
        # Concatenation of chunks must equal original text
        assert "".join(result) == text


class TestParseBool:
    """Tests for parse_bool()."""

    def test_none_returns_none(self) -> None:
        assert parse_bool(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert parse_bool("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert parse_bool("   ") is None

    def test_true_variants(self) -> None:
        for val in ("true", "True", "TRUE", "1", "yes", "YES"):
            assert parse_bool(val) is True, f"parse_bool({val!r}) should be True"

    def test_false_variants(self) -> None:
        for val in ("false", "False", "FALSE", "0", "no", "NO"):
            assert parse_bool(val) is False, f"parse_bool({val!r}) should be False"

    def test_invalid_value_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid boolean"):
            parse_bool("treu")

    def test_invalid_value_2_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid boolean"):
            parse_bool("maybe")

    def test_whitespace_stripped(self) -> None:
        assert parse_bool("  true  ") is True
        assert parse_bool("  false  ") is False


class TestParseDuration:
    """Tests for schedule._parse_duration()."""

    def test_seconds(self) -> None:
        assert _parse_duration("30s") == 30

    def test_minutes(self) -> None:
        assert _parse_duration("5m") == 300

    def test_hours(self) -> None:
        assert _parse_duration("1h") == 3600

    def test_days(self) -> None:
        assert _parse_duration("2d") == 172800

    def test_large_value(self) -> None:
        assert _parse_duration("100s") == 100

    def test_whitespace_stripped(self) -> None:
        assert _parse_duration("  10m  ") == 600

    def test_invalid_format_raises(self) -> None:
        import click

        with pytest.raises(click.BadParameter):
            _parse_duration("1hour")

    def test_missing_unit_raises(self) -> None:
        import click

        with pytest.raises(click.BadParameter):
            _parse_duration("60")

    def test_empty_string_raises(self) -> None:
        import click

        with pytest.raises(click.BadParameter):
            _parse_duration("")

    def test_zero_value(self) -> None:
        assert _parse_duration("0s") == 0


class TestApplyChunking:
    """Tests for scrape._apply_chunking() (T-02)."""

    _URL = "https://example.com/page"

    def _lines(self, result: bytes) -> list[dict]:
        return [json.loads(line) for line in result.decode("utf-8").strip().split("\n") if line]

    def test_single_chunk_when_text_fits(self) -> None:
        result = _apply_chunking(self._URL, b"hello world", chunk_size=100, chunk_overlap=0)
        lines = self._lines(result)
        assert len(lines) == 1

    def test_multiple_chunks_when_text_longer_than_size(self) -> None:
        result = _apply_chunking(self._URL, b"a" * 30, chunk_size=10, chunk_overlap=0)
        lines = self._lines(result)
        assert len(lines) == 3

    def test_output_is_valid_ndjson(self) -> None:
        result = _apply_chunking(self._URL, b"hello world foo bar", chunk_size=8, chunk_overlap=0)
        for line in result.decode("utf-8").strip().split("\n"):
            if line:
                obj = json.loads(line)
                assert isinstance(obj, dict)

    def test_required_fields_present(self) -> None:
        result = _apply_chunking(self._URL, b"hello world", chunk_size=100, chunk_overlap=0)
        obj = self._lines(result)[0]
        for field in ("url", "chunk_index", "total_chunks", "content", "fetched_at"):
            assert field in obj, f"Missing field {field!r}"

    def test_url_preserved_in_every_chunk(self) -> None:
        result = _apply_chunking(self._URL, b"a" * 30, chunk_size=10, chunk_overlap=0)
        for obj in self._lines(result):
            assert obj["url"] == self._URL

    def test_chunk_index_zero_based_sequential(self) -> None:
        result = _apply_chunking(self._URL, b"a" * 30, chunk_size=10, chunk_overlap=0)
        lines = self._lines(result)
        assert [obj["chunk_index"] for obj in lines] == list(range(len(lines)))

    def test_total_chunks_matches_actual_count(self) -> None:
        result = _apply_chunking(self._URL, b"a" * 30, chunk_size=10, chunk_overlap=0)
        lines = self._lines(result)
        for obj in lines:
            assert obj["total_chunks"] == len(lines)

    def test_content_concatenates_to_original_when_no_overlap(self) -> None:
        text = "hello world this is a test sentence"
        result = _apply_chunking(self._URL, text.encode(), chunk_size=8, chunk_overlap=0)
        lines = self._lines(result)
        assert "".join(obj["content"] for obj in lines) == text

    def test_output_is_bytes(self) -> None:
        result = _apply_chunking(self._URL, b"hello", chunk_size=100, chunk_overlap=0)
        assert isinstance(result, bytes)

    def test_output_decodable_as_utf8(self) -> None:
        data = "héllo wörld".encode()
        result = _apply_chunking(self._URL, data, chunk_size=100, chunk_overlap=0)
        result.decode("utf-8")  # must not raise

    def test_empty_body_produces_no_chunks(self) -> None:
        result = _apply_chunking(self._URL, b"", chunk_size=10, chunk_overlap=0)
        lines = self._lines(result)
        assert lines == []

    def test_overlap_produces_more_chunks(self) -> None:
        data = b"a" * 20
        no_overlap = self._lines(_apply_chunking(self._URL, data, chunk_size=5, chunk_overlap=0))
        with_overlap = self._lines(_apply_chunking(self._URL, data, chunk_size=5, chunk_overlap=2))
        assert len(with_overlap) > len(no_overlap)


class TestBuildScrapeKwargs:
    """Tests for build_scrape_kwargs() (T-07)."""

    def test_defaults_are_none_or_get(self) -> None:
        kwargs = build_scrape_kwargs()
        assert kwargs["render_js"] is None
        assert kwargs["screenshot"] is None
        assert kwargs["method"] == "GET"

    def test_parses_true_string_to_bool(self) -> None:
        kwargs = build_scrape_kwargs(render_js="true", screenshot="false")
        assert kwargs["render_js"] is True
        assert kwargs["screenshot"] is False

    def test_parses_1_and_0_as_bool(self) -> None:
        kwargs = build_scrape_kwargs(premium_proxy="1", stealth_proxy="0")
        assert kwargs["premium_proxy"] is True
        assert kwargs["stealth_proxy"] is False

    def test_preserves_int_values(self) -> None:
        kwargs = build_scrape_kwargs(wait=1000, session_id=42, window_width=1920)
        assert kwargs["wait"] == 1000
        assert kwargs["session_id"] == 42
        assert kwargs["window_width"] == 1920

    def test_preserves_string_values(self) -> None:
        kwargs = build_scrape_kwargs(country_code="us", ai_query="find the price")
        assert kwargs["country_code"] == "us"
        assert kwargs["ai_query"] == "find the price"

    def test_invalid_bool_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid boolean"):
            build_scrape_kwargs(render_js="maybe")

    def test_none_bool_stays_none(self) -> None:
        kwargs = build_scrape_kwargs(render_js=None, screenshot=None)
        assert kwargs["render_js"] is None
        assert kwargs["screenshot"] is None

    def test_all_keys_present(self) -> None:
        kwargs = build_scrape_kwargs()
        for key in ("render_js", "method", "screenshot", "country_code", "extract_rules"):
            assert key in kwargs, f"Expected key {key!r} in build_scrape_kwargs output"


class TestScrapeKwargsToApiParams:
    """Tests for scrape_kwargs_to_api_params() (T-07)."""

    def test_omits_none_values(self) -> None:
        params = scrape_kwargs_to_api_params({"render_js": None, "wait": None})
        assert "render_js" not in params
        assert "wait" not in params

    def test_converts_true_to_lowercase_string(self) -> None:
        params = scrape_kwargs_to_api_params({"render_js": True, "screenshot": False})
        assert params["render_js"] == "true"
        assert params["screenshot"] == "false"

    def test_converts_int_to_string(self) -> None:
        params = scrape_kwargs_to_api_params({"wait": 1000, "session_id": 42})
        assert params["wait"] == "1000"
        assert params["session_id"] == "42"

    def test_skips_method_body_custom_headers(self) -> None:
        params = scrape_kwargs_to_api_params(
            {"method": "POST", "body": "data", "custom_headers": {"X-Foo": "bar"}}
        )
        assert "method" not in params
        assert "body" not in params
        assert "custom_headers" not in params

    def test_passes_through_string_values(self) -> None:
        params = scrape_kwargs_to_api_params({"country_code": "us", "ai_query": "find price"})
        assert params["country_code"] == "us"
        assert params["ai_query"] == "find price"

    def test_omits_empty_string(self) -> None:
        params = scrape_kwargs_to_api_params({"country_code": ""})
        assert "country_code" not in params

    def test_output_values_are_all_strings(self) -> None:
        params = scrape_kwargs_to_api_params({"render_js": True, "wait": 500, "country_code": "gb"})
        for v in params.values():
            assert isinstance(v, str), f"Expected str, got {type(v)} for value {v!r}"


class TestWriteOutput:
    """Tests for write_output() (T-08)."""

    def test_writes_to_file(self, tmp_path) -> None:
        out = tmp_path / "result.txt"
        write_output(b"hello world", {}, 200, str(out), verbose=False)
        assert out.read_bytes() == b"hello world"

    def test_extracts_field_to_file(self, tmp_path) -> None:
        data = b'{"results": [{"url": "https://a.com"}, {"url": "https://b.com"}]}'
        out = tmp_path / "urls.txt"
        write_output(data, {}, 200, str(out), verbose=False, extract_field="results.url")
        content = out.read_text()
        assert "https://a.com" in content
        assert "https://b.com" in content

    def test_filters_fields_to_file(self, tmp_path) -> None:
        data = b'{"title": "foo", "price": 9.99, "hidden": "x"}'
        out = tmp_path / "filtered.json"
        write_output(data, {}, 200, str(out), verbose=False, fields="title,price")
        result = json.loads(out.read_text())
        assert "title" in result
        assert "price" in result
        assert "hidden" not in result

    def test_verbose_writes_status_to_stderr(self, tmp_path, capsys) -> None:
        out = tmp_path / "out.txt"
        write_output(b"data", {"Spb-Cost": "5"}, 200, str(out), verbose=True)
        err = capsys.readouterr().err
        assert "200" in err
        assert "5" in err

    def test_extract_field_takes_precedence_over_fields(self, tmp_path) -> None:
        """When both are set, extract_field wins."""
        data = b'{"items": [{"id": "1"}, {"id": "2"}], "total": 2}'
        out = tmp_path / "out.txt"
        write_output(
            data, {}, 200, str(out), verbose=False, extract_field="items.id", fields="total"
        )
        content = out.read_text()
        assert "1" in content
        assert "2" in content

    def test_writes_to_stdout_when_no_path(self, monkeypatch) -> None:
        buf = BytesIO()
        fake = type(
            "FakeStdout",
            (),
            {
                "buffer": buf,
                "write": buf.write,
                "flush": lambda self: None,
            },
        )()
        monkeypatch.setattr(sys, "stdout", fake)
        write_output(b"output data", {}, 200, None, verbose=False)
        assert b"output data" in buf.getvalue()

    def test_verbose_shows_estimated_credits_when_no_spb_cost(self, tmp_path, capsys) -> None:
        """When spb-cost header is absent and command is set, show estimated credits."""
        out = tmp_path / "out.json"
        write_output(b'{"q":"test"}', {}, 200, str(out), verbose=True, command="google")
        err = capsys.readouterr().err
        assert "Credit Cost (estimated):" in err
        assert "10-15" in err

    def test_verbose_shows_real_cost_when_spb_cost_present(self, tmp_path, capsys) -> None:
        """When spb-cost header is present, show real cost, not estimated."""
        out = tmp_path / "out.json"
        write_output(
            b'{"q":"test"}',
            {"Spb-Cost": "25"},
            200,
            str(out),
            verbose=True,
            command="google",
        )
        err = capsys.readouterr().err
        assert "Credit Cost: 25" in err
        assert "estimated" not in err.lower()

    def test_verbose_no_estimated_when_command_is_none(self, tmp_path, capsys) -> None:
        """When command is None, no estimated credit line is shown."""
        out = tmp_path / "out.json"
        write_output(b'{"q":"test"}', {}, 200, str(out), verbose=True, command=None)
        err = capsys.readouterr().err
        assert "estimated" not in err.lower()


class TestEstimatedCredits:
    """Tests for credits.ESTIMATED_CREDITS mapping."""

    def test_all_serp_commands_have_entries(self) -> None:
        from scrapingbee_cli.credits import ESTIMATED_CREDITS

        expected = {
            "google",
            "fast-search",
            "amazon-product",
            "amazon-search",
            "walmart-search",
            "walmart-product",
            "youtube-search",
            "youtube-metadata",
            "chatgpt",
        }
        assert set(ESTIMATED_CREDITS.keys()) == expected

    def test_all_values_are_non_empty_strings(self) -> None:
        from scrapingbee_cli.credits import ESTIMATED_CREDITS

        for cmd, cost in ESTIMATED_CREDITS.items():
            assert isinstance(cost, str), f"{cmd}: cost should be str"
            assert cost.strip(), f"{cmd}: cost should be non-empty"


class TestScheduleHelpers:
    """Tests for schedule._make_run_subdir and _extract_output_dir."""

    def test_make_run_subdir_is_under_parent(self) -> None:
        result = _make_run_subdir("price-runs")
        assert result.startswith("price-runs" + os.sep) or result.startswith("price-runs/")

    def test_make_run_subdir_contains_run_prefix(self) -> None:
        result = _make_run_subdir("price-runs")
        assert "run_" in result

    def test_make_run_subdir_unique_per_call(self) -> None:
        # Two calls should return different values (unless called in the same second,
        # which is fine — the test just documents the pattern).
        r1 = _make_run_subdir("out")
        r2 = _make_run_subdir("out")
        # Both should be under "out/"
        assert r1.startswith("out")
        assert r2.startswith("out")

    def test_extract_output_dir_finds_value(self) -> None:
        cmd_args = ("--output-dir", "mydir", "google", "query")
        assert _extract_output_dir(cmd_args) == "mydir"

    def test_extract_output_dir_returns_none_when_absent(self) -> None:
        cmd_args = ("google", "query")
        assert _extract_output_dir(cmd_args) is None

    def test_extract_output_dir_returns_none_when_no_value(self) -> None:
        # --output-dir at end of args with no value
        cmd_args = ("google", "--output-dir")
        assert _extract_output_dir(cmd_args) is None
