"""Unit tests for audit module — execution logging."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from scrapingbee_cli.audit import (
    MAX_LINES,
    _parse_timestamp,
    _rotate_if_needed,
    log_exec,
    read_audit_log,
)


class TestAuditLog:
    """Tests for audit logging."""

    def test_log_exec_creates_file(self, tmp_path):
        log_path = tmp_path / "audit.log"
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            log_exec("post-process", "jq '.title'", input_source="urls.txt")
        assert log_path.is_file()
        content = log_path.read_text()
        assert "post-process" in content
        assert "jq '.title'" in content
        assert "urls.txt" in content

    def test_log_exec_appends(self, tmp_path):
        log_path = tmp_path / "audit.log"
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            log_exec("post-process", "jq '.title'")
            log_exec("on-complete", "echo done")
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_log_exec_with_output_dir(self, tmp_path):
        log_path = tmp_path / "audit.log"
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            log_exec("on-complete", "echo done", output_dir="/tmp/batch_123")
        content = log_path.read_text()
        assert "/tmp/batch_123" in content

    def test_read_audit_log_empty(self, tmp_path):
        log_path = tmp_path / "audit.log"
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            result = read_audit_log()
        assert "No audit log found" in result

    def test_read_audit_log_content_returns_last_n(self, tmp_path):
        """read_audit_log(n=2) must return the LAST 2 lines, not just any 2."""
        log_path = tmp_path / "audit.log"
        log_path.write_text("line1\nline2\nline3\n")
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            result = read_audit_log(n=2)
        assert "line1" not in result
        assert "line2" in result
        assert "line3" in result

    def test_read_audit_log_n_larger_than_file(self, tmp_path):
        """When n > number of lines, all lines are returned."""
        log_path = tmp_path / "audit.log"
        log_path.write_text("only\n")
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            result = read_audit_log(n=100)
        assert "only" in result

    def test_log_exec_creates_parent_dirs(self, tmp_path):
        log_path = tmp_path / "subdir" / "audit.log"
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            log_exec("schedule", "scrape https://example.com")
        assert log_path.is_file()


class TestParseTimestamp:
    """Tests for _parse_timestamp()."""

    def test_valid_line(self):
        ts_str = "2024-01-15T10:30:00+00:00"
        line = f"{ts_str} | post-process | jq '.title' | | "
        result = _parse_timestamp(line)
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_empty_string(self):
        assert _parse_timestamp("") is None

    def test_no_pipe_separator(self):
        # No ' | ' → parts[0] is the whole line, not a valid ISO timestamp
        result = _parse_timestamp("not a timestamp line")
        assert result is None

    def test_malformed_timestamp(self):
        result = _parse_timestamp("not-a-date | feature | cmd | | ")
        assert result is None

    def test_timezone_aware_timestamp(self):
        ts_str = datetime.now(timezone.utc).isoformat()
        line = f"{ts_str} | schedule | echo hi | | "
        result = _parse_timestamp(line)
        assert result is not None
        assert result.tzinfo is not None


class TestRotateIfNeeded:
    """Tests for _rotate_if_needed()."""

    def test_no_rotation_below_limit(self, tmp_path):
        log_path = tmp_path / "audit.log"
        lines = "".join(f"line{i}\n" for i in range(100))
        log_path.write_text(lines)
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            _rotate_if_needed()
        assert log_path.read_text() == lines  # unchanged

    def test_rotation_above_limit(self, tmp_path):
        log_path = tmp_path / "audit.log"
        total = MAX_LINES + 500
        lines = [f"line{i}\n" for i in range(total)]
        log_path.write_text("".join(lines))
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            _rotate_if_needed()
        after = log_path.read_text().splitlines()
        assert len(after) == MAX_LINES
        # The last MAX_LINES lines should be kept (not the first ones)
        assert after[0] == f"line{total - MAX_LINES}"
        assert after[-1] == f"line{total - 1}"

    def test_oserror_is_silenced(self, tmp_path):
        """_rotate_if_needed must not raise even if AUDIT_LOG_PATH doesn't exist."""
        missing = tmp_path / "nonexistent.log"
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", missing):
            _rotate_if_needed()  # should not raise
