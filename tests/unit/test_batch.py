"""Unit tests for batch module."""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from scrapingbee_cli.batch import (
    CONCURRENCY_CAP,
    MIN_CREDITS_TO_RUN_BATCH,
    BatchResult,
    _find_completed_n,
    extension_for_scrape,
    extension_from_body_sniff,
    extension_from_content_type,
    resolve_batch_concurrency,
    run_batch_async,
    validate_batch_run,
    write_batch_output_to_dir,
)


class TestValidateBatchRun:
    """Tests for validate_batch_run()."""

    def test_passes_with_sufficient_credits(self):
        validate_batch_run(0, 10, {"credits": MIN_CREDITS_TO_RUN_BATCH, "max_concurrency": 5})

    def test_raises_when_credits_below_minimum(self):
        usage = {"credits": MIN_CREDITS_TO_RUN_BATCH - 1, "max_concurrency": 5}
        with pytest.raises(ValueError, match="insufficient credits"):
            validate_batch_run(0, 10, usage)

    def test_raises_when_credits_zero(self):
        usage = {"credits": 0, "max_concurrency": 5}
        with pytest.raises(ValueError, match="insufficient credits"):
            validate_batch_run(0, 1, usage)

    def test_raises_when_user_concurrency_exceeds_plan(self):
        usage = {"credits": 500, "max_concurrency": 5}
        with pytest.raises(ValueError, match="exceeds your plan limit"):
            validate_batch_run(10, 10, usage)

    def test_passes_when_user_concurrency_equals_plan_limit(self):
        usage = {"credits": 500, "max_concurrency": 5}
        validate_batch_run(5, 10, usage)  # exactly at limit — should not raise

    def test_auto_concurrency_never_raises_for_concurrency(self):
        """user_concurrency=0 means auto; plan-limit check is skipped."""
        usage = {"credits": 500, "max_concurrency": 1}
        validate_batch_run(0, 100, usage)  # should not raise

    def test_uses_default_max_concurrency_when_key_missing(self):
        """Default max_concurrency is 5 when key absent from usage dict."""
        usage = {"credits": 500}  # no max_concurrency key
        validate_batch_run(5, 10, usage)  # 5 <= default 5 — no raise
        with pytest.raises(ValueError, match="exceeds your plan limit"):
            validate_batch_run(6, 10, usage)  # 6 > default 5

    def test_error_message_includes_available_credits(self):
        usage = {"credits": 42, "max_concurrency": 5}
        with pytest.raises(ValueError, match="42"):
            validate_batch_run(0, 1, usage)

    def test_error_message_includes_plan_limit(self):
        usage = {"credits": 500, "max_concurrency": 3}
        with pytest.raises(ValueError, match="3"):
            validate_batch_run(10, 1, usage)


class TestFindCompletedN:
    """Tests for _find_completed_n()."""

    def test_returns_empty_for_nonexistent_dir(self):
        assert _find_completed_n("/nonexistent/path/xyz") == frozenset()

    def test_finds_numbered_files(self, tmp_path):
        (tmp_path / "1.json").write_text("{}")
        (tmp_path / "2.json").write_text("{}")
        (tmp_path / "3.html").write_text("<html/>")
        result = _find_completed_n(str(tmp_path))
        assert result == frozenset({1, 2, 3})

    def test_ignores_err_files(self, tmp_path):
        (tmp_path / "1.json").write_text("{}")
        (tmp_path / "2.err").write_text("Error")
        result = _find_completed_n(str(tmp_path))
        assert result == frozenset({1})  # 2.err not included

    def test_ignores_non_numeric_files(self, tmp_path):
        (tmp_path / "1.json").write_text("{}")
        (tmp_path / "manifest.json").write_text("{}")
        (tmp_path / "failures.txt").write_text("")
        result = _find_completed_n(str(tmp_path))
        assert result == frozenset({1})

    def test_finds_files_in_subdirs(self, tmp_path):
        screenshots = tmp_path / "screenshots"
        screenshots.mkdir()
        (tmp_path / "1.html").write_text("<html/>")
        (screenshots / "2.png").write_bytes(b"\x89PNG")
        result = _find_completed_n(str(tmp_path))
        assert result == frozenset({1, 2})


class TestRunBatchAsyncSkipN:
    """Tests for run_batch_async skip_n (resume) behaviour."""

    def test_skip_n_items_are_marked_skipped(self):
        async def do_one(inp: str):
            return inp.encode(), {}, 200, None, "txt"

        async def run():
            return await run_batch_async(
                ["a", "b", "c"],
                concurrency=3,
                async_fn=do_one,
                skip_n=frozenset({2}),  # skip item 2 (index 1)
            )

        results = asyncio.run(run())
        assert len(results) == 3
        assert results[0].skipped is False
        assert results[1].skipped is True  # index 1 → item 2
        assert results[1].body == b""
        assert results[2].skipped is False

    def test_skip_n_empty_processes_all(self):
        calls = []

        async def do_one(inp: str):
            calls.append(inp)
            return inp.encode(), {}, 200, None, None

        async def run():
            return await run_batch_async(
                ["a", "b"],
                concurrency=2,
                async_fn=do_one,
                skip_n=frozenset(),
            )

        asyncio.run(run())
        assert set(calls) == {"a", "b"}


class TestWriteBatchOutputToDir:
    """Tests for write_batch_output_to_dir manifest.json writing."""

    def _make_result(
        self,
        index,
        input_,
        body,
        status_code=200,
        ext="json",
        fetched_at="2025-01-01T00:00:00+00:00",
    ):
        return BatchResult(
            index=index,
            input=input_,
            body=body,
            headers={"content-type": "application/json"},
            status_code=status_code,
            error=None,
            expected_extension=ext,
            fetched_at=fetched_at,
        )

    def test_manifest_written_with_correct_structure(self, tmp_path):
        """manifest.json maps each input to {file, fetched_at, http_status}."""
        results = [
            self._make_result(
                0, "https://example.com/a", b'{"a":1}', fetched_at="2025-01-01T00:00:00+00:00"
            ),
            self._make_result(
                1, "https://example.com/b", b'{"b":2}', fetched_at="2025-01-02T00:00:00+00:00"
            ),
        ]
        write_batch_output_to_dir(results, str(tmp_path), verbose=False)

        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.exists(), "manifest.json should be written"
        manifest = json.loads(manifest_path.read_text())

        assert set(manifest.keys()) == {"https://example.com/a", "https://example.com/b"}
        entry_a = manifest["https://example.com/a"]
        assert entry_a["file"] == "1.json"
        assert entry_a["fetched_at"] == "2025-01-01T00:00:00+00:00"
        assert entry_a["http_status"] == 200

        entry_b = manifest["https://example.com/b"]
        assert entry_b["file"] == "2.json"
        assert entry_b["fetched_at"] == "2025-01-02T00:00:00+00:00"
        assert entry_b["http_status"] == 200

    def test_manifest_omits_errors(self, tmp_path):
        """Failed items (error not None) are not included in manifest.json."""
        results = [
            self._make_result(0, "https://example.com/ok", b'{"ok":true}'),
            BatchResult(
                index=1,
                input="https://example.com/fail",
                body=b"",
                headers={},
                status_code=0,
                error=RuntimeError("timeout"),
                fetched_at="",
            ),
        ]
        write_batch_output_to_dir(results, str(tmp_path), verbose=False)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert "https://example.com/ok" in manifest
        assert "https://example.com/fail" not in manifest

    def test_manifest_omits_skipped(self, tmp_path):
        """Skipped items (resume mode) are not included in manifest.json."""
        results = [
            self._make_result(0, "https://example.com/done", b'{"done":true}'),
            BatchResult(
                index=1,
                input="https://example.com/skip",
                body=b"",
                headers={},
                status_code=0,
                error=None,
                skipped=True,
                fetched_at="",
            ),
        ]
        write_batch_output_to_dir(results, str(tmp_path), verbose=False)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert "https://example.com/done" in manifest
        assert "https://example.com/skip" not in manifest

    def test_no_manifest_when_all_fail(self, tmp_path):
        """manifest.json is not written when there are no successful items."""
        results = [
            BatchResult(
                index=0,
                input="https://example.com/bad",
                body=b"",
                headers={},
                status_code=0,
                error=RuntimeError("fail"),
                fetched_at="",
            ),
        ]
        write_batch_output_to_dir(results, str(tmp_path), verbose=False)
        assert not (tmp_path / "manifest.json").exists()

    def test_screenshot_uses_subdir_in_manifest(self, tmp_path):
        """Screenshot outputs are stored in screenshots/ and manifest reflects that."""
        result = BatchResult(
            index=0,
            input="https://example.com/page",
            body=b"\x89PNG\r\n\x1a\n" + b"\x00" * 8,  # PNG magic bytes
            headers={"content-type": "image/png"},
            status_code=200,
            error=None,
            expected_extension="png",
            fetched_at="2025-01-01T00:00:00+00:00",
        )
        write_batch_output_to_dir([result], str(tmp_path), verbose=False)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["https://example.com/page"]["file"] == "screenshots/1.png"


class TestWriteBatchOutputToDirManifestFields:
    """Tests that manifest.json contains credits_used, latency_ms, content_sha256 (T-04)."""

    def _make_result(self, index, input_, body, headers=None, latency_ms=None):
        return BatchResult(
            index=index,
            input=input_,
            body=body,
            headers=headers or {"content-type": "application/json"},
            status_code=200,
            error=None,
            expected_extension="json",
            fetched_at="2025-01-01T00:00:00+00:00",
            latency_ms=latency_ms,
        )

    def test_manifest_has_credits_used_from_spb_cost_header(self, tmp_path):
        result = self._make_result(
            0,
            "https://example.com/a",
            b'{"x":1}',
            headers={"Spb-Cost": "5", "content-type": "application/json"},
            latency_ms=100,
        )
        write_batch_output_to_dir([result], str(tmp_path), verbose=False)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["https://example.com/a"]["credits_used"] == 5

    def test_manifest_credits_used_none_when_no_spb_cost_header(self, tmp_path):
        result = self._make_result(0, "https://example.com/a", b'{"x":1}')
        write_batch_output_to_dir([result], str(tmp_path), verbose=False)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["https://example.com/a"]["credits_used"] is None

    def test_manifest_has_latency_ms(self, tmp_path):
        result = self._make_result(0, "https://example.com/a", b'{"x":1}', latency_ms=987)
        write_batch_output_to_dir([result], str(tmp_path), verbose=False)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["https://example.com/a"]["latency_ms"] == 987

    def test_manifest_latency_ms_none_when_not_set(self, tmp_path):
        result = self._make_result(0, "https://example.com/a", b'{"x":1}', latency_ms=None)
        write_batch_output_to_dir([result], str(tmp_path), verbose=False)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["https://example.com/a"]["latency_ms"] is None

    def test_manifest_has_content_sha256(self, tmp_path):
        body = b'{"x":1}'
        expected_sha256 = hashlib.sha256(body).hexdigest()
        result = self._make_result(0, "https://example.com/a", body)
        write_batch_output_to_dir([result], str(tmp_path), verbose=False)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["https://example.com/a"]["content_sha256"] == expected_sha256

    def test_credits_used_int_parsed_correctly(self, tmp_path):
        result = self._make_result(
            0,
            "https://example.com/a",
            b'{"x":1}',
            headers={"spb-cost": "15", "content-type": "application/json"},
        )
        write_batch_output_to_dir([result], str(tmp_path), verbose=False)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["https://example.com/a"]["credits_used"] == 15


class TestResolveBatchConcurrency:
    """Tests for resolve_batch_concurrency()."""

    def test_zero_returns_usage_limit(self):
        result = resolve_batch_concurrency(0, {"max_concurrency": 10}, 5, warn=False)
        assert result == 10

    def test_zero_with_zero_limit_uses_fallback(self):
        # max_concurrency=0 is treated as "unset" (or 5 fallback), so returns 5
        result = resolve_batch_concurrency(0, {"max_concurrency": 0}, 5, warn=False)
        assert result == 5

    def test_user_value_within_limits_returned(self):
        result = resolve_batch_concurrency(5, {"max_concurrency": 10}, 20, warn=False)
        assert result == 5

    def test_user_value_capped_at_plan_limit(self):
        result = resolve_batch_concurrency(15, {"max_concurrency": 10}, 20, warn=False)
        assert result == 10

    def test_user_value_capped_at_concurrency_cap(self):
        # CONCURRENCY_CAP=100; even if plan allows 200, cap wins
        result = resolve_batch_concurrency(200, {"max_concurrency": 200}, 300, warn=False)
        assert result == CONCURRENCY_CAP

    def test_default_max_concurrency_when_key_missing(self):
        # No max_concurrency key → defaults to 5
        result = resolve_batch_concurrency(0, {}, 10, warn=False)
        assert result == 5

    def test_warn_false_suppresses_warning(self, capsys):
        resolve_batch_concurrency(200, {"max_concurrency": 200}, 300, warn=False)
        assert capsys.readouterr().err == ""

    def test_warn_true_prints_warning_when_capped(self, capsys):
        resolve_batch_concurrency(200, {"max_concurrency": 200}, 300, warn=True)
        assert "capped" in capsys.readouterr().err


class TestExtensionFromContentType:
    """Tests for extension_from_content_type()."""

    def test_json_content_type(self):
        assert extension_from_content_type({"content-type": "application/json"}) == "json"

    def test_html_content_type(self):
        assert extension_from_content_type({"content-type": "text/html"}) == "html"

    def test_png_content_type(self):
        assert extension_from_content_type({"content-type": "image/png"}) == "png"

    def test_unknown_content_type_returns_bin(self):
        assert extension_from_content_type({"content-type": "application/octet-stream"}) == "bin"

    def test_empty_headers_returns_bin(self):
        assert extension_from_content_type({}) == "bin"

    def test_charset_stripped(self):
        assert (
            extension_from_content_type({"content-type": "application/json; charset=utf-8"})
            == "json"
        )

    def test_case_insensitive_header_key(self):
        assert extension_from_content_type({"Content-Type": "text/html"}) == "html"

    def test_missing_content_type_returns_bin(self):
        assert extension_from_content_type({"x-custom": "value"}) == "bin"


class TestExtensionFromBodySniff:
    """Tests for extension_from_body_sniff()."""

    def test_png_magic_bytes(self):
        assert extension_from_body_sniff(b"\x89PNG\r\n\x1a\ndata") == "png"

    def test_jpg_magic_bytes(self):
        assert extension_from_body_sniff(b"\xff\xd8\xff\xe0data") == "jpg"

    def test_gif_magic_bytes(self):
        assert extension_from_body_sniff(b"GIF89adata") == "gif"

    def test_webp_magic_bytes(self):
        assert extension_from_body_sniff(b"RIFF\x00\x00\x00\x00WEBPdata") == "webp"

    def test_json_object_body(self):
        assert extension_from_body_sniff(b'{"key": "value"}') == "json"

    def test_json_array_body(self):
        assert extension_from_body_sniff(b'[{"a":1}]') == "json"

    def test_html_body(self):
        assert extension_from_body_sniff(b"<!DOCTYPE html><html>") == "html"

    def test_html_lowercase(self):
        assert extension_from_body_sniff(b"<html><body>") == "html"

    def test_markdown_body(self):
        body = b"[link text](https://example.com) some more text"
        assert extension_from_body_sniff(body) == "md"

    def test_empty_body_returns_none(self):
        assert extension_from_body_sniff(b"") is None

    def test_unknown_body_returns_none(self):
        assert extension_from_body_sniff(b"random binary data \x00\x01\x02") is None


class TestExtensionForScrape:
    """Tests for extension_for_scrape(): sniff > Content-Type > bin."""

    def test_sniff_wins_over_content_type(self):
        # PNG bytes but wrong content-type header → sniff wins
        body = b"\x89PNG\r\n\x1a\ndata"
        headers = {"content-type": "application/json"}
        assert extension_for_scrape(headers, body) == "png"

    def test_falls_back_to_content_type_when_no_sniff(self):
        # Unrecognisable bytes but valid content-type
        body = b"random bytes \x00\x01"
        headers = {"content-type": "application/json"}
        assert extension_for_scrape(headers, body) == "json"

    def test_falls_back_to_bin_when_unknown(self):
        body = b"random bytes \x00\x01"
        headers = {"content-type": "application/octet-stream"}
        assert extension_for_scrape(headers, body) == "bin"

    def test_json_body_overrides_bin_header(self):
        body = b'{"result": true}'
        headers = {"content-type": "application/octet-stream"}
        assert extension_for_scrape(headers, body) == "json"


class TestReadInputFile:
    """Tests for read_input_file()."""

    def test_reads_lines_from_file(self, tmp_path):
        from scrapingbee_cli.batch import read_input_file

        f = tmp_path / "input.txt"
        f.write_text("https://a.com\nhttps://b.com\nhttps://c.com\n")
        result = read_input_file(str(f))
        assert result == ["https://a.com", "https://b.com", "https://c.com"]

    def test_strips_whitespace(self, tmp_path):
        from scrapingbee_cli.batch import read_input_file

        f = tmp_path / "input.txt"
        f.write_text("  https://a.com  \n  https://b.com  \n")
        result = read_input_file(str(f))
        assert result == ["https://a.com", "https://b.com"]

    def test_skips_empty_lines(self, tmp_path):
        from scrapingbee_cli.batch import read_input_file

        f = tmp_path / "input.txt"
        f.write_text("https://a.com\n\n\nhttps://b.com\n\n")
        result = read_input_file(str(f))
        assert result == ["https://a.com", "https://b.com"]

    def test_empty_file_raises_value_error(self, tmp_path):
        from scrapingbee_cli.batch import read_input_file

        f = tmp_path / "empty.txt"
        f.write_text("\n\n\n")
        with pytest.raises(ValueError, match="no non-empty lines"):
            read_input_file(str(f))

    def test_nonexistent_file_raises_value_error(self):
        from scrapingbee_cli.batch import read_input_file

        with pytest.raises(ValueError, match="cannot open"):
            read_input_file("/nonexistent/path/file.txt")
