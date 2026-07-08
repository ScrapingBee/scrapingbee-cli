"""Unit tests for the scrollback drag-to-select-and-copy backend (interactive.py).

Covers the pure, module-level helpers — selection highlight (_styled_with_selection),
text slicing (_slice_selection), and the ScrollbackBuffer provenance/snapshot that
maps a mouse drag to a stable (line, char). The interactive mouse_handler + clipboard
path is validated separately via a PTY harness (not a CI dep).
"""

from __future__ import annotations

from scrapingbee_cli.interactive import (
    ScrollbackBuffer,
    _slice_selection,
    _styled_with_selection,
)


class TestStyledWithSelection:
    def test_single_line_span(self):
        assert _styled_with_selection([("", "hello world")], 0, 0, (0, 2), (0, 7)) == [
            ("", "he"),
            ("reverse", "llo w"),
            ("", "orld"),
        ]

    def test_out_of_range_returns_unchanged(self):
        row = [("", "x")]
        assert _styled_with_selection(row, 5, 0, (0, 0), (2, 9)) == row

    def test_multiline_first_line_to_eol(self):
        assert _styled_with_selection([("", "abcdefgh")], 0, 0, (0, 3), (2, 5)) == [
            ("", "abc"),
            ("reverse", "defgh"),
        ]

    def test_multiline_interior_whole_row(self):
        assert _styled_with_selection([("", "xyz")], 1, 0, (0, 3), (2, 5)) == [("reverse", "xyz")]

    def test_multiline_last_line_from_start(self):
        assert _styled_with_selection([("", "mnopqrst")], 2, 0, (0, 3), (2, 5)) == [
            ("reverse", "mnopq"),
            ("", "rst"),
        ]

    def test_wrapped_continuation_row(self):
        # 2nd visual row of a logical line, starting at char 10.
        assert _styled_with_selection([("", "klmnopqrst")], 0, 10, (0, 12), (0, 18)) == [
            ("", "kl"),
            ("reverse", "mnopqr"),
            ("", "st"),
        ]

    def test_spans_styled_fragments(self):
        assert _styled_with_selection(
            [("fg:red", "ERR "), ("", "details")], 0, 0, (0, 2), (0, 6)
        ) == [
            ("fg:red", "ER"),
            ("fg:red reverse", "R "),
            ("reverse", "de"),
            ("", "tails"),
        ]

    def test_empty_row(self):
        assert _styled_with_selection([], 0, 0, (0, 0), (0, 5)) == []


class TestSliceSelection:
    def test_single_line(self):
        assert _slice_selection(["hello world"], (0, 2), (0, 7)) == "llo w"

    def test_multi_line_joins_with_newline(self):
        texts = ["first line", "middle", "last line"]
        assert _slice_selection(texts, (0, 6), (2, 4)) == "line\nmiddle\nlast"

    def test_two_lines_no_middle(self):
        assert _slice_selection(["abcdef", "ghijkl"], (0, 3), (1, 2)) == "def\ngh"

    def test_empty_texts(self):
        assert _slice_selection([], (0, 0), (0, 5)) == ""

    def test_wrapped_single_line_is_contiguous(self):
        # A single logical line selected across what would be wrapped visual rows
        # extracts as ONE contiguous substring (no inserted newline).
        line = "a" * 50
        result = _slice_selection([line], (0, 5), (0, 45))
        assert result == "a" * 40
        assert "\n" not in result


class TestProvenanceAndSnapshot:
    def _buf(self):
        sb = ScrollbackBuffer()
        sb.lines = [
            [("", "short")],
            [("", "a" * 25)],  # wraps at width 10 -> 3 rows
            [("class:err", "ERR "), ("", "details here")],  # styled, wraps -> 2 rows
        ]
        sb.scroll_offset = 0
        return sb

    def test_meta_reconstructs_each_row(self):
        sb = self._buf()
        rows, meta = sb.get_visible_visual_with_meta(10, 10)
        assert len(rows) == len(meta)
        for (li, sc), row in zip(meta, rows):
            rt = "".join(t for _, t in row)
            full = "".join(t for _, t in sb.lines[li])
            assert full[sc : sc + len(rt)] == rt

    def test_meta_values(self):
        sb = self._buf()
        _, meta = sb.get_visible_visual_with_meta(10, 10)
        assert meta == [(0, 0), (1, 0), (1, 10), (1, 20), (2, 0), (2, 10)]

    def test_get_visible_visual_delegates(self):
        sb = self._buf()
        rows, _ = sb.get_visible_visual_with_meta(10, 10)
        assert sb.get_visible_visual(10, 10) == rows

    def test_snapshot_line_texts_and_clamp(self):
        sb = self._buf()
        assert sb.snapshot_line_texts(0, 2) == ["short", "a" * 25, "ERR details here"]
        assert sb.snapshot_line_texts(-5, 99) == ["short", "a" * 25, "ERR details here"]

    def test_width_le_1_meta_is_sentinel(self):
        sb = self._buf()
        _, meta = sb.get_visible_visual_with_meta(10, 1)
        assert meta and all(m == (-1, 0) for m in meta)


class TestCopyToClipboard:
    """The OS clipboard write used by drag-copy (and :view). Mocks subprocess so
    it's deterministic and never touches the real clipboard."""

    def test_darwin_uses_pbcopy(self, monkeypatch):
        import shutil
        import subprocess
        import sys

        from scrapingbee_cli.interactive import _copy_to_clipboard

        calls = []
        monkeypatch.setattr(sys, "platform", "darwin")
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
        monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)))
        assert _copy_to_clipboard("hello") is True
        assert calls[0][0] == ["pbcopy"]
        assert calls[0][1].get("input") == b"hello"

    def test_empty_text_returns_false(self):
        from scrapingbee_cli.interactive import _copy_to_clipboard

        assert _copy_to_clipboard("") is False

    def test_no_tool_returns_false(self, monkeypatch):
        import shutil

        from scrapingbee_cli.interactive import _copy_to_clipboard

        monkeypatch.setattr(shutil, "which", lambda name: None)
        assert _copy_to_clipboard("hello") is False
