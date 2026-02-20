"""Unit tests for batch module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from scrapingbee_cli.batch import (
    BatchResult,
    _batch_subdir_for_extension,
    default_batch_output_dir,
    extension_for_scrape,
    extension_from_body_sniff,
    extension_from_content_type,
    get_batch_usage,
    read_input_file,
    resolve_batch_concurrency,
    run_batch_async,
    validate_batch_run,
    write_batch_output_to_dir,
)


class TestReadInputFile:
    """Tests for read_input_file()."""

    def test_reads_non_empty_lines(self, tmp_path):
        f = tmp_path / "in.txt"
        f.write_text("a\n\nb\n  c  \n")
        assert read_input_file(str(f)) == ["a", "b", "c"]

    def test_empty_file_raises(self, tmp_path):
        (tmp_path / "empty.txt").write_text("")
        with pytest.raises(ValueError, match="no non-empty lines"):
            read_input_file(str(tmp_path / "empty.txt"))

    def test_only_whitespace_raises(self, tmp_path):
        (tmp_path / "ws.txt").write_text("   \n\n  ")
        with pytest.raises(ValueError, match="no non-empty lines"):
            read_input_file(str(tmp_path / "ws.txt"))


class TestValidateBatchRun:
    """Tests for validate_batch_run()."""

    def test_ok_when_under_concurrency_and_credits(self):
        validate_batch_run(0, 5, {"max_concurrency": 10, "credits": 100})

    def test_raises_when_user_concurrency_exceeds_limit(self):
        with pytest.raises(ValueError, match="concurrency 20 exceeds"):
            validate_batch_run(20, 5, {"max_concurrency": 10, "credits": 100})

    def test_raises_when_not_enough_credits(self):
        with pytest.raises(ValueError, match="not enough credits"):
            validate_batch_run(0, 50, {"max_concurrency": 10, "credits": 10})


class TestResolveBatchConcurrency:
    """Tests for resolve_batch_concurrency()."""

    def test_user_value_used_when_positive(self):
        assert resolve_batch_concurrency(5, {"max_concurrency": 10}, 20) == 5

    def test_usage_value_used_when_user_zero(self):
        assert resolve_batch_concurrency(0, {"max_concurrency": 8}, 20) == 8

    def test_full_usage_limit_when_user_zero(self):
        # When user does not set --concurrency, use full usage limit
        assert resolve_batch_concurrency(0, {"max_concurrency": 2000}, 5000) == 2000
        assert resolve_batch_concurrency(0, {"max_concurrency": 500}, 100) == 500

    def test_at_least_one(self):
        assert resolve_batch_concurrency(0, {"max_concurrency": 0}, 5) >= 1
        assert resolve_batch_concurrency(0, {}, 5) >= 1


class TestDefaultBatchOutputDir:
    """Tests for default_batch_output_dir()."""

    def test_format(self):
        name = default_batch_output_dir()
        assert name.startswith("batch_")
        # batch_YYYYMMDD_HHMMSS
        rest = name.replace("batch_", "")
        assert len(rest) == 15
        assert rest[8] == "_"


class TestExtensionFromContentType:
    """Tests for extension_from_content_type()."""

    def test_json(self):
        assert extension_from_content_type({"Content-Type": "application/json"}) == "json"
        assert (
            extension_from_content_type({"content-type": "application/json; charset=utf-8"})
            == "json"
        )

    def test_image(self):
        assert extension_from_content_type({"Content-Type": "image/png"}) == "png"
        assert extension_from_content_type({"Content-Type": "image/jpeg"}) == "jpg"

    def test_unidentified(self):
        assert extension_from_content_type({}) == "unidentified.txt"
        assert (
            extension_from_content_type({"Content-Type": "application/x-unknown"})
            == "unidentified.txt"
        )


class TestExtensionFromBodySniff:
    """Tests for extension_from_body_sniff()."""

    def test_png(self):
        assert extension_from_body_sniff(b"\x89PNG\r\n\x1a\nrest") == "png"

    def test_json(self):
        assert extension_from_body_sniff(b"  {") == "json"
        assert extension_from_body_sniff(b"[1,2]") == "json"

    def test_html(self):
        assert extension_from_body_sniff(b"<!doctype html>") == "html"

    def test_unknown(self):
        assert extension_from_body_sniff(b"???") is None


class TestExtensionForScrape:
    """Tests for extension_for_scrape(): body sniff first, then header."""

    def test_body_sniff_overrides_wrong_header(self):
        # API says text/plain but body is PNG
        ext = extension_for_scrape(
            {"Content-Type": "text/plain"},
            b"\x89PNG\r\n\x1a\n",
        )
        assert ext == "png"

    def test_falls_back_to_header(self):
        assert extension_for_scrape({"Content-Type": "image/jpeg"}, b"???") == "jpg"

    def test_unidentified(self):
        assert extension_for_scrape({}, b"???") == "unidentified.txt"


class TestWriteBatchOutputToDir:
    """Tests for write_batch_output_to_dir() file extensions."""

    def test_scrape_infers_extension(self, tmp_path):
        # expected_extension=None: infer from headers/body (scrape)
        results = [
            BatchResult(0, "u", b"{}", {"Content-Type": "application/json"}, 200, None, None),
            BatchResult(1, "u", b"<html/>", {"Content-Type": "text/html"}, 200, None, None),
            BatchResult(2, "u", b"???", {}, 200, None, None),
        ]
        out = write_batch_output_to_dir(results, str(tmp_path), verbose=False)
        assert out == str(tmp_path.resolve())
        assert (tmp_path / "1.json").read_bytes() == b"{}"
        assert (tmp_path / "2.html").read_bytes() == b"<html/>"
        assert (tmp_path / "3.unidentified.txt").read_bytes() == b"???"

    def test_documented_json_always_json(self, tmp_path):
        # expected_extension="json": always .json (google, amazon, etc.)
        results = [
            BatchResult(0, "u", b"{}", {"Content-Type": "text/plain"}, 200, None, "json"),
        ]
        write_batch_output_to_dir(results, str(tmp_path), verbose=False)
        assert (tmp_path / "1.json").read_bytes() == b"{}"

    def test_screenshots_and_files_subdirs(self, tmp_path):
        # Scrape-like (expected_extension=None): images → screenshots/, pdf/zip → files/
        results = [
            BatchResult(0, "u", b"\x89PNG\r\n\x1a\n", {}, 200, None, None),
            BatchResult(1, "u", b"binary", {"Content-Type": "application/pdf"}, 200, None, None),
            BatchResult(2, "u", b"{}", {}, 200, None, None),
        ]
        write_batch_output_to_dir(results, str(tmp_path), verbose=False)
        assert (tmp_path / "screenshots" / "1.png").read_bytes() == b"\x89PNG\r\n\x1a\n"
        assert (tmp_path / "files" / "2.pdf").read_bytes() == b"binary"
        assert (tmp_path / "3.json").read_bytes() == b"{}"

    def test_error_items_write_err_file(self, tmp_path):
        # When result.error is set, write N.err and skip success output for that item
        results = [
            BatchResult(0, "url1", b"{}", {}, 200, None, None),
            BatchResult(
                1,
                "url2",
                b"error body",
                {},
                500,
                RuntimeError("HTTP 500"),
                None,
            ),
            BatchResult(2, "url3", b"ok", {}, 200, None, "json"),
        ]
        write_batch_output_to_dir(results, str(tmp_path), verbose=False)
        assert (tmp_path / "1.json").read_bytes() == b"{}"
        assert (tmp_path / "2.err").read_bytes() == b"error body"
        assert (tmp_path / "3.json").read_bytes() == b"ok"
        assert not (tmp_path / "2.json").exists()

    def test_error_item_with_no_body_no_err_file(self, tmp_path):
        # When result.error is set but result.body is empty, no .err file written
        results = [
            BatchResult(1, "url2", b"", {}, 0, ConnectionError("fail"), None),
        ]
        write_batch_output_to_dir(results, str(tmp_path), verbose=False)
        assert not (tmp_path / "2.err").exists()
        assert not list(tmp_path.iterdir())  # no files written


class TestRunBatchAsync:
    """Tests for run_batch_async()."""

    def test_preserves_order(self):
        async def async_fn(inp: str):
            return b"ok", {}, 200, None, "json"

        results = asyncio.run(
            run_batch_async(["a", "b", "c"], concurrency=2, async_fn=async_fn)
        )
        assert len(results) == 3
        assert [r.input for r in results] == ["a", "b", "c"]
        assert [r.body for r in results] == [b"ok", b"ok", b"ok"]
        assert [r.error for r in results] == [None, None, None]

    def test_captures_exception_from_async_fn(self):
        async def async_fn(inp: str):
            raise ValueError("fail")

        results = asyncio.run(
            run_batch_async(["x"], concurrency=1, async_fn=async_fn)
        )
        assert len(results) == 1
        assert results[0].input == "x"
        assert results[0].body == b""
        assert results[0].headers == {}
        assert results[0].status_code == 0
        assert isinstance(results[0].error, ValueError)
        assert str(results[0].error) == "fail"

    def test_concurrency_capped_by_input_count(self):
        async def async_fn(inp: str):
            return inp.encode(), {}, 200, None, "json"

        results = asyncio.run(
            run_batch_async(["1", "2"], concurrency=10, async_fn=async_fn)
        )
        assert len(results) == 2
        assert results[0].body == b"1"
        assert results[1].body == b"2"


class TestGetBatchUsage:
    """Tests for get_batch_usage()."""

    def test_returns_usage_from_fetch(self):
        with patch("scrapingbee_cli.batch.get_api_key", return_value="fake-key"):
            with patch(
                "scrapingbee_cli.batch._fetch_usage_async",
                new_callable=AsyncMock,
                return_value={"max_concurrency": 10, "credits": 50},
            ):
                out = get_batch_usage(None)
        assert out["max_concurrency"] == 10
        assert out["credits"] == 50


class TestBatchSubdirForExtension:
    """Tests for _batch_subdir_for_extension()."""

    def test_screenshot_extensions(self):
        assert _batch_subdir_for_extension("png") == "screenshots"
        assert _batch_subdir_for_extension("jpg") == "screenshots"
        assert _batch_subdir_for_extension("gif") == "screenshots"
        assert _batch_subdir_for_extension("webp") == "screenshots"

    def test_binary_file_extensions(self):
        assert _batch_subdir_for_extension("pdf") == "files"
        assert _batch_subdir_for_extension("zip") == "files"

    def test_text_stays_in_root(self):
        assert _batch_subdir_for_extension("json") is None
        assert _batch_subdir_for_extension("html") is None
        assert _batch_subdir_for_extension("txt") is None
        assert _batch_subdir_for_extension("unidentified.txt") is None
