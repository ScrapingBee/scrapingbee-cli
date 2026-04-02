"""Tests for functions that previously had zero coverage.

Covers: run_on_complete, write_ndjson_line, _max_nesting_depth,
_flatten_dict (max_depth), _export_csv error paths,
_validate_api_key, _auto_name, _format_running_since.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# run_on_complete
# ---------------------------------------------------------------------------
class TestRunOnComplete:
    """Tests for cli_utils.run_on_complete()."""

    def test_no_op_when_cmd_is_none(self):
        from scrapingbee_cli.cli_utils import run_on_complete

        # Should return without error and without calling subprocess
        with patch("subprocess.run") as mock_run:
            run_on_complete(None)
        mock_run.assert_not_called()

    def test_no_op_when_cmd_is_empty_string(self):
        from scrapingbee_cli.cli_utils import run_on_complete

        with patch("subprocess.run") as mock_run:
            run_on_complete("")
        mock_run.assert_not_called()

    def test_env_vars_injected(self):
        from scrapingbee_cli.cli_utils import run_on_complete

        captured_env: dict = {}

        def fake_run(cmd, shell, env):  # noqa: ANN001
            captured_env.update(env)
            m = MagicMock()
            m.returncode = 0
            return m

        with (
            patch("subprocess.run", side_effect=fake_run),
            patch("scrapingbee_cli.exec_gate.require_exec"),
            patch("scrapingbee_cli.audit.log_exec"),
        ):
            run_on_complete(
                "echo done",
                output_dir="/tmp/batch",
                output_file="/tmp/out.csv",
                succeeded=5,
                failed=1,
            )

        assert captured_env["SCRAPINGBEE_OUTPUT_DIR"] == "/tmp/batch"
        assert captured_env["SCRAPINGBEE_OUTPUT_FILE"] == "/tmp/out.csv"
        assert captured_env["SCRAPINGBEE_SUCCEEDED"] == "5"
        assert captured_env["SCRAPINGBEE_FAILED"] == "1"

    def test_nonzero_exit_code_echoed(self, capsys):
        from scrapingbee_cli.cli_utils import run_on_complete

        m = MagicMock()
        m.returncode = 2

        with (
            patch("subprocess.run", return_value=m),
            patch("scrapingbee_cli.exec_gate.require_exec"),
            patch("scrapingbee_cli.audit.log_exec"),
        ):
            run_on_complete("false")

        err = capsys.readouterr().err
        assert "2" in err


# ---------------------------------------------------------------------------
# write_ndjson_line
# ---------------------------------------------------------------------------
class TestWriteNdjsonLine:
    """Tests for batch.write_ndjson_line()."""

    def _make_result(
        self,
        index: int = 0,
        input: str = "https://example.com",  # noqa: A002
        body: bytes = b'{"title": "Test"}',
        headers: dict = None,  # type: ignore[assignment]
        status_code: int = 200,
        error: Exception | None = None,
        skipped: bool = False,
        fetched_at: str = "2024-01-15T10:00:00+00:00",
        latency_ms: int | None = 123,
    ):
        from scrapingbee_cli.batch import BatchResult

        return BatchResult(
            index=index,
            input=input,
            body=body,
            headers=headers if headers is not None else {},
            status_code=status_code,
            error=error,
            skipped=skipped,
            fetched_at=fetched_at,
            latency_ms=latency_ms,
        )

    def test_skipped_result_writes_nothing(self):
        from scrapingbee_cli.batch import write_ndjson_line

        buf = io.StringIO()
        write_ndjson_line(self._make_result(skipped=True), fh=buf)
        assert buf.getvalue() == ""

    def test_writes_valid_json_line(self):
        from scrapingbee_cli.batch import write_ndjson_line

        buf = io.StringIO()
        write_ndjson_line(self._make_result(), fh=buf)
        line = buf.getvalue().strip()
        obj = json.loads(line)
        assert obj["index"] == 1  # index + 1
        assert obj["input"] == "https://example.com"
        assert obj["status_code"] == 200
        assert obj["body"] == {"title": "Test"}
        assert obj["error"] is None
        assert obj["fetched_at"] == "2024-01-15T10:00:00+00:00"
        assert obj["latency_ms"] == 123

    def test_non_json_body_stored_as_string(self):
        from scrapingbee_cli.batch import write_ndjson_line

        buf = io.StringIO()
        write_ndjson_line(self._make_result(body=b"<html>hi</html>"), fh=buf)
        obj = json.loads(buf.getvalue().strip())
        assert isinstance(obj["body"], str)
        assert "html" in obj["body"]

    def test_error_serialized_as_string(self):
        from scrapingbee_cli.batch import write_ndjson_line

        buf = io.StringIO()
        write_ndjson_line(self._make_result(error=RuntimeError("boom"), body=b""), fh=buf)
        obj = json.loads(buf.getvalue().strip())
        assert obj["error"] == "boom"

    def test_writes_to_stdout_when_no_fh(self, capsys):
        from scrapingbee_cli.batch import write_ndjson_line

        write_ndjson_line(self._make_result())
        out = capsys.readouterr().out
        obj = json.loads(out.strip())
        assert obj["index"] == 1


# ---------------------------------------------------------------------------
# _max_nesting_depth
# ---------------------------------------------------------------------------
class TestMaxNestingDepth:
    """Tests for export._max_nesting_depth()."""

    def test_flat_dict_is_depth_0(self):
        from scrapingbee_cli.commands.export import _max_nesting_depth

        assert _max_nesting_depth({"a": 1, "b": "x"}) == 0

    def test_one_level_nested(self):
        from scrapingbee_cli.commands.export import _max_nesting_depth

        assert _max_nesting_depth({"a": {"b": 1}}) == 1

    def test_three_levels_nested(self):
        from scrapingbee_cli.commands.export import _max_nesting_depth

        d = {"a": {"b": {"c": {"d": 1}}}}
        assert _max_nesting_depth(d) == 3

    def test_list_of_dicts_counts_one_level(self):
        from scrapingbee_cli.commands.export import _max_nesting_depth

        d = {"items": [{"price": 10}, {"price": 20}]}
        assert _max_nesting_depth(d) == 1

    def test_mixed_depth_returns_max(self):
        from scrapingbee_cli.commands.export import _max_nesting_depth

        d = {"a": {"b": 1}, "c": {"d": {"e": 2}}}
        assert _max_nesting_depth(d) == 2


# ---------------------------------------------------------------------------
# _flatten_dict with max_depth
# ---------------------------------------------------------------------------
class TestFlattenDictMaxDepth:
    """Tests for export._flatten_dict() max_depth behaviour."""

    def test_flat_dict_unchanged(self):
        from scrapingbee_cli.commands.export import _flatten_dict

        result = _flatten_dict({"a": 1, "b": "x"})
        assert result == {"a": "1", "b": "x"}

    def test_depth_0_json_encodes_nested_dict(self):
        from scrapingbee_cli.commands.export import _flatten_dict

        result = _flatten_dict({"a": {"b": 1}}, max_depth=0)
        assert result["a"] == '{"b": 1}'

    def test_depth_1_flattens_one_level(self):
        from scrapingbee_cli.commands.export import _flatten_dict

        result = _flatten_dict({"a": {"b": {"c": 1}}}, max_depth=1)
        # First level is flattened: a.b exists, but a.b.c is JSON-encoded
        assert "a.b" in result
        assert result["a.b"] == '{"c": 1}'

    def test_default_depth_is_5(self):
        from scrapingbee_cli.commands.export import _DEFAULT_FLATTEN_DEPTH

        assert _DEFAULT_FLATTEN_DEPTH == 5

    def test_list_of_dicts_indexed(self):
        from scrapingbee_cli.commands.export import _flatten_dict

        result = _flatten_dict({"items": [{"price": "10"}, {"price": "20"}]})
        assert result["items.0.price"] == "10"
        assert result["items.1.price"] == "20"

    def test_empty_list_stored_as_empty_string(self):
        from scrapingbee_cli.commands.export import _flatten_dict

        result = _flatten_dict({"tags": []})
        assert result["tags"] == ""

    def test_none_value_stored_as_empty_string(self):
        from scrapingbee_cli.commands.export import _flatten_dict

        result = _flatten_dict({"x": None})
        assert result["x"] == ""


# ---------------------------------------------------------------------------
# _export_csv error paths
# ---------------------------------------------------------------------------
class TestExportCsvErrorPaths:
    """Tests for _export_csv() error cases."""

    def _make_entry(self, tmp_path: Path, data: object, name: str = "1.json"):
        p = tmp_path / name
        p.write_text(json.dumps(data), encoding="utf-8")
        n = int(Path(name).stem)
        return (n, p, name)

    def test_columns_no_match_exits_with_available_list(self, tmp_path, capsys):
        from scrapingbee_cli.commands.export import _export_csv

        entry = self._make_entry(tmp_path, [{"title": "foo", "price": "10"}])
        with pytest.raises(SystemExit):
            _export_csv([entry], {}, None, columns="nonexistent_col")
        err = capsys.readouterr().err
        assert "nonexistent_col" in err
        assert "title" in err or "price" in err  # available columns listed

    def test_all_rows_dropped_exits(self, tmp_path, capsys):
        from scrapingbee_cli.commands.export import _export_csv

        entry = self._make_entry(tmp_path, [{"title": "foo"}, {"other": "bar"}])
        # Select a column that exists in some rows but filter leaves no rows
        # This case: all rows have "title" or "other"; selecting "missing" → no valid rows
        with pytest.raises(SystemExit):
            _export_csv([entry], {}, None, columns="missing_column")
        err = capsys.readouterr().err
        assert "missing_column" in err

    def test_depth_exceeds_default_exits(self, tmp_path, capsys):
        from scrapingbee_cli.commands.export import _DEFAULT_FLATTEN_DEPTH, _export_csv

        # Build a dict nested deeper than _DEFAULT_FLATTEN_DEPTH
        deep: dict = {}
        node = deep
        for i in range(_DEFAULT_FLATTEN_DEPTH + 2):
            node["child"] = {}
            node = node["child"]
        node["value"] = "leaf"

        entry = self._make_entry(tmp_path, [deep])
        with pytest.raises(SystemExit):
            _export_csv([entry], {}, None, flatten=True)
        err = capsys.readouterr().err
        assert "nesting depth" in err.lower() or "flatten-depth" in err

    def test_no_json_files_exits(self, tmp_path, capsys):
        from scrapingbee_cli.commands.export import _export_csv

        # Only .html file → no JSON rows
        p = tmp_path / "1.html"
        p.write_text("<html></html>")
        entry = (1, p, "1.html")
        with pytest.raises(SystemExit):
            _export_csv([entry], {}, None)
        err = capsys.readouterr().err
        assert "No JSON" in err


# ---------------------------------------------------------------------------
# _validate_api_key
# ---------------------------------------------------------------------------
class TestValidateApiKey:
    """Tests for auth._validate_api_key()."""

    def test_200_returns_true(self):
        from scrapingbee_cli.commands.auth import _validate_api_key

        with patch("asyncio.run", return_value=(200, b"{}")):
            ok, msg = _validate_api_key("good-key")
        assert ok is True
        assert msg == ""

    def test_401_returns_false_with_message(self):
        from scrapingbee_cli.commands.auth import _validate_api_key

        payload = json.dumps({"message": "Invalid API key."}).encode()
        with patch("asyncio.run", return_value=(401, payload)):
            ok, msg = _validate_api_key("bad-key")
        assert ok is False
        assert "Invalid" in msg

    def test_401_no_message_falls_back_to_default(self):
        from scrapingbee_cli.commands.auth import _validate_api_key

        with patch("asyncio.run", return_value=(401, b"{}")):
            ok, msg = _validate_api_key("bad-key")
        assert ok is False
        assert msg  # non-empty fallback

    def test_oserror_returns_network_error(self):

        from scrapingbee_cli.commands.auth import _validate_api_key

        with patch("asyncio.run", side_effect=OSError("Connection refused")):
            ok, msg = _validate_api_key("any-key")
        assert ok is False
        assert "Network error" in msg or "network" in msg.lower()

    def test_timeout_error_returns_false(self):
        import asyncio

        from scrapingbee_cli.commands.auth import _validate_api_key

        # In Python 3.11+, asyncio.TimeoutError is a subclass of OSError,
        # so it's caught by the OSError branch and returns "Network error: ..."
        with patch("asyncio.run", side_effect=asyncio.TimeoutError()):
            ok, msg = _validate_api_key("any-key")
        assert ok is False
        assert msg  # some non-empty error message is returned

    def test_non_200_non_401_returns_status(self):
        from scrapingbee_cli.commands.auth import _validate_api_key

        with patch("asyncio.run", return_value=(503, b"{}")):
            ok, msg = _validate_api_key("any-key")
        assert ok is False
        assert "503" in msg


# ---------------------------------------------------------------------------
# _auto_name
# ---------------------------------------------------------------------------
class TestAutoName:
    """Tests for schedule._auto_name()."""

    def test_uses_first_two_non_flag_args(self):
        from scrapingbee_cli.commands.schedule import _auto_name

        result = _auto_name(("scrape", "https://example.com", "--output-dir", "out"))
        assert "scrape" in result
        # Should not include flag names
        assert "--output-dir" not in result

    def test_special_chars_replaced_with_hyphens(self):
        from scrapingbee_cli.commands.schedule import _auto_name

        result = _auto_name(("scrape", "https://example.com/path?q=1"))
        assert " " not in result
        # Only safe chars remain
        import re

        assert re.match(r"^[a-zA-Z0-9_-]+$", result)

    def test_empty_args_uses_pid(self):
        from scrapingbee_cli.commands.schedule import _auto_name

        result = _auto_name(())
        assert result.startswith("schedule-")

    def test_only_bool_flags_uses_pid(self):
        from scrapingbee_cli.commands.schedule import _auto_name

        # Only args starting with "-" → parts is empty
        result = _auto_name(("--verbose", "--no-progress"))
        assert result.startswith("schedule-")

    def test_result_max_30_chars(self):
        from scrapingbee_cli.commands.schedule import _auto_name

        long_arg = "a" * 50
        result = _auto_name((long_arg,))
        assert len(result) <= 30


# ---------------------------------------------------------------------------
# _format_running_since
# ---------------------------------------------------------------------------
class TestFormatRunningSince:
    """Tests for schedule._format_running_since()."""

    def _ts(self, delta: timedelta) -> str:
        return (datetime.now() - delta).strftime("%Y-%m-%d %H:%M:%S")

    def test_seconds(self):
        from scrapingbee_cli.commands.schedule import _format_running_since

        result = _format_running_since(self._ts(timedelta(seconds=30)))
        assert result.endswith("s")

    def test_minutes(self):
        from scrapingbee_cli.commands.schedule import _format_running_since

        result = _format_running_since(self._ts(timedelta(minutes=5)))
        assert result.endswith("m")

    def test_hours(self):
        from scrapingbee_cli.commands.schedule import _format_running_since

        result = _format_running_since(self._ts(timedelta(hours=3, minutes=30)))
        assert "h" in result
        assert "m" in result

    def test_days(self):
        from scrapingbee_cli.commands.schedule import _format_running_since

        result = _format_running_since(self._ts(timedelta(days=2, hours=5)))
        assert "d" in result
        assert "h" in result

    def test_malformed_returns_question_mark(self):
        from scrapingbee_cli.commands.schedule import _format_running_since

        assert _format_running_since("not-a-date") == "?"
        assert _format_running_since("") == "?"
