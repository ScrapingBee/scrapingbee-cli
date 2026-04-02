"""Unit tests for v1.3.2 changes.

Covers:
1. user_agent_headers() — structured headers dict
2. read_audit_log() with since/until datetime filtering
3. _validate_schedule_name() — alphanumeric + hyphens/underscores
4. _duration_to_cron() — seconds rounding warning
5. find_incomplete_batches() / _save_batch_meta()
6. _handle_resume() — bare scrapingbee --resume discovery
7. _handle_scraping_config() — auto-route to scrape
8. confirm_overwrite() — prompt on existing file
9. store_common_options() — batch-only flag validation
10. --output-format no longer accepts "files"
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import click
import pytest

# =============================================================================
# 1. user_agent_headers()
# =============================================================================


class TestUserAgentHeaders:
    """Tests for user_agent_headers() structured headers dict."""

    def test_returns_dict(self):
        from scrapingbee_cli import user_agent_headers

        result = user_agent_headers()
        assert isinstance(result, dict)

    def test_user_agent_key_is_scrapingbee_cli(self):
        from scrapingbee_cli import user_agent_headers

        result = user_agent_headers()
        assert result["User-Agent"] == "ScrapingBee/CLI"

    def test_client_key_present(self):
        from scrapingbee_cli import user_agent_headers

        result = user_agent_headers()
        assert result["User-Agent-Client"] == "scrapingbee-cli"

    def test_version_key_matches_package(self):
        from scrapingbee_cli import __version__, user_agent_headers

        result = user_agent_headers()
        assert result["User-Agent-Client-Version"] == __version__

    def test_environment_key_is_python(self):
        from scrapingbee_cli import user_agent_headers

        result = user_agent_headers()
        assert result["User-Agent-Environment"] == "python"

    def test_environment_version_is_current_python(self):
        from scrapingbee_cli import user_agent_headers

        result = user_agent_headers()
        expected = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        assert result["User-Agent-Environment-Version"] == expected

    def test_os_key_contains_platform_info(self):
        import platform

        from scrapingbee_cli import user_agent_headers

        result = user_agent_headers()
        os_val = result["User-Agent-OS"]
        assert platform.system() in os_val
        assert platform.machine() in os_val

    def test_all_values_are_strings(self):
        from scrapingbee_cli import user_agent_headers

        result = user_agent_headers()
        for k, v in result.items():
            assert isinstance(v, str), f"{k}: expected str, got {type(v)}"


# =============================================================================
# 2. read_audit_log() datetime filtering
# =============================================================================


class TestAuditLogDatetimeFilter:
    """Tests for read_audit_log() with since/until params."""

    def _write_entries(self, log_path: Path, timestamps: list[str]) -> None:
        """Write audit log lines with given ISO timestamps."""
        lines = [f"{ts} | post-process | jq .title |  | \n" for ts in timestamps]
        log_path.write_text("".join(lines), encoding="utf-8")

    def test_since_filters_older_entries(self, tmp_path):
        from scrapingbee_cli.audit import read_audit_log

        log_path = tmp_path / "audit.log"
        self._write_entries(
            log_path,
            [
                "2024-01-01T10:00:00+00:00",
                "2024-01-02T10:00:00+00:00",
                "2024-01-03T10:00:00+00:00",
            ],
        )
        since = datetime(2024, 1, 2, tzinfo=timezone.utc)
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            result = read_audit_log(since=since)
        assert "2024-01-01" not in result
        assert "2024-01-02" in result
        assert "2024-01-03" in result

    def test_until_filters_newer_entries(self, tmp_path):
        from scrapingbee_cli.audit import read_audit_log

        log_path = tmp_path / "audit.log"
        # Use midnight timestamps so until=Jan2 includes Jan1 and Jan2 (midnight = inclusive)
        self._write_entries(
            log_path,
            [
                "2024-01-01T00:00:00+00:00",
                "2024-01-02T00:00:00+00:00",
                "2024-01-03T00:00:00+00:00",
            ],
        )
        until = datetime(2024, 1, 2, tzinfo=timezone.utc)
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            result = read_audit_log(until=until)
        assert "2024-01-01" in result
        assert "2024-01-02" in result
        assert "2024-01-03" not in result

    def test_since_and_until_range(self, tmp_path):
        from scrapingbee_cli.audit import read_audit_log

        log_path = tmp_path / "audit.log"
        self._write_entries(
            log_path,
            [
                "2024-01-01T00:00:00+00:00",
                "2024-01-02T00:00:00+00:00",
                "2024-01-03T00:00:00+00:00",
                "2024-01-04T00:00:00+00:00",
            ],
        )
        since = datetime(2024, 1, 2, tzinfo=timezone.utc)
        until = datetime(2024, 1, 3, tzinfo=timezone.utc)
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            result = read_audit_log(since=since, until=until)
        assert "2024-01-01" not in result
        assert "2024-01-02" in result
        assert "2024-01-03" in result
        assert "2024-01-04" not in result

    def test_empty_range_returns_no_entries_message(self, tmp_path):
        from scrapingbee_cli.audit import read_audit_log

        log_path = tmp_path / "audit.log"
        self._write_entries(log_path, ["2024-01-01T10:00:00+00:00"])
        since = datetime(2024, 6, 1, tzinfo=timezone.utc)
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            result = read_audit_log(since=since)
        assert "No entries found" in result

    def test_n_param_ignored_when_since_set(self, tmp_path):
        from scrapingbee_cli.audit import read_audit_log

        log_path = tmp_path / "audit.log"
        self._write_entries(
            log_path,
            [
                "2024-01-01T10:00:00+00:00",
                "2024-01-02T10:00:00+00:00",
                "2024-01-03T10:00:00+00:00",
            ],
        )
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        # n=1 should be ignored because since is set — all 3 entries returned
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            result = read_audit_log(n=1, since=since)
        assert "2024-01-01" in result
        assert "2024-01-02" in result
        assert "2024-01-03" in result


# =============================================================================
# 3. _validate_schedule_name()
# =============================================================================


class TestValidateScheduleName:
    """Tests for schedule._validate_schedule_name()."""

    def test_valid_alphanumeric(self):
        from scrapingbee_cli.commands.schedule import _validate_schedule_name

        _validate_schedule_name("prices")  # should not raise

    def test_valid_with_hyphens(self):
        from scrapingbee_cli.commands.schedule import _validate_schedule_name

        _validate_schedule_name("price-tracker")

    def test_valid_with_underscores(self):
        from scrapingbee_cli.commands.schedule import _validate_schedule_name

        _validate_schedule_name("price_tracker_daily")

    def test_valid_starts_with_digit(self):
        from scrapingbee_cli.commands.schedule import _validate_schedule_name

        _validate_schedule_name("1daily")

    def test_empty_name_rejected(self):
        from scrapingbee_cli.commands.schedule import _validate_schedule_name

        with pytest.raises((click.BadParameter, SystemExit)):
            _validate_schedule_name("")

    def test_starts_with_hyphen_rejected(self):
        from scrapingbee_cli.commands.schedule import _validate_schedule_name

        with pytest.raises((click.BadParameter, SystemExit)):
            _validate_schedule_name("-bad")

    def test_spaces_rejected(self):
        from scrapingbee_cli.commands.schedule import _validate_schedule_name

        with pytest.raises((click.BadParameter, SystemExit)):
            _validate_schedule_name("my name")

    def test_special_chars_rejected(self):
        from scrapingbee_cli.commands.schedule import _validate_schedule_name

        with pytest.raises((click.BadParameter, SystemExit)):
            _validate_schedule_name("bad@name")

    def test_too_long_rejected(self):
        from scrapingbee_cli.commands.schedule import _validate_schedule_name

        with pytest.raises((click.BadParameter, SystemExit)):
            _validate_schedule_name("a" * 61)

    def test_exactly_60_chars_accepted(self):
        from scrapingbee_cli.commands.schedule import _validate_schedule_name

        _validate_schedule_name("a" * 60)


# =============================================================================
# 4. _duration_to_cron() — rounding warning for seconds
# =============================================================================


class TestDurationToCronRounding:
    """Tests for schedule._duration_to_cron() seconds rounding."""

    def test_90s_rounds_to_1m_with_warning(self, capsys):
        from scrapingbee_cli.commands.schedule import _duration_to_cron

        result = _duration_to_cron("90s")
        assert result == "*/1 * * * *"
        err = capsys.readouterr().err
        assert "Rounding" in err or "warning" in err.lower() or "90s" in err

    def test_120s_rounds_to_2m_no_warning(self, capsys):
        from scrapingbee_cli.commands.schedule import _duration_to_cron

        result = _duration_to_cron("120s")
        assert result == "*/2 * * * *"
        err = capsys.readouterr().err
        assert "Rounding" not in err

    def test_180s_equals_3m(self):
        from scrapingbee_cli.commands.schedule import _duration_to_cron

        assert _duration_to_cron("180s") == "*/3 * * * *"


# =============================================================================
# 5. _save_batch_meta() / find_incomplete_batches()
# =============================================================================


class TestBatchMeta:
    """Tests for batch metadata saving and discovery."""

    def test_save_batch_meta_creates_file(self, tmp_path):
        from scrapingbee_cli.batch import _save_batch_meta

        out_dir = str(tmp_path / "batch_test")
        (tmp_path / "batch_test").mkdir()
        _save_batch_meta(out_dir, total=10, succeeded=5, failed=2)
        meta_path = tmp_path / "batch_test" / ".batch_meta.json"
        assert meta_path.is_file()

    def test_save_batch_meta_content(self, tmp_path):
        from scrapingbee_cli.batch import _save_batch_meta

        out_dir = str(tmp_path / "batch_test")
        (tmp_path / "batch_test").mkdir()
        _save_batch_meta(out_dir, total=10, succeeded=5, failed=2)
        meta = json.loads((tmp_path / "batch_test" / ".batch_meta.json").read_text())
        assert meta["total"] == 10
        assert meta["succeeded"] == 5
        assert meta["failed"] == 2
        assert "created_at" in meta
        assert "command" in meta

    def test_save_batch_meta_preserves_created_at_on_update(self, tmp_path):
        from scrapingbee_cli.batch import _save_batch_meta

        out_dir = str(tmp_path / "batch_test")
        (tmp_path / "batch_test").mkdir()
        _save_batch_meta(out_dir, total=10, succeeded=3, failed=1)
        first_meta = json.loads((tmp_path / "batch_test" / ".batch_meta.json").read_text())
        first_created = first_meta["created_at"]

        _save_batch_meta(out_dir, total=10, succeeded=8, failed=1)
        second_meta = json.loads((tmp_path / "batch_test" / ".batch_meta.json").read_text())
        assert second_meta["created_at"] == first_created

    def test_find_incomplete_batches_finds_incomplete(self, tmp_path):
        from scrapingbee_cli.batch import find_incomplete_batches

        d = tmp_path / "batch_001"
        d.mkdir()
        meta = {
            "command": "scrapingbee scrape --input-file urls.txt",
            "total": 10,
            "succeeded": 5,
            "failed": 1,
            "created_at": "2024-01-01T10:00:00+00:00",
        }
        (d / ".batch_meta.json").write_text(json.dumps(meta))
        results = find_incomplete_batches(str(tmp_path))
        assert len(results) == 1
        assert results[0]["total"] == 10
        assert results[0]["succeeded"] == 5

    def test_find_incomplete_batches_skips_complete(self, tmp_path):
        from scrapingbee_cli.batch import find_incomplete_batches

        d = tmp_path / "batch_002"
        d.mkdir()
        meta = {
            "command": "scrapingbee scrape --input-file urls.txt",
            "total": 5,
            "succeeded": 5,
            "failed": 0,
            "created_at": "2024-01-01T10:00:00+00:00",
        }
        (d / ".batch_meta.json").write_text(json.dumps(meta))
        results = find_incomplete_batches(str(tmp_path))
        assert results == []

    def test_find_incomplete_batches_finds_crawl_dirs(self, tmp_path):
        from scrapingbee_cli.batch import find_incomplete_batches

        d = tmp_path / "crawl_001"
        d.mkdir()
        meta = {
            "command": "scrapingbee crawl https://example.com",
            "total": 20,
            "succeeded": 10,
            "failed": 0,
            "created_at": "2024-01-01T10:00:00+00:00",
        }
        (d / ".batch_meta.json").write_text(json.dumps(meta))
        results = find_incomplete_batches(str(tmp_path))
        assert len(results) == 1
        assert results[0]["dir"].endswith("crawl_001")

    def test_find_incomplete_batches_empty_dir(self, tmp_path):
        from scrapingbee_cli.batch import find_incomplete_batches

        results = find_incomplete_batches(str(tmp_path))
        assert results == []

    def test_find_incomplete_batches_sorted_by_created_at(self, tmp_path):
        from scrapingbee_cli.batch import find_incomplete_batches

        for i, ts in enumerate(
            ["2024-01-01T10:00:00+00:00", "2024-01-03T10:00:00+00:00", "2024-01-02T10:00:00+00:00"]
        ):
            d = tmp_path / f"batch_00{i}"
            d.mkdir()
            meta = {
                "command": "cmd",
                "total": 5,
                "succeeded": 1,
                "failed": 0,
                "created_at": ts,
            }
            (d / ".batch_meta.json").write_text(json.dumps(meta))
        results = find_incomplete_batches(str(tmp_path))
        # Most recent first
        assert results[0]["created_at"] == "2024-01-03T10:00:00+00:00"
        assert results[2]["created_at"] == "2024-01-01T10:00:00+00:00"


# =============================================================================
# 6. _handle_resume()
# =============================================================================


class TestHandleResume:
    """Tests for cli._handle_resume()."""

    def test_returns_false_when_no_resume_flag(self, monkeypatch):
        from scrapingbee_cli.cli import _handle_resume

        monkeypatch.setattr(sys, "argv", ["scrapingbee", "scrape", "https://example.com"])
        assert _handle_resume() is False

    def test_returns_false_when_resume_with_other_args(self, monkeypatch):
        from scrapingbee_cli.cli import _handle_resume

        monkeypatch.setattr(
            sys, "argv", ["scrapingbee", "scrape", "--resume", "--output-dir", "dir"]
        )
        assert _handle_resume() is False

    def test_returns_true_when_bare_resume(self, monkeypatch, capsys):
        from scrapingbee_cli.cli import _handle_resume

        monkeypatch.setattr(sys, "argv", ["scrapingbee", "--resume"])
        with patch(
            "scrapingbee_cli.batch.find_incomplete_batches",
            return_value=[],
        ):
            result = _handle_resume()
        assert result is True

    def test_prints_incomplete_batches(self, monkeypatch, capsys, tmp_path):
        from scrapingbee_cli.cli import _handle_resume

        monkeypatch.setattr(sys, "argv", ["scrapingbee", "--resume"])
        batch_dir = str(tmp_path / "batch_001")
        batches = [
            {
                "dir": batch_dir,
                "command": "scrapingbee scrape --input-file urls.txt",
                "total": 10,
                "succeeded": 5,
                "failed": 1,
                "created_at": "2024-01-01T10:00:00+00:00",
            }
        ]
        with patch("scrapingbee_cli.batch.find_incomplete_batches", return_value=batches):
            result = _handle_resume()
        assert result is True
        err = capsys.readouterr().err
        # Should show count and the suggested resume command
        assert "1 incomplete" in err or "batch_001" in err
        # Suggested command must include --resume and --output-dir
        assert "--resume" in err
        assert "--output-dir" in err

    def test_prints_no_batches_message_when_empty(self, monkeypatch, capsys):
        from scrapingbee_cli.cli import _handle_resume

        monkeypatch.setattr(sys, "argv", ["scrapingbee", "--resume"])
        with patch("scrapingbee_cli.batch.find_incomplete_batches", return_value=[]):
            _handle_resume()
        err = capsys.readouterr().err
        assert "No incomplete" in err


# =============================================================================
# 7. _handle_scraping_config()
# =============================================================================


class TestHandleScrapingConfig:
    """Tests for cli._handle_scraping_config()."""

    def test_no_op_when_no_scraping_config(self, monkeypatch):
        from scrapingbee_cli.cli import _handle_scraping_config

        original = ["scrapingbee", "scrape", "https://example.com"]
        monkeypatch.setattr(sys, "argv", original[:])
        _handle_scraping_config()
        assert sys.argv == original

    def test_injects_scrape_when_no_subcommand(self, monkeypatch):
        from scrapingbee_cli.cli import _handle_scraping_config

        monkeypatch.setattr(sys, "argv", ["scrapingbee", "--scraping-config", "My-Config"])
        _handle_scraping_config()
        assert sys.argv[1] == "scrape"
        assert "--scraping-config" in sys.argv
        assert "My-Config" in sys.argv

    def test_no_inject_when_scrape_already_present(self, monkeypatch):
        from scrapingbee_cli.cli import _handle_scraping_config

        original = ["scrapingbee", "scrape", "--scraping-config", "My-Config"]
        monkeypatch.setattr(sys, "argv", original[:])
        _handle_scraping_config()
        assert sys.argv == original

    def test_no_inject_when_other_command_present(self, monkeypatch):
        from scrapingbee_cli.cli import _handle_scraping_config

        original = ["scrapingbee", "google", "--scraping-config", "My-Config"]
        monkeypatch.setattr(sys, "argv", original[:])
        _handle_scraping_config()
        assert sys.argv == original

    def test_injects_before_url(self, monkeypatch):
        from scrapingbee_cli.cli import _handle_scraping_config

        monkeypatch.setattr(
            sys, "argv", ["scrapingbee", "--scraping-config", "Blog", "https://example.com"]
        )
        _handle_scraping_config()
        assert sys.argv[1] == "scrape"
        assert "https://example.com" in sys.argv

    def test_preserves_all_flags(self, monkeypatch):
        from scrapingbee_cli.cli import _handle_scraping_config

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "scrapingbee",
                "--scraping-config",
                "My-Config",
                "--render-js",
                "false",
                "--verbose",
            ],
        )
        _handle_scraping_config()
        assert sys.argv[1] == "scrape"
        assert "--render-js" in sys.argv
        assert "--verbose" in sys.argv


# =============================================================================
# 8. confirm_overwrite()
# =============================================================================


class TestConfirmOverwrite:
    """Tests for cli_utils.confirm_overwrite()."""

    def test_no_op_when_path_is_none(self):
        from scrapingbee_cli.cli_utils import confirm_overwrite

        confirm_overwrite(None, overwrite=False)  # should not raise

    def test_no_op_when_file_does_not_exist(self, tmp_path):
        from scrapingbee_cli.cli_utils import confirm_overwrite

        path = str(tmp_path / "new.txt")
        confirm_overwrite(path, overwrite=False)  # should not raise

    def test_no_op_when_overwrite_true(self, tmp_path):
        from scrapingbee_cli.cli_utils import confirm_overwrite

        path = tmp_path / "exists.txt"
        path.write_text("data")
        confirm_overwrite(str(path), overwrite=True)  # should not raise

    def test_exits_when_user_declines(self, tmp_path, monkeypatch):
        from scrapingbee_cli.cli_utils import confirm_overwrite

        path = tmp_path / "exists.txt"
        path.write_text("data")
        monkeypatch.setattr("click.confirm", lambda *a, **kw: False)
        with pytest.raises(SystemExit):
            confirm_overwrite(str(path), overwrite=False)

    def test_continues_when_user_confirms(self, tmp_path, monkeypatch):
        from scrapingbee_cli.cli_utils import confirm_overwrite

        path = tmp_path / "exists.txt"
        path.write_text("data")
        monkeypatch.setattr("click.confirm", lambda *a, **kw: True)
        confirm_overwrite(str(path), overwrite=False)  # should not raise


# =============================================================================
# 9. store_common_options() — batch-only flags without --input-file
# =============================================================================


class TestStoreCommonOptionsBatchValidation:
    """Tests for batch-only flag validation in store_common_options()."""

    def _make_obj(self, **overrides) -> dict:
        """Build a minimal valid single-URL options dict."""
        defaults = {
            "output_file": None,
            "output_dir": "",
            "verbose": False,
            "input_file": None,
            "input_column": None,
            "output_format": None,
            "concurrency": 0,
            "no_progress": False,
            "post_process": None,
            "on_complete": None,
            "deduplicate": False,
            "sample": 0,
            "resume": False,
            "update_csv": False,
            "retries": 3,
            "backoff": 2.0,
            "extract_field": None,
            "fields": None,
            "overwrite": False,
        }
        defaults.update(overrides)
        return defaults

    def test_update_csv_without_input_file_exits(self, capsys):
        from scrapingbee_cli.cli_utils import store_common_options

        obj = {}
        with pytest.raises(SystemExit):
            store_common_options(obj, **self._make_obj(update_csv=True))
        err = capsys.readouterr().err
        assert "--update-csv" in err
        # Should suggest a corrected command with --input-file
        assert "--input-file" in err

    def test_output_dir_without_input_file_exits(self, capsys):
        from scrapingbee_cli.cli_utils import store_common_options

        obj = {}
        with pytest.raises(SystemExit):
            store_common_options(obj, **self._make_obj(output_dir="/tmp/out"))
        err = capsys.readouterr().err
        assert "--output-dir" in err
        assert "--input-file" in err

    def test_concurrency_without_input_file_exits(self, capsys):
        from scrapingbee_cli.cli_utils import store_common_options

        obj = {}
        with pytest.raises(SystemExit):
            store_common_options(obj, **self._make_obj(concurrency=5))
        err = capsys.readouterr().err
        assert "--concurrency" in err
        assert "--input-file" in err

    def test_output_format_without_input_file_exits(self, capsys):
        from scrapingbee_cli.cli_utils import store_common_options

        obj = {}
        with pytest.raises(SystemExit):
            store_common_options(obj, **self._make_obj(output_format="csv"))
        err = capsys.readouterr().err
        assert "--output-format" in err
        assert "--input-file" in err

    def test_deduplicate_without_input_file_exits(self, capsys):
        from scrapingbee_cli.cli_utils import store_common_options

        obj = {}
        with pytest.raises(SystemExit):
            store_common_options(obj, **self._make_obj(deduplicate=True))
        err = capsys.readouterr().err
        assert "--deduplicate" in err
        assert "--input-file" in err

    def test_resume_without_input_file_shows_discovery_hint(self, capsys):
        from scrapingbee_cli.cli_utils import store_common_options

        obj = {}
        with pytest.raises(SystemExit):
            store_common_options(obj, **self._make_obj(resume=True))
        err = capsys.readouterr().err
        assert "--resume" in err
        # Should show bare scrapingbee --resume hint for discovery
        assert "scrapingbee --resume" in err

    def test_negative_concurrency_exits(self):
        from scrapingbee_cli.cli_utils import store_common_options

        obj = {}
        with pytest.raises(SystemExit):
            store_common_options(obj, **self._make_obj(concurrency=-1, input_file="urls.txt"))

    def test_output_file_and_output_dir_mutual_exclusion(self):
        from scrapingbee_cli.cli_utils import store_common_options

        obj = {}
        with pytest.raises(SystemExit):
            store_common_options(
                obj,
                **self._make_obj(
                    output_file="/tmp/out.json",
                    output_dir="/tmp/out/",
                    input_file="urls.txt",
                ),
            )

    def test_valid_single_url_options_pass(self):
        from scrapingbee_cli.cli_utils import store_common_options

        obj = {}
        store_common_options(obj, **self._make_obj())  # should not raise

    def test_valid_batch_options_pass(self):
        from scrapingbee_cli.cli_utils import store_common_options

        obj = {}
        store_common_options(
            obj,
            **self._make_obj(
                input_file="urls.txt",
                output_dir="/tmp/out",
                concurrency=5,
                deduplicate=True,
            ),
        )  # should not raise


# =============================================================================
# 10. --output-format no longer accepts "files"
# =============================================================================


class TestOutputFormatChoices:
    """Verify that --output-format only accepts csv and ndjson."""

    def test_output_format_choices_shown_in_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["scrape", "--help"])
        assert code == 0
        # The choice list must show [csv|ndjson], not [csv|ndjson|files]
        assert "[csv|ndjson]" in out

    def test_csv_accepted_in_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["scrape", "--help"])
        assert code == 0
        assert "csv" in out

    def test_ndjson_accepted_in_help(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["scrape", "--help"])
        assert code == 0
        assert "ndjson" in out

    def test_files_not_in_choice_bracket(self):
        from tests.conftest import cli_run

        code, out, _ = cli_run(["scrape", "--help"])
        assert code == 0
        # "files" must not be listed as a valid choice value in the bracket
        assert "[csv|ndjson|files]" not in out
        assert "[files|" not in out
