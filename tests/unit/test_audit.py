"""Unit tests for audit module — execution logging."""

from __future__ import annotations

from unittest.mock import patch

from scrapingbee_cli.audit import log_exec, read_audit_log


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

    def test_read_audit_log_content(self, tmp_path):
        log_path = tmp_path / "audit.log"
        log_path.write_text("line1\nline2\nline3\n")
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            result = read_audit_log(n=2)
        assert "line2" in result
        assert "line3" in result

    def test_log_exec_creates_parent_dirs(self, tmp_path):
        log_path = tmp_path / "subdir" / "audit.log"
        with patch("scrapingbee_cli.audit.AUDIT_LOG_PATH", log_path):
            log_exec("schedule", "scrape https://example.com")
        assert log_path.is_file()
