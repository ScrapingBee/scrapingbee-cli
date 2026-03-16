"""Unit tests for export command helpers."""

from __future__ import annotations

import csv
import io
import json

from click.testing import CliRunner

from scrapingbee_cli.cli import cli
from scrapingbee_cli.commands.export import _find_main_list, _flatten_value


class TestFindMainList:
    """Tests for _find_main_list()."""

    def test_returns_none_for_flat_object(self):
        assert _find_main_list({"title": "Widget", "price": 29.99}) is None

    def test_returns_none_for_empty_dict(self):
        assert _find_main_list({}) is None

    def test_returns_list_of_dicts(self):
        data = {"organic_results": [{"url": "a"}, {"url": "b"}], "meta_data": {}}
        result = _find_main_list(data)
        assert result == [{"url": "a"}, {"url": "b"}]

    def test_returns_largest_list_when_multiple(self):
        data = {
            "short": [{"x": 1}],
            "long": [{"a": 1}, {"a": 2}, {"a": 3}],
        }
        result = _find_main_list(data)
        assert result is not None and len(result) == 3

    def test_ignores_list_of_non_dicts(self):
        data = {"tags": ["python", "scraping"], "results": [{"url": "a"}]}
        result = _find_main_list(data)
        assert result == [{"url": "a"}]

    def test_returns_none_when_all_lists_are_scalars(self):
        data = {"tags": ["a", "b", "c"]}
        assert _find_main_list(data) is None


class TestFlattenValue:
    """Tests for _flatten_value()."""

    def test_string_unchanged(self):
        assert _flatten_value("hello") == "hello"

    def test_int_to_str(self):
        assert _flatten_value(42) == "42"

    def test_float_to_str(self):
        assert _flatten_value(3.14) == "3.14"

    def test_none_to_empty_string(self):
        assert _flatten_value(None) == ""

    def test_dict_serialised_as_json(self):
        result = _flatten_value({"a": 1})
        assert json.loads(result) == {"a": 1}

    def test_list_serialised_as_json(self):
        result = _flatten_value([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]


class TestExportCsvCommand:
    """Integration tests for export --format csv via CLI runner."""

    def test_flat_objects_produce_csv_rows(self, tmp_path):
        (tmp_path / "1.json").write_text(
            json.dumps({"asin": "B001", "title": "Widget", "price": 9.99})
        )
        (tmp_path / "2.json").write_text(
            json.dumps({"asin": "B002", "title": "Gadget", "price": 19.99})
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["export", "--input-dir", str(tmp_path), "--format", "csv"],
        )
        assert result.exit_code == 0, result.output
        reader = csv.DictReader(io.StringIO(result.output))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["asin"] == "B001"
        assert rows[1]["asin"] == "B002"

    def test_list_results_are_expanded_to_rows(self, tmp_path):
        data = {
            "organic_results": [
                {"url": "https://a.com", "title": "A"},
                {"url": "https://b.com", "title": "B"},
            ],
            "meta_data": {"total": 2},
        }
        (tmp_path / "1.json").write_text(json.dumps(data))
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["export", "--input-dir", str(tmp_path), "--format", "csv"],
        )
        assert result.exit_code == 0, result.output
        reader = csv.DictReader(io.StringIO(result.output))
        rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["url"] == "https://a.com"
        assert rows[1]["title"] == "B"

    def test_non_json_files_skipped(self, tmp_path):
        (tmp_path / "1.json").write_text(json.dumps({"x": 1}))
        (tmp_path / "2.html").write_text("<html/>")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["export", "--input-dir", str(tmp_path), "--format", "csv"],
        )
        assert result.exit_code == 0
        reader = csv.DictReader(io.StringIO(result.output))
        rows = list(reader)
        assert len(rows) == 1

    def test_url_column_added_from_manifest(self, tmp_path):
        (tmp_path / "1.json").write_text(json.dumps({"title": "Page A"}))
        manifest = {"https://example.com/a": "1.json"}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["export", "--input-dir", str(tmp_path), "--format", "csv"],
        )
        assert result.exit_code == 0
        reader = csv.DictReader(io.StringIO(result.output))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["_url"] == "https://example.com/a"

    def test_new_manifest_format_with_dict_values(self, tmp_path):
        """New manifest format {url: {file, fetched_at, http_status}} is handled correctly."""
        (tmp_path / "1.json").write_text(json.dumps({"title": "Page A"}))
        manifest = {
            "https://example.com/a": {
                "file": "1.json",
                "fetched_at": "2025-01-01T00:00:00+00:00",
                "http_status": 200,
            }
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["export", "--input-dir", str(tmp_path), "--format", "csv"],
        )
        assert result.exit_code == 0
        reader = csv.DictReader(io.StringIO(result.output))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["_url"] == "https://example.com/a"

    def test_exits_nonzero_when_no_json_files(self, tmp_path):
        (tmp_path / "1.html").write_text("<html/>")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["export", "--input-dir", str(tmp_path), "--format", "csv"],
        )
        assert result.exit_code != 0
