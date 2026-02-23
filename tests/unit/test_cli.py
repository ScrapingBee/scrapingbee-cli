"""Unit tests for CLI helpers: validation, constants."""

from __future__ import annotations

import sys

import pytest

from scrapingbee_cli.cli import _reject_equals_syntax
from scrapingbee_cli.cli_utils import (
    WAIT_BROWSER_HELP,
    _validate_json_option,
    _validate_page,
    _validate_price_range,
    _validate_range,
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
