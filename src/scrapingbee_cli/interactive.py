"""Interactive REPL — Ink-style hybrid (real scrollback + persistent bottom prompt).

The pattern is the same one Claude CLI uses (see Ink's `<Static>` component):
- Past command output is printed to real terminal stdout → goes into terminal
  scrollback. Mouse-wheel scrolling and selection work normally, resize is
  handled by the terminal, and quitting leaves a clean record behind.
- The input area + status toolbar live at the very bottom of the terminal as
  a small persistent `Application(full_screen=False)`. prompt_toolkit's
  `patch_stdout` redraws this strip whenever something prints, so the prompt
  is always visible no matter how many lines of output flow above.

That means: typing a command, hitting enter, watching output stream in
*above* the prompt — exactly the Claude experience — without losing real
terminal scrollback or selection.

Implementation notes:
- ONE persistent Application for the whole REPL session (not one-per-prompt).
- Enter key binding runs the click command synchronously inside the handler.
  Output from the command goes through patched stdout/stderr and lands above
  the prompt.
- Interactive commands (tutorial, auth) take over the terminal via
  `run_in_terminal` so click.prompt() works.
- On launch we pad with newlines so the prompt anchors at the bottom from
  the first frame.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, Iterable

from rich.text import Text

from .theme import BEE_DIM, BEE_RED, BEE_YELLOW, err_console

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Refined palette
# ---------------------------------------------------------------------------

_AMBER     = "#E5A800"   # frame border / soft accent
_GREEN     = "#22C55E"   # success
_DIM2      = "#555555"   # darker chrome (toolbar labels, hint)
_BG_CHIP   = "#1a1400"   # chip background (settings)
_URL_CYAN  = "#7DD3FC"   # URLs in input lexer

_STYLE_DICT = {
    # Top/bottom horizontal rules around the input
    "rule":          _AMBER,
    # Prompt mark inside the input area
    "promptmark":    f"{BEE_YELLOW} bold",
    # Lexer (input syntax highlighting). Specific categories have explicit
    # colours; unstyled tokens fall through to the application's default
    # style (key `""`), which is set per-session in `_style_dict_for`.
    "lexer.cmd":     f"{BEE_YELLOW} bold",
    "lexer.flag":    _AMBER,
    "lexer.url":     _URL_CYAN,
    "lexer.string":  _GREEN,
    # Bottom toolbar
    "toolbar":         f"{BEE_DIM}",
    "toolbar.label":   _DIM2,
    "toolbar.value":   f"{BEE_YELLOW} bold",
    "toolbar.ok":      f"{_GREEN} bold",
    "toolbar.fail":    f"{BEE_RED} bold",
    "toolbar.hint":    _DIM2,
    "toolbar.chip":    f"bg:{_BG_CHIP} {BEE_YELLOW}",
    "toolbar.gauge":   f"{BEE_YELLOW}",
    # Completion menu
    "completion-menu":                          f"bg:{_BG_CHIP}",
    "completion-menu.completion":               f"bg:{_BG_CHIP} {BEE_YELLOW}",
    "completion-menu.completion.current":       f"bg:{BEE_YELLOW} #000000 bold",
    "completion-menu.meta.completion":          f"bg:{_BG_CHIP} #886600",
    "completion-menu.meta.completion.current":  f"bg:{BEE_YELLOW} #000000",
    "auto-suggestion": "fg:#777777 italic",
}


def _style_dict_for(keep_bg: bool) -> dict[str, str]:
    """Return the prompt_toolkit Style dict for the REPL session.

    When `keep_bg` is False (default), set the empty class `""` (the default
    style) to a dark-theme foreground. Combined with the OSC 11/10 escapes
    that switch the *terminal* fg/bg to dark, this gives a single coherent
    "dark theme" applied at both layers — explicit class colours stay as-is,
    and any unstyled text falls back to a readable light-grey.

    With `keep_bg=True`, the default class is empty and the terminal's own
    fg/bg are untouched — the user's system theme drives all defaults.
    """
    style = dict(_STYLE_DICT)
    if not keep_bg:
        style[""] = "fg:#EAEAEA"
    return style


# ---------------------------------------------------------------------------
# Binary-write adapter
# ---------------------------------------------------------------------------


class _BinaryAdapter:
    """Adapter that exposes a ``.write(bytes)`` interface on top of a text
    stream. Bolted onto prompt_toolkit's StdoutProxy at runtime so callers
    that write bytes (``sys.stdout.buffer.write(b"...")``) work transparently
    while we're inside a ``patch_stdout`` context.
    """

    def __init__(self, text_stream) -> None:
        self._stream = text_stream

    def write(self, data) -> int:
        if data is None or len(data) == 0:
            return 0
        if isinstance(data, (bytes, bytearray, memoryview)):
            text = bytes(data).decode("utf-8", errors="replace")
        else:
            text = str(data)
        self._stream.write(text)
        return len(data)

    def flush(self) -> None:
        try:
            self._stream.flush()
        except Exception:
            pass

    @property
    def closed(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Virtual scrollback (for full_screen=True mode)
# ---------------------------------------------------------------------------


try:
    from prompt_toolkit.auto_suggest import AutoSuggest as _PTKAutoSuggest
except Exception:  # pragma: no cover — prompt_toolkit should always be present
    _PTKAutoSuggest = object  # type: ignore[assignment,misc]


class BeeAutoSuggest(_PTKAutoSuggest):
    """Context-aware ghost-text autosuggest for the REPL prompt.

    On each keystroke prompt_toolkit calls ``get_suggestion`` with the
    current buffer; we look at the partial token under the cursor and
    return a single greyed-out continuation (or ``None`` for silence).

    Sources used, in order:
    - **First word** → match against known command names.
    - **A flag** (token starts with ``-``) → match flags registered for
      the current command.
    - **Token after a choice/bool flag** → match valid choice values.
    - **Free text otherwise** → match the start of a previous history
      line that begins with the same prefix.

    Candidates are ranked by recency in command history (most-recently-
    used wins → behaves like frequency for active users). If the
    partial token doesn't prefix any known candidate, we return
    ``None`` — typos get no suggestion, even if they happen to be
    substrings of past commands.

    Accepting a suggestion (Right arrow / End, or Ctrl+F for the first
    word in emacs-style bindings) is handled by prompt_toolkit's
    built-in ``auto_suggest_apply`` key processors — no extra wiring
    needed here.
    """

    def __init__(
        self,
        command_names,
        command_flags,
        bool_flags,
        choice_flags,
        history,
        is_disabled=None,
    ) -> None:
        self._command_names = sorted(command_names)
        self._command_flags = command_flags
        self._bool_flags = bool_flags
        self._choice_flags = choice_flags
        self._history = history
        # Optional callable; when it returns True we skip suggestions
        # entirely. Used during first-run API key entry — we don't want
        # history-based suggestions (which might leak a previously-typed
        # secret) or command-name suggestions (irrelevant in that mode).
        self._is_disabled = is_disabled
        # Cache history lines (newest-first). Refreshed lazily when the
        # underlying length changes — cheap O(1) check, avoids re-listing
        # the history on every keystroke.
        self._cached_lines: list[str] = []
        self._cached_len = -1

    def _refresh_history(self) -> None:
        if self._history is None:
            return
        try:
            lines = list(self._history.get_strings())
        except Exception:
            return
        if len(lines) != self._cached_len:
            self._cached_len = len(lines)
            self._cached_lines = lines

    def _rank_by_recency(self, candidates: list[str]) -> list[str]:
        """Sort candidates by first occurrence in (newest-first) history.
        Unseen candidates fall to the end, then ordered alphabetically."""
        self._refresh_history()
        recency: dict[str, int] = {}
        for i, line in enumerate(self._cached_lines):
            for tok in line.split():
                if tok in candidates and tok not in recency:
                    recency[tok] = i
        return sorted(candidates, key=lambda c: (recency.get(c, 10**9), c))

    def get_suggestion(self, buffer, document):
        from prompt_toolkit.auto_suggest import Suggestion

        try:
            if self._is_disabled is not None and self._is_disabled():
                return None
            text = document.text_before_cursor
            if not text:
                return None
            words = text.split()
            if not words:
                return None
            first = words[0]

            # Gate against typos at the command level. We only allow a
            # suggestion if the first token is either a recognised command
            # or a valid PREFIX of one — otherwise we'd risk surfacing
            # history junk for a clear typo (the user's explicit ask).
            first_is_known = first in self._command_flags
            first_is_prefix = (
                not first_is_known
                and any(c.startswith(first) for c in self._command_names)
            )
            if not (first_is_known or first_is_prefix):
                return None

            # 1) Prefer a full history-line continuation. Catches the most
            #    natural case: "scrape https://exam" → finish the URL
            #    and any flags the user last paired with it.
            self._refresh_history()
            for line in self._cached_lines:
                if line.startswith(text) and line != text:
                    return Suggestion(line[len(text):])

            # 2) No matching history line. Suggest from the structured
            #    options (command names, flags, choice values).
            has_trailing_space = text.endswith(" ")
            last = words[-1]
            on_first = (len(words) == 1) and not has_trailing_space

            if on_first:
                cands = [
                    c for c in self._command_names
                    if c.startswith(last) and c != last
                ]
                if not cands:
                    return None
                best = self._rank_by_recency(cands)[0]
                return Suggestion(best[len(last):])

            # Multi-word — need a recognised command to suggest structure.
            if not first_is_known:
                return None
            if has_trailing_space:
                return None  # no partial token to complete

            if last.startswith("-"):
                flags = self._command_flags.get(first, [])
                cands = [f for f in flags if f.startswith(last) and f != last]
                if not cands:
                    return None
                best = self._rank_by_recency(cands)[0]
                return Suggestion(best[len(last):])

            if len(words) >= 2:
                prev = words[-2]
                if prev in self._choice_flags:
                    cands = [
                        v for v in self._choice_flags[prev]
                        if v.startswith(last) and v != last
                    ]
                    if not cands:
                        return None
                    best = self._rank_by_recency(cands)[0]
                    return Suggestion(best[len(last):])
                if prev in self._bool_flags:
                    for v in ("true", "false"):
                        if v.startswith(last.lower()) and v != last.lower():
                            return Suggestion(v[len(last):])
                    return None
            return None
        except Exception:
            return None


def _make_capped_history(filename: str, max_entries: int = 10_000):
    """Construct a ``FileHistory`` with the on-disk file pre-trimmed to
    keep at most ``max_entries`` most-recent entries.

    prompt_toolkit's stock ``FileHistory`` appends forever — every
    command you ever type lives in ``.history`` until you delete the
    file manually. For long-running CLI users that file grows unbounded
    and slows down the REPL's initial history-load. We keep the last
    10000 entries on disk (a few months of normal use, file stays
    under ~2 MB).

    Trim runs once at construction. During the session, ``FileHistory``
    appends as normal — no per-write overhead. The file may briefly
    exceed the cap mid-session; the excess is dropped on next startup.
    """
    import datetime as _dt
    import os as _os

    from prompt_toolkit.history import FileHistory

    if _os.path.exists(filename):
        try:
            tmp_history = FileHistory(filename)
            strings = list(tmp_history.load_history_strings())  # newest-first
            if len(strings) > max_entries:
                keep_newest_first = strings[:max_entries]
                keep_oldest_first = list(reversed(keep_newest_first))
                tmp = filename + ".tmp"
                now = _dt.datetime.now()
                try:
                    with open(tmp, "wb") as f:
                        for s in keep_oldest_first:
                            f.write(f"\n# {now}\n".encode("utf-8"))
                            for line in s.split("\n"):
                                f.write(f"+{line}\n".encode("utf-8"))
                    _os.replace(tmp, filename)
                except Exception:
                    try:
                        _os.unlink(tmp)
                    except Exception:
                        pass
        except Exception:
            pass
    return FileHistory(filename)


def _split_fragments_to_width(
    line: list[tuple[str, str]], width: int
) -> list[list[tuple[str, str]]]:
    """Split a logical line's (style, text) fragments into a list of
    visual rows, each at most ``width`` characters wide.

    Empty input → one empty row (so blank lines still occupy one row).
    Preserves styles across the split — if a styled fragment crosses a
    row boundary, the boundary lands inside the fragment with the same
    style on both sides.
    """
    if width <= 0:
        return [list(line)]
    if not line:
        return [[]]
    out: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_len = 0
    for sty, text in line:
        if not text:
            continue
        i = 0
        n = len(text)
        while i < n:
            room = width - current_len
            if room <= 0:
                out.append(current)
                current = []
                current_len = 0
                room = width
            chunk = text[i : i + room]
            current.append((sty, chunk))
            current_len += len(chunk)
            i += len(chunk)
    if current or not out:
        out.append(current)
    return out


class ScrollbackBuffer:
    """In-memory line buffer that backs the scrollable output Window.

    When the REPL runs in full_screen mode we own the alt buffer, so command
    output can't flow into real terminal scrollback. Instead, every line of
    output gets parsed for ANSI escapes and stored as a list of
    ``(style, text)`` fragments. The render callback for the output Window
    asks the buffer for a slice based on the current scroll offset.

    Thread-safe append: command output is written from worker threads and
    the renderer reads from the loop thread; a lock keeps the list
    consistent without trying to be clever.
    """

    MAX_LINES = 10_000  # ring-buffer cap so a runaway scrape can't OOM us

    def __init__(self) -> None:
        self.lines: list[list[tuple[str, str]]] = []
        # How many lines we're scrolled up from the bottom. 0 = at bottom
        # (auto-follow); positive = locked at some scrolled-up position.
        self.scroll_offset = 0
        self._lock = threading.Lock()

    def append_fragments(self, fragments: list[tuple[str, str]]) -> None:
        """Append one rendered line (already styled) as the final entry."""
        with self._lock:
            self.lines.append(list(fragments))
            if len(self.lines) > self.MAX_LINES:
                # Drop the oldest 10% — cheaper than dropping one at a time
                # if a scrape produces tens of thousands of lines.
                drop = self.MAX_LINES // 10
                del self.lines[:drop]

    def replace_last_line(self, fragments: list[tuple[str, str]]) -> None:
        """Overwrite the most recent line. Used for in-place progress
        updates via the standard terminal ``\\r`` idiom — write
        ``\\r<content>\\n`` and the previous line gets replaced rather
        than another row appended.
        """
        with self._lock:
            if self.lines:
                self.lines[-1] = list(fragments)
            else:
                self.lines.append(list(fragments))

    def replace_last_n_lines(
        self, n: int, lines: list[list[tuple[str, str]]]
    ) -> None:
        """Replace the most recent ``n`` lines with the given ``lines``.
        If fewer than ``n`` lines exist, the remainder is appended.
        Used for multi-line in-place progress widgets (e.g. the
        3-row honeycomb progress bar).
        """
        with self._lock:
            if len(self.lines) >= n and n > 0:
                # Replace tail in place — same count, no shift.
                self.lines[len(self.lines) - n:] = [list(f) for f in lines]
            else:
                # Not enough prior lines to replace; append.
                for f in lines:
                    self.lines.append(list(f))

    def append_ansi_text(self, text: str) -> None:
        """Parse ANSI codes in ``text`` and append the resulting line(s).

        Handles partial-line writes: callers may write text without a
        trailing newline (e.g. an in-progress progress bar). We split on
        ``\\n``; the final post-split chunk goes into a pending buffer
        that gets prepended to the next write.

        Carriage-return (``\\r``) handling: anything before the last
        ``\\r`` on a line is discarded (standard terminal "go to start
        of line" semantics), AND the resulting line replaces the
        previous line in scrollback instead of appending. This lets
        callers do in-place progress updates by writing
        ``\\r<progress>\\n`` repeatedly.
        """
        from prompt_toolkit.formatted_text import ANSI, to_formatted_text

        # Combine with anything pending from a previous partial write.
        with self._lock:
            pending = self._pending if hasattr(self, "_pending") else ""
            combined = pending + text
            chunks = combined.split("\n")
            self._pending = chunks[-1]  # may be empty if text ended with \n
            complete = chunks[:-1]

        for raw in complete:
            had_cr = "\r" in raw
            if had_cr:
                # Everything before the last \r is overwritten — keep
                # only what comes after it.
                raw = raw.rsplit("\r", 1)[1]
            try:
                fragments = list(to_formatted_text(ANSI(raw)))
            except Exception:
                fragments = [("", raw)]
            if had_cr:
                self.replace_last_line(fragments)
            else:
                self.append_fragments(fragments)

    def flush_pending(self) -> None:
        """Commit any pending partial line as its own row."""
        with self._lock:
            pending = getattr(self, "_pending", "")
            self._pending = ""
        if pending:
            from prompt_toolkit.formatted_text import ANSI, to_formatted_text

            try:
                fragments = list(to_formatted_text(ANSI(pending)))
            except Exception:
                fragments = [("", pending)]
            self.append_fragments(fragments)

    def get_visible_window(
        self, height: int
    ) -> list[list[tuple[str, str]]]:
        """Backwards-compatible: visible slice in *logical* lines."""
        with self._lock:
            total = len(self.lines)
            if total == 0:
                return []
            max_offset = max(0, total - height)
            if self.scroll_offset > max_offset:
                self.scroll_offset = max_offset
            end = total - self.scroll_offset
            start = max(0, end - height)
            return [list(line) for line in self.lines[start:end]]

    def get_visible_visual(
        self, height: int, width: int
    ) -> list[list[tuple[str, str]]]:
        """Return visible content in *visual rows* (post-wrap).

        Long single lines that wrap to multiple terminal rows are
        pre-split here at ``width`` characters so each entry in the
        returned list is exactly one terminal row. ``scroll_offset``
        is in visual rows too, so one ``scroll_up(1)`` step moves the
        view by exactly one visible row — even through a 5000-char
        JSON blob that wraps to dozens of rows. This is what makes
        wheel/trackpad scrolling feel consistent regardless of line
        length.
        """
        if width <= 1:
            return self.get_visible_window(height)
        with self._lock:
            # Walk from the bottom up, accumulating visual rows until we
            # have enough to fill the window at the requested scroll offset.
            # Stops early on large buffers — we don't need to wrap content
            # the user can't see this frame.
            need = max(0, self.scroll_offset) + max(1, height)
            collected: list[list[tuple[str, str]]] = []  # newest-first
            for line in reversed(self.lines):
                for visual_row in reversed(_split_fragments_to_width(line, width)):
                    collected.append(visual_row)
                if len(collected) >= need:
                    break
            collected.reverse()  # back to oldest-first
            total = len(collected)
            max_offset = max(0, total - height)
            if self.scroll_offset > max_offset:
                self.scroll_offset = max_offset
            end = total - self.scroll_offset
            start = max(0, end - height)
            return collected[start:end]

    def scroll_up(self, n: int = 1) -> None:
        with self._lock:
            # Soft cap — get_visible_window will further clamp based on
            # the actual rendered height, but capping here at total-1
            # avoids letting offset grow unboundedly between renders.
            self.scroll_offset = min(
                max(0, len(self.lines) - 1), self.scroll_offset + n
            )

    def scroll_down(self, n: int = 1) -> None:
        with self._lock:
            self.scroll_offset = max(0, self.scroll_offset - n)

    def scroll_to_top(self) -> None:
        with self._lock:
            self.scroll_offset = max(0, len(self.lines) - 1)

    def scroll_to_bottom(self) -> None:
        with self._lock:
            self.scroll_offset = 0

    @property
    def at_bottom(self) -> bool:
        with self._lock:
            return self.scroll_offset == 0

    def insert_line(self, index: int, fragments: list[tuple[str, str]]) -> None:
        """Insert a single line at ``index`` (clamped to current length).

        Used to retroactively splice the command-echo line in front of a
        finished command's output, so the user sees ``❯ <cmd>`` above the
        output rows the command produced — without the echo being visible
        during execution itself (where the shimmer is the live indicator).
        """
        with self._lock:
            i = max(0, min(index, len(self.lines)))
            self.lines.insert(i, list(fragments))

    def current_length(self) -> int:
        with self._lock:
            return len(self.lines)


class ScrollbackWriter:
    """File-like writer that pipes everything into a ScrollbackBuffer.

    Installed as ``sys.stdout`` / ``sys.stderr`` while the REPL runs.
    Click commands, rich consoles, plain ``print`` calls — all flow
    through here, get parsed for ANSI, and end up as rows in the
    scrollback. The renderer then displays them.

    Thread-safe: command output comes from worker threads while the
    prompt_toolkit loop renders on the main thread.
    """

    encoding = "utf-8"

    def __init__(self, scrollback: ScrollbackBuffer, on_write: Any = None) -> None:
        self._sb = scrollback
        self._on_write = on_write  # callable to nudge the app to re-render

    def write(self, s: Any) -> int:
        if not s:
            return 0
        if isinstance(s, (bytes, bytearray, memoryview)):
            s = bytes(s).decode("utf-8", errors="replace")
        elif not isinstance(s, str):
            s = str(s)
        self._sb.append_ansi_text(s)
        if self._on_write is not None:
            try:
                self._on_write()
            except Exception:
                pass
        return len(s)

    def flush(self) -> None:
        # No-op — we don't buffer beyond ScrollbackBuffer's pending partial.
        pass

    def isatty(self) -> bool:
        return True  # let click / rich treat us as a tty so colors stay on

    @property
    def closed(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Shimmer (prompt_toolkit-formatted)
# ---------------------------------------------------------------------------

# Used for the live "running command" line above the input. A bright white
# "peak" cell sweeps across the line, flanked by warm-yellow cells, with the
# rest in brand yellow — reads as a glow running along the command text.
_SHIMMER_PEAK_PT  = "#FFFFFF"
_SHIMMER_FLANK_PT = "#FFE780"


def _shimmer_pt(text: str, position: int, base_color: str) -> list[tuple[str, str]]:
    """Return prompt_toolkit formatted-text tuples with a shimmer at `position`.

    Character at `position` is peak white, neighbours at ±1 are warm yellow,
    everything else uses ``base_color``. Combined with a position that
    advances each tick this reads as a wave of light along the text.
    """
    out: list[tuple[str, str]] = []
    for i, ch in enumerate(text):
        distance = abs(i - position)
        if distance == 0:
            style = f"bold fg:{_SHIMMER_PEAK_PT}"
        elif distance == 1:
            style = f"bold fg:{_SHIMMER_FLANK_PT}"
        else:
            style = f"bold fg:{base_color}"
        out.append((style, ch))
    return out


# ---------------------------------------------------------------------------
# Click tree introspection
# ---------------------------------------------------------------------------


def _walk_click_tree(cli_group: Any) -> tuple[
    dict[str, str], dict[str, list[str]], set[str], dict[str, list[str]]
]:
    """Return (command_help, command_flags, bool_flags, choice_flags)."""
    import click

    command_help: dict[str, str] = {}
    command_flags: dict[str, list[str]] = {}
    bool_flags: set[str] = set()
    choice_flags: dict[str, list[str]] = {}

    for name, cmd in cli_group.commands.items():
        first_line = ""
        for source in (cmd.short_help, cmd.help):
            if source:
                first_line = source.strip().splitlines()[0]
                break
        command_help[name] = first_line

        flags: list[str] = []
        for param in cmd.params:
            if not isinstance(param, click.Option):
                continue
            for opt in param.opts:
                if opt.startswith("--"):
                    flags.append(opt)
                    if param.is_flag:
                        bool_flags.add(opt)
                    if isinstance(param.type, click.Choice):
                        choice_flags[opt] = list(param.type.choices)
        command_flags[name] = sorted(set(flags))

    return command_help, command_flags, bool_flags, choice_flags


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


class SessionState:
    """REPL-wide mutable state surfaced in the bottom toolbar."""

    USAGE_REFRESH_INTERVAL = 30.0  # seconds between background usage API calls

    def __init__(self) -> None:
        self.last_command: str | None = None
        self.last_status: str | None = None     # "ok" | "fail"
        self.last_duration: float | None = None
        # Live account state — surfaced in the toolbar. None ⇒ unknown / N/A.
        self.credits: int | None = None              # available = max - used
        self.credits_total: int | None = None        # max_api_credit
        self.used_credits: int | None = None         # used_api_credit (latest)
        self.used_credits_at_start: int | None = None  # snapshotted after first ok refresh
        self.max_concurrency: int | None = None
        self.current_concurrency: int | None = None
        # Whether the API key was present when the REPL started (or after auth).
        # Drives "N/A" rendering in the toolbar while False.
        self.api_key_set: bool = False
        # Short hash of the live API key. Used to detect logout/relogin with
        # the same key — when the key is unchanged we keep the session
        # counter going instead of resetting it to 0.
        self.api_key_hash: str | None = None
        self.last_usage_refresh_mono: float | None = None  # time.monotonic() of last ok refresh
        self.settings: dict[str, str] = {}
        # In-flight execution state — drives the live "running" line above
        # the input (with shimmer sweep) and the toolbar's running indicator.
        self.is_running: bool = False
        self.running_command: str | None = None
        self.running_command_text: str | None = None  # full line as typed
        self.run_start: float | None = None
        self.tick: int = 0   # frame counter for the shimmer position
        # Mouse mode toggle: "scroll" = mouse_support on (wheel scrolls the
        # virtual buffer, drag-select needs a per-terminal modifier);
        # "select" = mouse_support off (native drag-select works everywhere
        # without a modifier, but wheel scroll stops). Alt+S toggles.
        self.mouse_mode: str = "scroll"

    def apply_settings_to_args(self, args: list[str]) -> list[str]:
        if not self.settings:
            return args
        present = {a for a in args if a.startswith("--")}
        out = list(args)
        for key, value in self.settings.items():
            flag = f"--{key}"
            if flag in present:
                continue
            out.extend([flag, value])
        return out

    def refresh_credits_from_cache(self) -> None:
        """Populate live fields from the on-disk usage cache.

        Cache file shape (written by ``batch.write_usage_file_cache``):
            ``{"ts": <float>, "key_hash": <str>, "data": <parsed_dict>}``
        where ``data`` is the output of ``client.parse_usage``:
            ``{"credits": int, "max_api_credit": int, "max_concurrency": int}``

        Only the ``data`` sub-dict has the values we care about; reading any
        other key would just see metadata. Earlier versions iterated
        ``data.values()`` and relied on the fact that the inner dict happened
        to have matching keys — works by accident, brittle if the cache
        format ever grows.
        """
        try:
            import json
            from pathlib import Path

            cache = Path.home() / ".config" / "scrapingbee-cli" / "usage_cache.json"
            if not cache.exists():
                return
            entry = json.loads(cache.read_text(encoding="utf-8"))
            if not isinstance(entry, dict):
                return
            data = entry.get("data")
            if not isinstance(data, dict):
                return
            if isinstance(data.get("credits"), int):
                self.credits = data["credits"]
            if isinstance(data.get("max_api_credit"), int):
                self.credits_total = data["max_api_credit"]
            if isinstance(data.get("max_concurrency"), int):
                self.max_concurrency = data["max_concurrency"]
        except Exception:
            return

    def update_from_usage_response(self, raw: dict, key_hash: str | None = None) -> None:
        """Apply a parsed JSON usage-API response to the live state.

        Snapshots ``used_credits_at_start`` on first successful update so the
        toolbar's "used this session" remains accurate even if the REPL was
        launched before the first refresh succeeded. If ``key_hash`` is
        provided and differs from the previous one, the session start
        snapshot is reset — so logging out and back in with a *different*
        key starts the counter at 0, but re-auth with the *same* key keeps
        counting from where it left off.
        """
        if key_hash is not None and key_hash != self.api_key_hash:
            # Key changed (initial set OR switched to a different key) —
            # forget the previous session's baseline so the next snapshot
            # below establishes a fresh one.
            self.used_credits_at_start = None
            self.api_key_hash = key_hash
        max_credit = raw.get("max_api_credit")
        used_credit = raw.get("used_api_credit")
        if isinstance(max_credit, (int, float)):
            self.credits_total = int(max_credit)
        if isinstance(used_credit, (int, float)):
            self.used_credits = int(used_credit)
            if self.used_credits_at_start is None:
                self.used_credits_at_start = int(used_credit)
        if self.credits_total is not None and self.used_credits is not None:
            self.credits = max(0, self.credits_total - self.used_credits)
        mc = raw.get("max_concurrency")
        if isinstance(mc, (int, float)):
            self.max_concurrency = int(mc)
        cc = raw.get("current_concurrency")
        if isinstance(cc, (int, float)):
            self.current_concurrency = int(cc)
        self.last_usage_refresh_mono = time.monotonic()

    @property
    def session_credits_used(self) -> int | None:
        if self.used_credits is None or self.used_credits_at_start is None:
            return None
        return max(0, self.used_credits - self.used_credits_at_start)

    @property
    def seconds_until_next_refresh(self) -> int | None:
        if self.last_usage_refresh_mono is None:
            return None
        remaining = (
            self.last_usage_refresh_mono + self.USAGE_REFRESH_INTERVAL - time.monotonic()
        )
        return max(0, int(remaining + 0.999))  # ceil so the countdown never shows -1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_credits(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _credit_gauge(used_pct: int) -> str:
    """Tiny block-bar showing credit usage (0..100)."""
    blocks = "▁▂▃▄▅▆▇█"
    n = min(7, max(0, int(used_pct * 8 / 100)))
    return blocks[n]


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _suggest(typed: str, candidates: Iterable[str], threshold: int = 2) -> str | None:
    best: tuple[int, str] | None = None
    for c in candidates:
        d = _levenshtein(typed.lower(), c.lower())
        if d <= threshold and (best is None or d < best[0]):
            best = (d, c)
    return best[1] if best else None


# ---------------------------------------------------------------------------
# Lexer (syntax highlighting in the input buffer)
# ---------------------------------------------------------------------------


def _make_lexer():
    from prompt_toolkit.lexers import Lexer

    class CmdLexer(Lexer):
        def lex_document(self, document):
            def get_line(lineno: int):
                if lineno >= len(document.lines):
                    return []
                line = document.lines[lineno]
                tokens: list[tuple[str, str]] = []
                first_word_seen = False
                for piece in re.split(r"(\s+)", line):
                    if not piece:
                        continue
                    if piece.isspace():
                        tokens.append(("", piece))
                        continue
                    if not first_word_seen:
                        # First word coloured even if it's a slash-command
                        tokens.append(("class:lexer.cmd", piece))
                        first_word_seen = True
                    elif piece.startswith("--"):
                        tokens.append(("class:lexer.flag", piece))
                    elif piece.startswith(("http://", "https://")):
                        tokens.append(("class:lexer.url", piece))
                    elif (
                        len(piece) > 1
                        and piece[0] in ("'", '"')
                        and piece[-1] == piece[0]
                    ):
                        tokens.append(("class:lexer.string", piece))
                    else:
                        # Inherit the app default style (`""`), which is set
                        # to light-grey foreground when --keep-bg is off and
                        # left empty (terminal default) when --keep-bg is on.
                        tokens.append(("", piece))
                return tokens

            return get_line

    return CmdLexer()


# ---------------------------------------------------------------------------
# Bottom toolbar
# ---------------------------------------------------------------------------


def _make_toolbar(state: SessionState):
    """Return a callable producing toolbar segments.

    The toolbar adapts to terminal width:
    - Wide:   credits gauge · last cmd · all chips · hint
    - Medium: credits gauge · last cmd · chip count · hint
    - Narrow: credits · last cmd · chip count

    While a command is in flight (``state.is_running``) the toolbar shows a
    plain "running · <elapsed>s" label; the visual animation lives on the
    shimmering command line just above the input.
    """

    def render() -> list[tuple[str, str]]:
        # Width: prefer prompt_toolkit's live SIGWINCH-tracked size when an
        # app is actually running (so the toolbar stays in lockstep with
        # what prompt_toolkit's own renderer is using). Outside a run loop,
        # ``get_app()`` returns a dummy whose output reports a constant 80
        # — useless — so we fall through to shutil in that case.
        width = 0
        try:
            from prompt_toolkit.application import get_app as _get_app

            _app = _get_app()
            # get_app() returns a dummy outside a real run loop; its output
            # reports a constant 80 — useless. Only trust the live app.
            if getattr(_app, "is_running", False):
                width = _app.output.get_size().columns
        except Exception:
            pass
        if not width:
            import shutil
            width = shutil.get_terminal_size((80, 24)).columns
        segs: list[tuple[str, str]] = [("class:toolbar", "  ")]

        # --- In-flight: running label + elapsed + rotating usage stats ───
        # Layout: ``running · 12.3s`` pinned on the left, ``Ctrl+C to stop``
        # pinned on the right, and a rotating stat (Used Session / Concurrency
        # / Next Update) in the middle. The rotation cycles every 5s so the
        # user can monitor credits being consumed during a long scrape
        # without leaving the command.
        if state.is_running:
            segs.append(("class:toolbar.label", "running"))
            if state.run_start is not None:
                elapsed = time.monotonic() - state.run_start
                segs.append(("class:toolbar", f"  ·  {elapsed:.1f}s"))

            # Build rotating stat chunks (subset of the idle toolbar's info).
            stat_chunks: list[list[tuple[str, str]]] = []
            if state.api_key_set and state.credits is not None:
                stat_chunks.append([
                    ("class:toolbar.label", "Available "),
                    ("class:toolbar.value", _format_credits(state.credits)),
                ])
            scu = state.session_credits_used if state.api_key_set else None
            stat_chunks.append([
                ("class:toolbar.label", "Used (Session) "),
                ("class:toolbar.value", _format_credits(scu) if scu is not None else "N/A"),
            ])
            if state.api_key_set and state.max_concurrency is not None:
                cur = state.current_concurrency if state.current_concurrency is not None else 0
                stat_chunks.append([
                    ("class:toolbar.label", "Concurrency "),
                    ("class:toolbar.value", f"{cur}/{state.max_concurrency}"),
                ])
            if state.api_key_set:
                nxt = state.seconds_until_next_refresh
                if nxt is not None:
                    stat_chunks.append([
                        ("class:toolbar.label", "Next Update "),
                        ("class:toolbar.value", f"{nxt}s"),
                    ])

            stop_hint = "Ctrl+C to stop"
            stop_hint_len = len(stop_hint)
            so_far = sum(len(t) for _, t in segs)
            # Reserve room for: "  ·  <stat>  ..." + right-aligned stop hint
            available = max(0, width - so_far - stop_hint_len - 6)

            # Pick the stat chunk for this rotation tick — only if it fits.
            if stat_chunks and available > 8:
                idx = int(time.monotonic() / 5) % len(stat_chunks)
                chunk = stat_chunks[idx]
                chunk_len = sum(len(t) for _, t in chunk)
                if chunk_len + 5 <= available:
                    segs.append(("class:toolbar", "  ·  "))
                    segs.extend(chunk)

            # Setting chips still show below if any room remains
            if state.settings:
                so_far = sum(len(t) for _, t in segs)
                budget = max(0, width - so_far - stop_hint_len - 4)
                shown = 0
                for k, v in state.settings.items():
                    chip = f" {k}={v} "
                    if budget < len(chip) + 2 and shown > 0:
                        break
                    segs.append(("class:toolbar", "  "))
                    segs.append(("class:toolbar.chip", chip))
                    budget -= len(chip) + 2
                    shown += 1
                remaining = len(state.settings) - shown
                if remaining > 0:
                    segs.append(("class:toolbar", "  "))
                    segs.append(("class:toolbar.hint", f"+{remaining} more"))

            # Right-align "Ctrl+C to stop" hint
            used = sum(len(t) for _, t in segs)
            if width - used > stop_hint_len + 4:
                segs.append(("class:toolbar", " " * max(2, width - used - stop_hint_len - 2)))
                segs.append(("class:toolbar.hint", stop_hint))
            return segs

        # --- Idle: build all fields, then either render statically or paginate
        # When the joined toolbar text exceeds the terminal width we'd
        # otherwise emit a line longer than the screen — the terminal soft-
        # wraps it into a phantom 2nd row that prompt_toolkit doesn't know
        # about, leaving a ghost-toolbar in scrollback on resize. To keep
        # everything visible without scrolling jitter, we greedy-pack fields
        # into "pages" that each fit, then cycle pages every PAGE_SECONDS.
        # Each page is rendered statically — no per-frame motion — so it
        # reads cleanly and doesn't waste redraws.
        fields: list[list[tuple[str, str]]] = []

        # Available Credits
        avail: list[tuple[str, str]] = [("class:toolbar.label", "Available Credits ")]
        if state.api_key_set and state.credits is not None:
            avail.append(("class:toolbar.value", _format_credits(state.credits)))
            if state.credits_total:
                used_pct = max(
                    0,
                    min(100, 100 - int(state.credits / state.credits_total * 100)),
                )
                avail.append(("class:toolbar.hint", f"  ({used_pct}% used)"))
        else:
            avail.append(("class:toolbar.value", "N/A"))
        fields.append(avail)

        # Used (Current Session)
        used_chunk: list[tuple[str, str]] = [
            ("class:toolbar.label", "Used (Current Session) ")
        ]
        scu = state.session_credits_used if state.api_key_set else None
        used_chunk.append(
            ("class:toolbar.value", _format_credits(scu) if scu is not None else "N/A")
        )
        fields.append(used_chunk)

        # Concurrency
        conc_chunk: list[tuple[str, str]] = [("class:toolbar.label", "Concurrency ")]
        if state.api_key_set and state.max_concurrency is not None:
            cur = state.current_concurrency if state.current_concurrency is not None else 0
            conc_chunk.append(("class:toolbar.value", f"{cur}/{state.max_concurrency}"))
        else:
            conc_chunk.append(("class:toolbar.value", "N/A"))
        fields.append(conc_chunk)

        # Next Update countdown (only after first successful refresh)
        if state.api_key_set:
            nxt = state.seconds_until_next_refresh
            if nxt is not None:
                fields.append([
                    ("class:toolbar.label", "Next Update "),
                    ("class:toolbar.value", f"{nxt}s"),
                ])

        # (Removed "last cmd" indicator — the typed command and its
        # ✓/✗ footer are already visible in the scrollback echo, so a
        # toolbar copy doesn't add information and just consumes width.)

        # Session setting chips
        if state.settings:
            chip_segs: list[tuple[str, str]] = []
            for k, v in state.settings.items():
                if chip_segs:
                    chip_segs.append(("class:toolbar", " "))
                chip_segs.append(("class:toolbar.chip", f" {k}={v} "))
            fields.append(chip_segs)

        # Hint chunk — surfaces the active mouse mode and how to switch.
        # Replaces the older "tab · ↑↓ · :help · :q" cheat-sheet, since the
        # mode toggle is the one keybinding the user might actually need
        # to *change* during a session. The other shortcuts are in :help.
        if not state.api_key_set:
            hint_text = "type `auth` to set API key"
            hint_chunk: list[tuple[str, str]] = [("class:toolbar.hint", hint_text)]
        else:
            mode_label = (
                "Scroll mode" if state.mouse_mode == "scroll" else "Select mode"
            )
            hint_chunk = [
                ("class:toolbar.value", mode_label),
                ("class:toolbar.hint", "  ·  Shift+Tab to switch"),
            ]

        LEADING = "  "
        SEP = "  ·  "
        PAGE_SECONDS = 5  # how long each page is displayed before rotating

        def _seg_len(chunk: list[tuple[str, str]]) -> int:
            return sum(len(t) for _, t in chunk)

        # The mode hint ("Scroll mode · Tab to switch" / auth nudge) is the
        # one piece of toolbar content the user needs to see at all times —
        # it advertises the only globally-mutable runtime mode. Pin it on
        # every page by reserving its width up-front and pagination only
        # packs the *other* fields into the remaining space.
        hint_len = _seg_len(hint_chunk)
        budget = max(10, width - 2)
        # Reserve room for hint + separator on every page. If the hint alone
        # is wider than the budget, we'll still try to render it (final
        # hard-truncate at the bottom of this function will clip).
        field_budget = max(0, budget - hint_len - len(SEP))

        # Greedy-pack the non-hint fields into pages, each ≤ field_budget.
        pages: list[list[list[tuple[str, str]]]] = []
        cur: list[list[tuple[str, str]]] = []
        cur_len = len(LEADING)
        for chunk in fields:
            chunk_len = _seg_len(chunk)
            added = chunk_len + (len(SEP) if cur else 0)
            if cur and cur_len + added > field_budget:
                pages.append(cur)
                cur = [chunk]
                cur_len = len(LEADING) + chunk_len
            else:
                cur.append(chunk)
                cur_len += added
        if cur:
            pages.append(cur)
        # Even if there are no non-hint fields (extreme narrow), produce
        # one empty page so the hint still renders.
        if not pages:
            pages = [[]]

        # Rotate pages by wall-clock time. Single-page case is static.
        if len(pages) == 1:
            page_idx = 0
        else:
            page_idx = int(time.monotonic() / PAGE_SECONDS) % len(pages)
        page = pages[page_idx]

        # Compose the chosen page.
        segs: list[tuple[str, str]] = [("class:toolbar", LEADING)]
        for i, chunk in enumerate(page):
            if i > 0:
                segs.append(("class:toolbar", SEP))
            segs.extend(chunk)

        # Page indicator (e.g. "1/3") trailing — only when rotating.
        if len(pages) > 1:
            indicator = f"  ({page_idx + 1}/{len(pages)})"
            cur_total = sum(len(t) for _, t in segs)
            if cur_total + len(indicator) <= field_budget:
                segs.append(("class:toolbar.hint", indicator))

        # Hint always rendered on the right edge of every page.
        cur_total = sum(len(t) for _, t in segs)
        pad = max(2, width - cur_total - hint_len - 2)
        segs.append(("class:toolbar", " " * pad))
        segs.extend(hint_chunk)

        # Final safety: hard-truncate so we never emit a line wider than
        # the terminal (prevents the soft-wrap ghost-toolbar artifact).
        total = sum(len(t) for _, t in segs)
        if total > width - 1:
            cap = max(0, width - 1)
            kept: list[tuple[str, str]] = []
            used_len = 0
            for sty, text in segs:
                room = cap - used_len
                if room <= 0:
                    break
                if len(text) <= room:
                    kept.append((sty, text))
                    used_len += len(text)
                else:
                    kept.append((sty, text[: max(0, room - 1)] + "…"))
                    break
            segs = kept
        return segs

    return render


# ---------------------------------------------------------------------------
# Application (Frame around input + toolbar)
# ---------------------------------------------------------------------------


def _build_application(state: SessionState, completer: Any, history_path: str):
    from prompt_toolkit.application import Application
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.filters import has_completions
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.dimension import D
    from prompt_toolkit.styles import Style

    try:
        history = FileHistory(history_path)
    except Exception:
        history = None  # type: ignore[assignment]

    buffer = Buffer(
        history=history,
        completer=completer,
        complete_while_typing=False,
        auto_suggest=AutoSuggestFromHistory(),
        multiline=False,
    )

    # The input is a single Window with a per-line prefix (the chevron).
    # `dont_extend_height=True` makes the Window report its preferred height as
    # the content's line count — so the layout shrinks to fit, no greedy fill.
    def _line_prefix(line_no, _wrap_count):
        if line_no == 0:
            return [("class:promptmark", "❯ ")]
        return [("", "  ")]

    input_window = Window(
        content=BufferControl(buffer=buffer, lexer=_make_lexer()),
        get_line_prefix=_line_prefix,
        wrap_lines=True,
        height=D(min=1),
        dont_extend_height=True,
    )

    toolbar_window = Window(
        content=FormattedTextControl(_make_toolbar(state)),
        height=D.exact(1),
    )

    # No horizontal rules above/below the input. Earlier versions had `─`
    # rules for visual structure, but every resize redraws the layout at the
    # new width and leaves the old wider rule fragments behind in scrollback —
    # piles of yellow horizontal lines accumulate. Visual hierarchy still
    # holds via the yellow chevron prompt mark and the dim toolbar.
    layout = Layout(HSplit([input_window, toolbar_window]))

    kb = KeyBindings()

    @kb.add("enter")
    def _enter(event):
        text = buffer.text
        if text.strip():
            event.app.exit(result=text)

    @kb.add("c-c")
    def _ctrl_c(event):
        event.app.exit(result=None)

    @kb.add("c-d")
    def _ctrl_d(event):
        if not buffer.text:
            event.app.exit(result=None)

    # Tab opens / advances the completion menu. (Custom KeyBindings override
    # prompt_toolkit's default Tab handler, so we re-bind it explicitly.)
    @kb.add("tab", filter=~has_completions)
    def _tab_open(event):
        event.current_buffer.start_completion(select_first=False)

    @kb.add("tab", filter=has_completions)
    def _tab_next(event):
        event.current_buffer.complete_next()

    @kb.add("s-tab", filter=has_completions)
    def _shift_tab(event):
        event.current_buffer.complete_previous()

    @kb.add("escape", filter=has_completions, eager=True)
    def _escape_menu(event):
        event.current_buffer.cancel_completion()

    app = Application(
        layout=layout,
        key_bindings=kb,
        style=Style.from_dict(_STYLE_DICT),
        full_screen=False,
        mouse_support=False,
        # Erase the rendered prompt area on exit so rules + input + toolbar
        # don't pile up in scrollback as stale-width artifacts after every
        # submit (or after a terminal resize). The submitted command is
        # echoed manually by the main loop so the user can still see what
        # they typed.
        erase_when_done=True,
    )
    return app, buffer


# ---------------------------------------------------------------------------
# Banner / help / output frame
# ---------------------------------------------------------------------------


# ScrapingBee wordmark — approximation of the actual brand logo
# (https://www.scrapingbee.com/images/favico.svg): three honeycomb cells
# arranged in an L-shape (top, bottom-left, bottom-right) next to the
# "ScrapingBee" text rendered in the figlet ``smblock`` font.
# All rendered in brand yellow (terminal limits us to single-colour per
# Window; the real SVG has the bottom-left cell highlighted vs the other
# two). ~42 cols × 4 rows.
# "ScrapingBee" rendered in the figlet ``smblock`` font — 4 rows × 32 cols,
# roughly the same width as the "Web scraping from the terminal" tagline.
# Same block-letter style as the old 6-row logo, just compact.
_SCRAPINGBEE_LOGO = [
    "  ▞▀▖            ▗       ▛▀▖      ",
    "  ▚▄ ▞▀▖▙▀▖▝▀▖▛▀▖▄ ▛▀▖▞▀▌▙▄▘▞▀▖▞▀▖",
    "  ▖ ▌▌ ▖▌  ▞▀▌▙▄▘▐ ▌ ▌▚▄▌▌ ▌▛▀ ▛▀ ",
    "  ▝▀ ▝▀ ▘  ▝▀▘▌  ▀▘▘ ▘▗▄▘▀▀ ▝▀▘▝▀▘",
]
# Legacy 6-row logos kept around in case we want to swap back later or
# use them elsewhere (e.g. a one-shot welcome screen). The pinned REPL
# banner uses the compact form above.
_BEE_LOGO = [
    "  ██████╗ ███████╗███████╗",
    "  ██╔══██╗██╔════╝██╔════╝",
    "  ██████╔╝█████╗  █████╗  ",
    "  ██╔══██╗██╔══╝  ██╔══╝  ",
    "  ██████╔╝███████╗███████╗",
    "  ╚═════╝ ╚══════╝╚══════╝",
]


def _render_banner(version: str) -> str:
    """Render the startup banner to an ANSI-formatted string.

    Rendered into an in-memory StringIO via rich so the whole banner is
    assembled before any write to the terminal — avoids interleaving with
    other stdout writes (clear-screen, padding newlines) and avoids any
    timing-related re-ordering between rich's internal flushing and our
    direct sys.stdout.write calls.
    """
    from io import StringIO

    from rich.console import Console

    from .theme import SCRAPINGBEE_THEME

    buf = StringIO()
    c = Console(
        file=buf,
        theme=SCRAPINGBEE_THEME,
        highlight=False,
        force_terminal=True,
        width=200,  # don't wrap the wide ASCII logo
    )
    c.print()
    for line in _SCRAPINGBEE_LOGO:
        c.print(f"[bold {BEE_YELLOW}]{line}[/]")
    for line in _BEE_LOGO:
        c.print(f"[bold white]{line}[/]")
    c.print()
    # Version
    c.print(f"  [bold {BEE_YELLOW}]v{version}[/]")
    # Tagline
    c.print(f"  [{BEE_DIM}]Web scraping from the terminal[/]")
    c.print()
    # Hint
    hint = Text()
    hint.append("  Type ", style=BEE_DIM)
    hint.append(":help", style=f"bold {BEE_YELLOW}")
    hint.append(" for commands, ", style=BEE_DIM)
    hint.append(":q", style=f"bold {BEE_YELLOW}")
    hint.append(" to quit", style=BEE_DIM)
    c.print(hint)
    c.print()
    return buf.getvalue()


def _print_help(commands: dict[str, str]) -> None:
    """Print the REPL command list with a two-column layout.

    Long descriptions wrap with a hanging indent so continuation lines line
    up under the description column instead of flowing back to column 0.
    Column widths:
        4 (leading)  +  20 (cmd col)  +  2 (gap)  =  26-col indent for
    continuation lines. The description column gets the rest of the
    terminal width.
    """
    import shutil
    import textwrap

    cmd_col = 20
    leading = 4
    gap = 2
    indent_width = leading + cmd_col + gap  # 26
    indent_str = " " * indent_width

    def _print_row(cmd: str, desc: str) -> None:
        try:
            term_w = shutil.get_terminal_size((80, 24)).columns
        except Exception:
            term_w = 80
        desc_w = max(20, term_w - indent_width)
        lines = textwrap.wrap(desc, width=desc_w) or [""]
        # Build Text objects directly instead of using Rich's markup
        # parser — markup strings like ``[dim]...[/]`` go through Rich's
        # console renderer which strips leading whitespace and re-wraps
        # at its own console width (re-wrapping our pre-wrapped lines
        # mid-word, and dropping the hanging indent). Plain Text objects
        # plus ``soft_wrap=True`` keep the spans and indent intact.
        first = Text()
        first.append(" " * leading)
        first.append(cmd.ljust(cmd_col), style=f"bold {BEE_YELLOW}")
        first.append(" " * gap)
        first.append(lines[0], style=BEE_DIM)
        err_console.print(first, soft_wrap=True)
        for line in lines[1:]:
            cont = Text()
            cont.append(indent_str)
            cont.append(line, style=BEE_DIM)
            err_console.print(cont, soft_wrap=True)

    err_console.print()
    groups = {
        "Pages":        ["scrape", "crawl"],
        "Search":       ["google", "fast-search"],
        "Marketplaces": ["amazon-product", "amazon-search",
                         "walmart-product", "walmart-search"],
        "Media":        ["youtube-search", "youtube-metadata"],
        "AI":           ["chatgpt"],
        "Learn":        ["tutorial"],
        "Account":      ["auth", "logout"],
        "Tools":        ["usage", "schedule", "export", "docs", "unsafe"],
    }
    for i, (group_name, cmds) in enumerate(groups.items()):
        if i > 0:
            err_console.print()  # blank row between categories for breathing room
        err_console.print(f"  [{BEE_DIM}]{group_name}[/]")
        for cmd in cmds:
            _print_row(cmd, commands.get(cmd, ""))
    err_console.print()
    err_console.print(f"  [{BEE_DIM}]REPL[/]")
    for cmd, desc in [
        (":help, :?",   "Show this command list"),
        (":clear",      "Clear the screen"),
        (":view",       "Scroll the last command's output ('crawl' = crawl log, or pass a path)"),
        (":set K=V ...", "Set one or more session defaults"),
        (":unset K",    "Remove a session default ('all' or '*' clears every)"),
        (":reset",      "Clear every session default"),
        (":show",       "Show current session defaults"),
        ("!<cmd>",      "Run a shell command (requires unsafe mode)"),
        (":q, :quit",   "Quit the REPL"),
    ]:
        _print_row(cmd, desc)
    err_console.print()


def _print_command_header(args: list[str]) -> None:
    import shutil

    width = shutil.get_terminal_size((80, 24)).columns
    label = " " + " ".join(args) + " "
    fill = max(3, width - len(label) - 6)
    line = Text()
    line.append("─── ", style=BEE_DIM)
    line.append(label, style=f"bold {BEE_YELLOW}")
    line.append("─" * fill, style=BEE_DIM)
    err_console.print(line)


def _print_command_footer(status: str, duration: float) -> None:
    line = Text()
    line.append("  ")
    if status == "ok":
        line.append("✓", style=f"bold {_GREEN}")
    elif status == "fail":
        line.append("✗", style=f"bold {BEE_RED}")
    elif status == "stopped":
        line.append("■", style=f"bold {BEE_YELLOW}")
    line.append(f"  {duration:.2f}s", style=BEE_DIM)
    err_console.print(line)
    err_console.print()


# ---------------------------------------------------------------------------
# Slash-command dispatcher
# ---------------------------------------------------------------------------


def _open_pager(path: str) -> None:
    """Cross-platform scrollable pager built on prompt_toolkit.

    Replaces external tools (`less` on Unix, `more` on Windows) with an
    in-process viewer so the CLI works identically everywhere with no extra
    install. Arrow keys / page up-down / home / end / mouse wheel scroll;
    `q` or `Esc` exits back to the REPL. Long lines wrap to the terminal
    width so you can see all of a wide JSON or HTML response without
    horizontal scrolling. Press `p` to toggle pretty-printed JSON.
    """
    import json
    from pathlib import Path

    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.filters import Condition
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.dimension import D
    from prompt_toolkit.styles import Style

    raw_text = Path(path).read_text(encoding="utf-8", errors="replace")

    # If the cached output is valid JSON, prepare a pretty-printed
    # version up-front. We default to pretty mode so the user sees the
    # human-readable form first; `r` toggles raw if they need to grep
    # the original bytes. When the content isn't JSON, pretty is
    # unavailable and we stick with raw.
    pretty_text: str | None
    try:
        pretty_text = json.dumps(
            json.loads(raw_text), indent=2, ensure_ascii=False
        )
    except Exception:
        pretty_text = None

    mode = ["pretty" if pretty_text is not None else "raw"]

    buffer = Buffer(read_only=Condition(lambda: True))

    def _set_text(s: str) -> None:
        buffer.set_document(Document(text=s, cursor_position=0), bypass_readonly=True)

    _set_text(pretty_text if mode[0] == "pretty" else raw_text)

    def _current_line_count() -> int:
        return buffer.document.line_count

    text_window = Window(
        content=BufferControl(buffer=buffer),
        # Wrap long lines so a multi-KB JSON / HTML response is fully
        # visible without horizontal scrolling. The previous default
        # (wrap_lines=False) clipped at column-N and the rest was just
        # gone unless the user used Left/Right scrolling.
        wrap_lines=True,
    )

    def _status_line():
        cursor_line = buffer.document.cursor_position_row + 1
        total = _current_line_count()
        pct = int(cursor_line / max(1, total) * 100)
        mode_label = "pretty" if mode[0] == "pretty" else "raw"
        # `r` toggles raw on/off. Hidden when there's no pretty version
        # available (non-JSON content) — there'd be nothing to toggle to.
        toggle_hint = (
            ("r: pretty" if mode[0] == "raw" else "r: raw")
            if pretty_text is not None else ""
        )
        right_hint = (
            "↑↓ PgUp/PgDn scroll" + (f"  ·  {toggle_hint}" if toggle_hint else "")
            + "  ·  q to exit"
        )
        return [
            ("class:pager.bar", "  "),
            ("class:pager.value", f"{cursor_line}/{total}"),
            ("class:pager.bar", f"  ({pct}%)  ·  {mode_label}  ·  "),
            ("class:pager.label", path),
            ("class:pager.bar", "    "),
            ("class:pager.hint", right_hint),
        ]

    status_window = Window(
        content=FormattedTextControl(_status_line),
        height=D.exact(1),
    )

    layout = Layout(HSplit([text_window, status_window]))

    kb = KeyBindings()

    @kb.add("q")
    @kb.add("c-c")
    def _exit(event):
        event.app.exit()

    # Esc gets its own binding with ``eager=True`` so it fires immediately
    # instead of waiting through prompt_toolkit's internal key-processor
    # ``timeoutlen`` (the buffered-input default + any partial-match
    # search across implicit bindings). Without eager the user perceives
    # a multi-second pause between pressing Esc and the pager exiting.
    @kb.add("escape", eager=True)
    def _exit_esc(event):
        event.app.exit()

    @kb.add("r")
    def _toggle_raw(_e):
        # No-op if the content isn't JSON — pretty isn't available, so
        # we're already showing raw and there's nothing to toggle to.
        if pretty_text is None:
            return
        if mode[0] == "pretty":
            mode[0] = "raw"
            _set_text(raw_text)
        else:
            mode[0] = "pretty"
            _set_text(pretty_text)

    @kb.add("up")
    def _up(_e):
        buffer.cursor_up()

    @kb.add("down")
    def _down(_e):
        buffer.cursor_down()

    @kb.add("pageup")
    def _pgup(_e):
        buffer.cursor_up(count=20)

    @kb.add("pagedown")
    def _pgdn(_e):
        buffer.cursor_down(count=20)

    @kb.add("home")
    def _home(event):
        buffer.cursor_position = 0

    @kb.add("end")
    def _end(event):
        buffer.cursor_position = len(buffer.text)

    @kb.add("left")
    def _left(_e):
        buffer.cursor_left()

    @kb.add("right")
    def _right(_e):
        buffer.cursor_right()

    style = Style.from_dict(
        {
            "pager.bar":   f"bg:{_BG_CHIP} {BEE_DIM}",
            "pager.value": f"bg:{_BG_CHIP} {BEE_YELLOW} bold",
            "pager.label": f"bg:{_BG_CHIP} {BEE_DIM}",
            "pager.hint":  f"bg:{_BG_CHIP} {_DIM2}",
        }
    )

    pager_app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=True,
        mouse_support=True,
    )
    # Shrink BOTH escape-related timeouts. ``ttimeoutlen`` is the parser-
    # level wait for "is this Esc-byte the start of an escape sequence",
    # default 0.5s. ``timeoutlen`` is the key-processor wait for "is this
    # complete key the start of a multi-key binding", default 1.0s.
    # Together with eager=True on the Esc-exit binding above, this makes
    # Esc fire essentially instantly in the pager. 50ms is enough for
    # any well-formed escape sequence from a modern terminal.
    pager_app.ttimeoutlen = 0.05
    pager_app.timeoutlen = 0.05

    # We're (almost certainly) called from inside the REPL's prompt_toolkit
    # event loop — a sync key-binding handler invoked `:view`. Calling
    # ``pager_app.run()`` here would hit ``asyncio.run()`` from inside a
    # running loop and raise. Detect that and farm the pager out to a
    # worker thread which has no loop of its own, so ``app.run()`` can
    # safely create a fresh one. Blocking the main thread on ``join()``
    # freezes the outer app's rendering while the pager has the terminal,
    # which is exactly what we want — the pager uses the alternate screen
    # buffer (full_screen=True), then yields it back on exit.
    try:
        import asyncio as _asyncio_check

        _asyncio_check.get_running_loop()
        in_loop = True
    except RuntimeError:
        in_loop = False

    if not in_loop:
        pager_app.run()
        return

    err_holder: list[BaseException | None] = [None]

    def _run_in_worker() -> None:
        try:
            pager_app.run()
        except BaseException as e:
            err_holder[0] = e

    t = threading.Thread(target=_run_in_worker, daemon=False)
    t.start()
    t.join()
    if err_holder[0] is not None:
        raise err_holder[0]
    # NOTE: the caller (run_repl, after :view) is responsible for
    # re-entering the alt buffer and resetting the outer app's renderer
    # cache. prompt_toolkit's Application.run cleanup emits
    # ``\x1b[?1049l`` on exit, which kicks the outer REPL out of the
    # alt buffer too — only the caller has access to ``app`` to invalidate
    # it properly, so the cleanup lives there.


def _normalize_setting_key(key: str) -> str:
    """Strip leading dashes; settings keys are stored without `--` prefix.

    Hyphen vs underscore is left to the user — we don't normalise either way
    because click options exist in both forms across the codebase. The
    validation check (against the click flag list) settles which is correct.
    """
    return key.strip().lstrip("-")


def _parse_set_args(rest: str) -> list[tuple[str, str]] | str:
    """Parse the argument string for `:set`. Returns either a list of
    (key, value) pairs, or an error string explaining what's wrong.

    Accepted forms (mix and match in one line):
      :set country-code=fr
      :set --country-code fr
      :set country-code=fr premium-proxy=true device=mobile
      :set --country-code fr --premium-proxy true
    """
    try:
        tokens = shlex.split(rest)
    except ValueError as e:
        return f"parse error: {e}"

    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if "=" in tok and not tok.startswith("="):
            key, _, value = tok.partition("=")
            key = _normalize_setting_key(key)
            value = value.strip()
            if not key or value == "":
                return f"empty key or value in '{tok}'"
            pairs.append((key, value))
            i += 1
        elif tok.startswith("--"):
            key = _normalize_setting_key(tok)
            if i + 1 >= len(tokens):
                return f"missing value for --{key}"
            pairs.append((key, tokens[i + 1]))
            i += 2
        else:
            return (
                f"unexpected '{tok}'. Use key=value or --key value "
                f"(e.g. :set country-code=fr or :set --country-code fr)"
            )
    return pairs


def _handle_meta(
    line: str,
    state: SessionState,
    command_help: dict[str, str],
    all_known_flags: set[str],
    bool_flags: set[str],
    choice_flags: dict[str, list[str]],
    scrollback: ScrollbackBuffer | None = None,
) -> str | None:
    parts = line.strip().split(None, 1)
    head = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    head_low = head.lower()

    if head_low in {":q", ":quit", "exit", "quit", "q"}:
        return "quit"
    if head_low in {":help", ":?", "help", "?"}:
        _print_help(command_help)
        return "ok"
    if head_low in {":clear", "clear"}:
        if scrollback is not None:
            # full_screen mode — clear our virtual buffer
            with scrollback._lock:
                scrollback.lines.clear()
                scrollback.scroll_offset = 0
        else:
            # Legacy fallback (shouldn't trigger in current REPL)
            sys.stderr.write("\033[2J\033[H")
            sys.stderr.flush()
        return "ok"
    if head_low == ":show":
        if not state.settings:
            err_console.print(f"  [{BEE_DIM}]No session defaults set.[/]")
        else:
            err_console.print()
            for k, v in state.settings.items():
                err_console.print(
                    f"  [bold {BEE_YELLOW}]{k:<20}[/]  [dim]{v}[/]"
                )
            err_console.print()
        return "ok"
    if head_low == ":view":
        from pathlib import Path

        cache_dir = Path.home() / ".cache" / "scrapingbee-cli"
        crawl_log = cache_dir / "crawl.log"
        target_arg = rest.strip()
        # `:view`                  → last command's output
        # `:view crawl`            → the crawl log written by the most recent
        #                            `crawl` run in REPL mode
        # `:view crawl <log-path>` → also alias-mode, but ONLY when the
        #                            path after ``crawl`` resolves to the
        #                            actual crawl.log on disk. This lets
        #                            users copy the full hint line ("crawl
        #                            /Users/.../crawl.log") into the
        #                            prompt; random text after ``crawl``
        #                            falls through to "file not found"
        #                            instead of silently opening the log.
        # `:view <path>`           → arbitrary file (must exist)
        if not target_arg:
            target_path = cache_dir / "last-output"
            missing_msg = "no recent output to view"
        elif target_arg.lower() == "crawl":
            target_path = crawl_log
            missing_msg = "no crawl log yet — run `crawl ...` first"
        elif target_arg.lower().startswith("crawl "):
            after = target_arg[len("crawl "):].strip()
            try:
                supplied_path = Path(after).expanduser().resolve(strict=False)
                if supplied_path == crawl_log.resolve(strict=False):
                    target_path = crawl_log
                    missing_msg = "no crawl log yet — run `crawl ...` first"
                else:
                    target_path = Path(target_arg).expanduser()
                    missing_msg = f"file not found: {target_arg}"
            except Exception:
                target_path = Path(target_arg).expanduser()
                missing_msg = f"file not found: {target_arg}"
        else:
            target_path = Path(target_arg).expanduser()
            missing_msg = f"file not found: {target_arg}"
        if not target_path.exists():
            err_console.print(f"  [{BEE_DIM}]{missing_msg}[/]")
            return "ok"
        try:
            _open_pager(str(target_path))
        except FileNotFoundError:
            # File got deleted between exists() and read() — race with cleanup
            err_console.print(f"  [{BEE_DIM}]file no longer available[/]")
        except Exception as e:
            err_console.print(f"  [bold {BEE_RED}]pager error:[/] {e}")
            err_console.print(
                f"  [{BEE_DIM}]full output saved at[/] "
                f"[bold {BEE_YELLOW}]{target_path}[/]"
            )
        return "ok"

    if head_low in {":reset", ":unset-all"}:
        n = len(state.settings)
        state.settings.clear()
        err_console.print(f"  [{BEE_DIM}]cleared {n} setting(s)[/]")
        return "ok"
    if head_low == ":unset":
        target = rest.strip()
        if not target:
            err_console.print(
                f"  [bold {BEE_RED}]usage:[/] :unset KEY  |  :unset *  |  :reset"
            )
            return "ok"
        if target in {"*", "all"}:
            n = len(state.settings)
            state.settings.clear()
            err_console.print(f"  [{BEE_DIM}]cleared {n} setting(s)[/]")
            return "ok"
        # Allow space- or comma-separated multiple keys.
        keys = [_normalize_setting_key(k) for k in re.split(r"[,\s]+", target) if k]
        for key in keys:
            if key in state.settings:
                del state.settings[key]
                err_console.print(
                    f"  [{BEE_DIM}]unset[/] [bold {BEE_YELLOW}]{key}[/]"
                )
            else:
                err_console.print(f"  [{BEE_DIM}]not set:[/] {key}")
        return "ok"
    if head_low == ":set":
        if not rest.strip():
            err_console.print(
                f"  [bold {BEE_RED}]usage:[/] :set KEY=VALUE [KEY=VALUE ...]"
            )
            err_console.print(
                f"  [{BEE_DIM}]    or:[/] :set --KEY VALUE [--KEY VALUE ...]"
            )
            return "ok"
        parsed = _parse_set_args(rest)
        if isinstance(parsed, str):
            err_console.print(f"  [bold {BEE_RED}]:set[/] {parsed}")
            return "ok"

        valid_keys = {f.lstrip("-") for f in all_known_flags}
        applied: list[tuple[str, str]] = []
        rejected: list[str] = []
        for key, value in parsed:
            if key not in valid_keys:
                err_console.print(
                    f"  [bold {BEE_RED}]unknown option:[/] "
                    f"[bold {BEE_YELLOW}]--{key}[/]"
                )
                suggestion = _suggest(key, valid_keys, threshold=2)
                if suggestion:
                    err_console.print(
                        f"  [{BEE_DIM}]  did you mean[/] "
                        f"[bold {BEE_YELLOW}]--{suggestion}[/][{BEE_DIM}]?[/]"
                    )
                rejected.append(key)
                continue
            flag = f"--{key}"
            # Validate choices
            if flag in choice_flags and value not in choice_flags[flag]:
                err_console.print(
                    f"  [bold {BEE_RED}]invalid value for[/] "
                    f"[bold {BEE_YELLOW}]--{key}[/][bold {BEE_RED}]:[/] {value}"
                )
                err_console.print(
                    f"  [{BEE_DIM}]  choices:[/] "
                    + ", ".join(choice_flags[flag])
                )
                rejected.append(key)
                continue
            # Validate bool values
            if flag in bool_flags and value.lower() not in (
                "true", "false", "yes", "no", "1", "0", "on", "off"
            ):
                err_console.print(
                    f"  [bold {BEE_RED}]--{key} expects a bool, got:[/] {value}"
                )
                rejected.append(key)
                continue
            state.settings[key] = value
            applied.append((key, value))

        for key, value in applied:
            err_console.print(
                f"  [{BEE_DIM}]set[/] [bold {BEE_YELLOW}]{key}[/] = "
                f"[dim]{value}[/]"
            )
        return "ok"
    return None


# ---------------------------------------------------------------------------
# Completer
# ---------------------------------------------------------------------------


def _make_completer(
    commands: list[str],
    command_flags: dict[str, list[str]],
    bool_flags: set[str],
    choice_flags: dict[str, list[str]],
    command_help: dict[str, str],
):
    from prompt_toolkit.completion import Completer, Completion

    meta_cmds = [
        ":help", ":?", ":clear", ":view", ":set", ":unset", ":reset", ":show",
        ":q", ":quit",
    ]

    # Precompute the union of every flag known to any command. Used as a
    # fallback completion pool when the user's typed command isn't
    # recognised (typo, in-progress rename, etc.) — without this the
    # completer would silently stop suggesting anything as soon as the
    # first word is unknown, which is confusing UX.
    _all_known_flags: list[str] = sorted({
        f for flags in command_flags.values() for f in flags
    })

    class BeeCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor.lstrip()
            words = text.split()
            on_first = (not text) or (len(words) == 1 and not text.endswith(" "))

            if on_first:
                partial = words[0].lower() if words else ""
                pool: list[tuple[str, str]] = [(c, command_help.get(c, "")) for c in commands]
                pool.extend((m, "REPL meta") for m in meta_cmds)
                for cmd, meta in sorted(pool):
                    if cmd.startswith(partial):
                        yield Completion(
                            cmd, start_position=-len(partial), display_meta=meta
                        )
                return

            cmd_name = words[0]
            # If cmd_name is unknown, fall back to the union of all flags
            # so the user still gets *some* suggestions instead of silence.
            # Display "(unknown command)" so they know completions may
            # not actually apply to what they typed.
            cmd_known = cmd_name in command_flags
            flags_for_cmd = (
                command_flags[cmd_name] if cmd_known else _all_known_flags
            )
            last = words[-1] if words else ""
            prev = words[-2] if len(words) >= 2 else ""

            if text.endswith(" ") and prev in bool_flags:
                yield Completion("true", display_meta="enable")
                yield Completion("false", display_meta="disable")
                return
            if text.endswith(" ") and prev in choice_flags:
                for v in choice_flags[prev]:
                    yield Completion(v)
                return
            if len(words) >= 2 and not last.startswith("-"):
                if prev in bool_flags:
                    for v in ("true", "false"):
                        if v.startswith(last.lower()):
                            yield Completion(v, start_position=-len(last))
                    return
                if prev in choice_flags:
                    for v in choice_flags[prev]:
                        if v.startswith(last.lower()):
                            yield Completion(v, start_position=-len(last))
                    return
            if last.startswith("-"):
                meta_label = "" if cmd_known else "(unknown command)"
                for flag in flags_for_cmd:
                    if flag.startswith(last):
                        yield Completion(
                            flag, start_position=-len(last), display_meta=meta_label
                        )

    return BeeCompleter()


# ---------------------------------------------------------------------------
# Multi-line: trailing backslash continues the next line
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Main loop — persistent Application + patch_stdout
# ---------------------------------------------------------------------------


_INTERACTIVE_COMMANDS = {"tutorial", "auth"}


def run_repl(cli_group: Any, version: str, *, keep_bg: bool = False) -> None:
    """Run the REPL with the Ink-style hybrid pattern.

    Banner is printed to real stdout, lands in scrollback. The input + toolbar
    live in a persistent Application(full_screen=False) at the bottom of the
    terminal. The whole loop runs inside ``patch_stdout()`` so any print or
    click.echo from a command flows through real terminal stdout (real
    scrollback, real selection) while the bottom strip is redrawn afterwards.
    """
    import shutil
    from pathlib import Path

    import click
    from prompt_toolkit.application import Application
    from prompt_toolkit.application.run_in_terminal import run_in_terminal
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.filters import Condition, has_completions
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import ConditionalContainer, HSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.layout.dimension import D
    from prompt_toolkit.styles import Style

    from .theme import set_repl_mode

    set_repl_mode(True)

    # ── Asyncio loop tracking for fast Ctrl+C ───────────────────────────────
    # Commands like ``scrape`` run ``asyncio.run(...)`` inside a worker
    # thread to drive aiohttp. While the loop is in ``select()`` waiting
    # on a socket, ``PyThreadState_SetAsyncExc`` doesn't deliver an
    # interrupt — it only fires at the next Python bytecode boundary, and
    # no bytecode runs until ``select()`` returns (typically when the
    # ScrapingBee API responds, which can be 30+ seconds).
    #
    # We monkey-patch ``asyncio.run`` for the duration of this REPL
    # session so we can keep a handle to the worker's loop. The Ctrl+C
    # handler then uses ``call_soon_threadsafe`` to cancel in-flight
    # tasks — that wakes the selector immediately and raises
    # ``CancelledError`` on the await, which propagates out cleanly
    # (the worker's except clause turns it into "stopped").
    import asyncio as _asyncio_mod

    _active_worker_loop: list[Any] = [None]
    _original_asyncio_run = _asyncio_mod.run

    def _tracking_loop_factory():
        loop = _asyncio_mod.new_event_loop()
        _active_worker_loop[0] = loop
        return loop

    def _tracking_asyncio_run(main, *, debug=None, loop_factory=None):
        try:
            return _original_asyncio_run(
                main,
                debug=debug,
                loop_factory=loop_factory or _tracking_loop_factory,
            )
        finally:
            _active_worker_loop[0] = None

    _asyncio_mod.run = _tracking_asyncio_run

    # ── Click tree introspection ────────────────────────────────────────────
    command_help, command_flags, bool_flags, choice_flags = _walk_click_tree(cli_group)
    command_names = sorted(command_flags.keys())
    all_known_flags: set[str] = set()
    for flags_list in command_flags.values():
        all_known_flags.update(flags_list)

    state = SessionState()
    state.refresh_credits_from_cache()

    from .config import get_api_key_if_set

    state.api_key_set = bool(get_api_key_if_set(None))

    history_path = str(Path.home() / ".config" / "scrapingbee-cli" / ".history")
    Path(history_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        history = _make_capped_history(history_path, max_entries=10_000)
    except Exception:
        history = None  # type: ignore[assignment]

    completer = _make_completer(
        command_names, command_flags, bool_flags, choice_flags, command_help
    )

    # Set the terminal background to pure black AND the default foreground to
    # light grey for the REPL session. We need both — otherwise, any text the
    # terminal renders with its theme-default foreground (e.g. a number or an
    # unstyled token in the lexer) keeps the user's theme's fg colour, which
    # may be near-black on a light theme → invisible on our forced-black bg.
    # OSC 11 sets bg, OSC 10 sets fg. BEL terminator (`\x07`) is the most
    # compatible across Mac Terminal, Warp, iTerm2, kitty, alacritty,
    # gnome-terminal, Windows Terminal. Opt out with `scrapingbee --keep-bg`.
    _set_black_bg = not keep_bg
    if _set_black_bg:
        sys.stdout.write("\033]11;#000000\007")
        sys.stdout.write("\033]10;#EAEAEA\007")
        sys.stdout.flush()

    # Create the virtual scrollback buffer and seed it with the banner.
    # In full_screen mode we own the alt buffer entirely. The banner is
    # rendered as a FIXED Window at the top of the layout (not pushed into
    # scrollback), so it stays anchored while command output flows in the
    # scrollback area below it. Trade-off: banner consumes its natural
    # height of terminal rows every frame, but the user keeps the brand
    # surface visible (their explicit ask: "when scraping banner should
    # not disappear").
    scrollback = ScrollbackBuffer()
    rows = shutil.get_terminal_size((80, 24)).lines  # kept for API-key prompt sizing

    # ── Multi-line in-place progress renderer ───────────────────────────────
    # Wired so batch operations (``scrape --input-file ...``) can update a
    # 3-row honeycomb progress widget in place rather than appending a new
    # row per completion. The renderer keeps track of how many lines the
    # previous frame consumed so the next frame overwrites the same band.
    from .theme import set_progress_renderer as _set_progress_renderer

    _progress_line_count = [0]

    def _render_progress(rendered_lines: list[str]) -> None:
        from prompt_toolkit.formatted_text import ANSI, to_formatted_text

        fragments_per_line: list[list[tuple[str, str]]] = []
        for raw in rendered_lines:
            try:
                fragments_per_line.append(list(to_formatted_text(ANSI(raw))))
            except Exception:
                fragments_per_line.append([("", raw)])
        n = len(fragments_per_line)
        prev = _progress_line_count[0]
        if prev > 0 and prev == n:
            scrollback.replace_last_n_lines(prev, fragments_per_line)
        else:
            # First frame, or row-count changed (rare): append fresh and
            # remember how many lines to overwrite next time.
            for f in fragments_per_line:
                scrollback.append_fragments(f)
        _progress_line_count[0] = n

    _set_progress_renderer(_render_progress)

    # ── First-run API key state ─────────────────────────────────────────────
    # When no API key is configured we open the REPL UI in a "first-run"
    # mode: the bottom prompt changes from ``❯`` to ``API key: ``, the
    # input field is masked via PasswordProcessor, and ``_submit`` routes
    # to ``_handle_first_run_key`` (which validates against /usage and
    # writes to ~/.config/scrapingbee-cli/.env). Once a key validates we
    # flip the flag and the prompt transitions to normal command mode in
    # place — no app restart, no screen flicker.
    _first_run_needs_key = [not state.api_key_set]
    if _first_run_needs_key[0]:
        # Render the welcome lines into the scrollback area so the user
        # sees them right below the banner while the input field shows
        # ``API key:``. We use a throwaway rich Console to produce ANSI,
        # then append to the scrollback buffer (the live ``err_console``
        # path doesn't work yet — patch_stdout isn't installed until
        # ``app.run()`` starts).
        try:
            from io import StringIO as _SIO
            from rich.console import Console as _RC

            _buf = _SIO()
            _c = _RC(
                file=_buf, force_terminal=True, color_system="truecolor",
                highlight=False, width=shutil.get_terminal_size((80, 24)).columns,
            )
            _c.print(
                f"  [{BEE_DIM}]Welcome! Enter your API key to get started — "
                f"find it at [bold {BEE_YELLOW}]dashboard.scrapingbee.com/dashboard[/]"
                f"[{BEE_DIM}].[/]"
            )
            _c.print()
            scrollback.append_ansi_text(_buf.getvalue())
        except Exception:
            pass

    # ── Input buffer ────────────────────────────────────────────────────────
    # Locked while a worker thread is running a command so the user can't
    # submit another command on top of the first one (their outputs would
    # interleave through patched stdout).
    is_input_locked = [False]
    # Reference to the currently-running worker thread (or None). Used by the
    # Ctrl+C handler to inject KeyboardInterrupt into the worker so the user
    # can stop a long scrape without exiting the REPL.
    current_worker: list[threading.Thread | None] = [None]
    # Currently-running shell subprocess (when the user submits ``!cmd``).
    # Ctrl+C uses this to terminate the child process directly — injecting
    # KeyboardInterrupt into the worker thread alone doesn't fire while the
    # thread is blocked reading the subprocess's stdout in a C-level read().
    current_subprocess: list[Any] = [None]

    input_buffer = Buffer(
        history=history,
        completer=completer,
        complete_while_typing=False,
        auto_suggest=BeeAutoSuggest(
            command_names=command_names,
            command_flags=command_flags,
            bool_flags=bool_flags,
            choice_flags=choice_flags,
            history=history,
            is_disabled=lambda: _first_run_needs_key[0],
        ),
        multiline=False,
        read_only=Condition(lambda: is_input_locked[0]),
    )

    def _line_prefix(line_no, _wrap_count):
        if line_no == 0:
            if _first_run_needs_key[0]:
                return [("class:promptmark", "API key: ")]
            return [("class:promptmark", "❯ ")]
        return [("", "  ")]

    # While a command is in flight we collapse the input window's height to
    # 0 — instead of hiding it via ConditionalContainer. Hiding via Conditional
    # makes the focused window invisible, but prompt_toolkit still places the
    # terminal cursor *somewhere*, and Mac Terminal renders that cursor as a
    # visible `[` block on the first visible row. With the input still in the
    # layout but 0-rows tall, the cursor is "on" the input but in an invisible
    # row → no stray indicator anywhere.
    def _input_height():
        if state.is_running:
            return D.exact(0)
        return D(min=1, max=8)

    # ``AppendAutoSuggestion`` is the input processor that renders ghost-text
    # auto-suggestions after the cursor. Without it, ``buffer.suggestion``
    # is set correctly but never drawn — BufferControl alone only handles
    # the typed text + lexer styling. ``HighlightMatchingBracketProcessor``
    # isn't applied so we don't add it.
    #
    # ``PasswordProcessor`` masks the input when ``_first_run_needs_key`` is
    # True so an API key isn't visible on-screen. Wrapped in a
    # ``ConditionalProcessor`` so masking flips off automatically once the
    # key validates and we transition to normal command mode.
    from prompt_toolkit.layout.processors import (
        AppendAutoSuggestion,
        ConditionalProcessor,
        PasswordProcessor,
    )

    input_window = Window(
        content=BufferControl(
            buffer=input_buffer,
            lexer=_make_lexer(),
            input_processors=[
                ConditionalProcessor(
                    PasswordProcessor(),
                    Condition(lambda: _first_run_needs_key[0]),
                ),
                AppendAutoSuggestion(),
            ],
        ),
        get_line_prefix=_line_prefix,
        wrap_lines=True,
        height=_input_height,
        dont_extend_height=True,
        always_hide_cursor=Condition(lambda: state.is_running),
    )

    toolbar_window = Window(
        content=FormattedTextControl(_make_toolbar(state)),
        height=D.exact(1),
        wrap_lines=False,  # pin explicitly so toolbar can never grow to 2 rows
    )

    # Live "running command" line that appears above the input only while a
    # command is in flight. Renders the typed line with a sweeping white-glim
    # shimmer so the user has clear visual feedback that something is happening.
    def _running_text() -> list[tuple[str, str]]:
        if not state.is_running or not state.running_command_text:
            return []
        text = f"❯ {state.running_command_text}"
        pos = state.tick % max(1, len(text))
        return _shimmer_pt(text, pos, BEE_YELLOW)

    running_window = ConditionalContainer(
        content=Window(
            content=FormattedTextControl(_running_text),
            height=D.exact(1),
        ),
        filter=Condition(lambda: state.is_running),
    )

    # ── Scrollback Window — virtual buffer rendered as the top section ─────
    # This Window fills the vertical space above the running line / input /
    # toolbar. It renders whatever ScrollbackBuffer says is visible based
    # on the current scroll offset. The user scrolls it with PgUp/PgDn etc.
    def _scrollback_render() -> list[tuple[str, str]]:
        height = 20
        width = 80
        try:
            from prompt_toolkit.application import get_app as _get_app

            _app = _get_app()
            if getattr(_app, "is_running", False):
                size = _app.output.get_size()
                # Reserve rows for the full banner + everything below the
                # scrollback in the layout: banner_visual + spacer_top(1)
                # + separator(1) + running_or_input(1) + spacer_bottom(1)
                # + toolbar(1) = banner_visual + 5.
                reserved = _banner_visual_height + 5
                height = max(1, size.rows - reserved)
                width = max(1, size.columns)
        except Exception:
            pass
        # Use visual-row pagination so scrolling moves exactly one terminal
        # row per step, even through long single-line content that would
        # otherwise wrap into many visual rows. We split at width-1 so a
        # full-width row never accidentally pushes the cursor onto the
        # next terminal row (which some terminals do at col == width).
        visual_rows = scrollback.get_visible_visual(height, max(1, width - 1))
        out: list[tuple[str, str]] = []
        for i, row in enumerate(visual_rows):
            if i > 0:
                out.append(("", "\n"))
            out.extend(row)
        return out

    # FormattedTextControl subclass that routes mouse wheel / trackpad
    # scroll events to our virtual buffer. prompt_toolkit's default mouse
    # mode (1000) captures button events but NOT motion, so the terminal
    # still handles drag-select natively (or with a modifier — Option on
    # Mac, Shift on most Linux terminals — depending on the terminal).
    from prompt_toolkit.mouse_events import MouseEventType
    from prompt_toolkit.layout.controls import FormattedTextControl as _PTFTC

    class _ScrollbackControl(_PTFTC):
        def mouse_handler(self, mouse_event):
            et = mouse_event.event_type
            # 1 line per wheel/trackpad event keeps motion smooth — trackpads
            # send a flurry of small events per gesture, so a tight step
            # tracks the user's finger movement closely. Larger steps (3+)
            # feel jumpy / snap-y.
            if et == MouseEventType.SCROLL_UP:
                scrollback.scroll_up(1)
                try:
                    app.invalidate()
                except Exception:
                    pass
                return None
            if et == MouseEventType.SCROLL_DOWN:
                scrollback.scroll_down(1)
                try:
                    app.invalidate()
                except Exception:
                    pass
                return None
            return NotImplemented

    scrollback_window = Window(
        content=_ScrollbackControl(_scrollback_render),
        # We pre-wrap content ourselves (see _split_fragments_to_width) so
        # each line passed to prompt_toolkit is already ≤ terminal width.
        # Disable prompt_toolkit's own line-wrapping so it doesn't try to
        # second-guess us — we want exact control of which visual rows
        # appear for accurate scroll-by-row behaviour.
        wrap_lines=False,
        always_hide_cursor=True,
    )

    # ── Pinned banner Window (smaller logo, original stacked structure) ───
    # Restores the original banner layout — ASCII logo, then version,
    # tagline, blank, hint — but uses only the SCRAPING logo (6 rows)
    # instead of stacking SCRAPING + BEE (which was 12 rows). Half the
    # vertical footprint, same look.
    _banner_visual_height = len(_SCRAPINGBEE_LOGO) + 5  # logo + 5 text rows

    def _banner_render() -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        # SCRAPING logo in brand yellow.
        for i, logo_line in enumerate(_SCRAPINGBEE_LOGO):
            if i > 0:
                out.append(("", "\n"))
            out.append((f"bold {BEE_YELLOW}", logo_line))
        # Spacer row
        out.append(("", "\n"))
        # v1.4.1
        out.append(("", "\n"))
        out.append((f"bold {BEE_YELLOW}", f"  v{version}"))
        # Tagline
        out.append(("", "\n"))
        out.append((f"{BEE_DIM}", "  Web scraping from the terminal"))
        out.append(("", "\n"))
        # Hint
        out.append((f"{BEE_DIM}", "  Type "))
        out.append((f"bold {BEE_YELLOW}", ":help"))
        out.append((f"{BEE_DIM}", " for commands, "))
        out.append((f"bold {BEE_YELLOW}", ":q"))
        out.append((f"{BEE_DIM}", " to quit"))
        return out

    def _banner_height() -> "D":
        return D.exact(_banner_visual_height)

    banner_window = Window(
        content=FormattedTextControl(_banner_render),
        height=_banner_height,
        wrap_lines=False,
        always_hide_cursor=True,
    )

    # Breathing room around the prompt area (Claude-CLI-style).
    # - blank row above the separator → visual gap from output
    # - dim horizontal rule → clear boundary between "history" and "input"
    # - blank row below the toolbar → keeps the toolbar from sitting right
    #   on the bottom edge of the terminal
    def _hr_render() -> list[tuple[str, str]]:
        try:
            from prompt_toolkit.application import get_app as _get_app

            _app = _get_app()
            if getattr(_app, "is_running", False):
                cols = _app.output.get_size().columns
            else:
                cols = 80
        except Exception:
            cols = 80
        return [("class:toolbar.hint", "─" * max(1, cols))]

    spacer_top = Window(height=D.exact(1), char=" ")
    separator = Window(
        content=FormattedTextControl(_hr_render),
        height=D.exact(1),
        always_hide_cursor=True,
    )
    spacer_bottom = Window(height=D.exact(1), char=" ")

    # FloatContainer wraps the main layout so we can hover a completion
    # popup near the cursor. Without the Float + CompletionsMenu prompt-
    # toolkit's `start_completion()` enters completion *state* but nothing
    # visible changes — the user thought Tab did nothing and pressed
    # again, hitting `complete_next` which cycled invisibly. With the
    # menu in place, the first Tab opens the popup; Up/Down navigate
    # entries; Enter / Tab inserts; Esc dismisses.
    from prompt_toolkit.layout.containers import Float, FloatContainer
    from prompt_toolkit.layout.menus import CompletionsMenu

    main_split = HSplit(
        [
            banner_window,
            scrollback_window,
            spacer_top,
            separator,
            running_window,
            input_window,
            spacer_bottom,
            toolbar_window,
        ]
    )
    layout = Layout(
        FloatContainer(
            content=main_split,
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=10, scroll_offset=1),
                ),
            ],
        )
    )

    # ── Command echo ────────────────────────────────────────────────────────
    def _echo_to_scrollback(line: str) -> None:
        """Echo the submitted command into scrollback (dim grey).

        Both chevron and line use the explicit ``#888888`` colour rather
        than mixing in Rich's ``dim`` attribute on top — on our dark
        background the compound was rendering nearly black, making the
        echo invisible. A single mid-grey shade is subdued enough to feel
        like "history" without disappearing.

        Only the *live* input prompt at the bottom uses the bright yellow
        chevron, so the eye can find "where I'm typing now" without it
        competing with past commands above.
        """
        echo = Text()
        echo.append("❯ ", style=BEE_DIM)
        echo.append(line, style=BEE_DIM)
        err_console.print(echo)

    # ── First-run API key validation ────────────────────────────────────────
    # Called from ``_submit`` on the main thread when ``_first_run_needs_key``
    # is True. The user just submitted the masked key — we validate it
    # against the live /usage endpoint, persist on success, and flip the
    # flag so subsequent submits route to ``_execute`` (normal commands).
    def _handle_first_run_key(key_raw: str, raw_with_ws: str) -> None:
        from .commands.auth import _validate_api_key
        from .config import ENV_API_KEY, save_api_key_to_dotenv

        key = key_raw.strip()
        # Pasted keys from password managers often pick up surrounding
        # whitespace. Silently strip but warn so the user knows we did.
        if key and key != raw_with_ws.rstrip("\n"):
            err_console.print(
                f"  [{BEE_DIM}]Note: stripped surrounding whitespace from your key.[/]"
            )
        if not key:
            err_console.print(
                f"  [bold {BEE_RED}]Empty key.[/] [{BEE_DIM}]Please paste your API key.[/]"
            )
            return
        err_console.print(f"  [{BEE_DIM}]Validating…[/]")
        valid, err_msg = _validate_api_key(key)
        if valid:
            try:
                save_api_key_to_dotenv(key)
            except Exception as e:
                err_console.print(
                    f"  [bold {BEE_RED}]Could not save:[/] [{BEE_DIM}]{e}[/]"
                )
            os.environ[ENV_API_KEY] = key
            state.api_key_set = True
            _first_run_needs_key[0] = False
            err_console.print(f"  [bold {BEE_YELLOW}]✓[/] API key saved.")
            # Toolbar credits/concurrency are stale (None); trigger a fresh
            # /usage fetch so the bottom strip populates without waiting
            # for the 30s tick.
            _signal_refresh_from_thread()
            try:
                app.invalidate()
            except Exception:
                pass
        else:
            err_console.print(
                f"  [bold {BEE_RED}]Invalid:[/] [{BEE_DIM}]{err_msg or 'unknown error'}. Try again.[/]"
            )

    # ── Shell command execution (`!cmd` in the REPL) ────────────────────────
    # Runs in a worker thread so the REPL stays responsive. stdout+stderr
    # are merged and streamed line-by-line through the patched
    # ``sys.stdout`` (which writes into scrollback). Ctrl+C terminates the
    # child process via ``current_subprocess[0].terminate()`` AND injects
    # KeyboardInterrupt into the worker thread (so a hung read returns
    # promptly).
    def _execute_shell(shell_cmd: str, original_line: str, echo_idx: int) -> None:
        import subprocess

        output_start_index = echo_idx
        start = time.monotonic()
        status_ref = ["ok"]
        state.is_running = True
        state.running_command = "shell"
        state.running_command_text = original_line
        state.run_start = start

        def _run() -> None:
            try:
                # Use the system shell so users can pipe / redirect / glob
                # naturally. Merge stderr into stdout for unified streaming;
                # any separation is the user's problem (they'd redirect
                # 2>&1 themselves if they cared).
                proc = subprocess.Popen(  # noqa: S602 — gated by exec_gate
                    shell_cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                current_subprocess[0] = proc
                try:
                    assert proc.stdout is not None
                    for chunk in iter(proc.stdout.readline, ""):
                        sys.stdout.write(chunk)
                finally:
                    code = proc.wait()
                    current_subprocess[0] = None
                if code != 0:
                    status_ref[0] = "fail"
                    err_console.print(
                        f"  [{BEE_DIM}]exit code {code}[/]"
                    )
            except KeyboardInterrupt:
                # Ctrl+C: stop the child if it's still running, then mark
                # the command as cancelled in the footer.
                proc = current_subprocess[0]
                if proc is not None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                err_console.print(f"  [{BEE_DIM}]stopped[/]")
                status_ref[0] = "stopped"
            except Exception as e:
                err_console.print(f"  [bold {BEE_RED}]error:[/] {e}")
                status_ref[0] = "fail"

        def _finish() -> None:
            duration = time.monotonic() - start
            state.is_running = False
            state.running_command = None
            state.running_command_text = None
            state.run_start = None
            # Splice the dim echo line above the streamed output.
            try:
                from prompt_toolkit.formatted_text import (
                    ANSI as _ANSI,
                    to_formatted_text as _tft,
                )
                from io import StringIO as _SIO
                from rich.console import Console as _RC

                _buf = _SIO()
                _c = _RC(
                    file=_buf, force_terminal=True, color_system="truecolor",
                    highlight=False, width=200,
                )
                _echo_t = Text()
                _echo_t.append("❯ ", style=BEE_DIM)
                _echo_t.append(original_line, style=BEE_DIM)
                _c.print(_echo_t, end="")
                _echo_fragments = list(_tft(_ANSI(_buf.getvalue())))
                scrollback.insert_line(output_start_index, _echo_fragments)
            except Exception:
                pass
            _print_command_footer(status_ref[0], duration)
            state.last_command = "shell"
            state.last_status = status_ref[0]
            state.last_duration = duration
            is_input_locked[0] = False
            try:
                app.invalidate()
            except Exception:
                pass

        is_input_locked[0] = True
        try:
            app.invalidate()
        except Exception:
            pass

        def _worker() -> None:
            try:
                _run()
            finally:
                current_worker[0] = None
                try:
                    _finish()
                except Exception:
                    state.is_running = False
                    state.running_command = None
                    state.running_command_text = None
                    state.run_start = None
                    is_input_locked[0] = False
                    try:
                        app.invalidate()
                    except Exception:
                        pass

        worker_thread = threading.Thread(target=_worker, daemon=True)
        current_worker[0] = worker_thread
        worker_thread.start()

    # ── Command execution (synchronous, output flows via patched stdout) ────
    def _execute(line: str) -> bool:
        """Run a single REPL submission: meta-command or click command.

        Returns ``True`` if the submission was consumed (whether it
        succeeded, failed at runtime, or was an unknown command) — in
        every such case the user has gotten feedback and the input buffer
        should be cleared. Returns ``False`` only when the submission
        couldn't even be parsed (shlex error); the caller leaves the
        buffer untouched so the user can correct and retry without
        re-typing.
        """
        line = line.strip()
        if not line:
            return True

        # Meta-commands (`:set`, `:help`, `:show`, ...) and unknown / parse
        # errors echo the command immediately — there's no shimmer pass for
        # those. Click commands defer the echo until after completion, so
        # the live shimmering line above the input is the only on-screen
        # representation while the command runs.
        # `:q` is handled at the key-binding layer so we don't get here for it.
        #
        # Snapshot scrollback length before running the meta-handler so we
        # can splice the ``❯ line`` echo at this position afterwards. Without
        # this, the echo lands AFTER any error/info the meta-handler
        # printed (e.g. ``file not found: foo`` then ``❯ :view foo``), which
        # reads upside-down. Insert-at-position keeps the conversational
        # order: command, then its output.
        meta_echo_idx = scrollback.current_length()
        meta = _handle_meta(
            line, state, command_help, all_known_flags, bool_flags, choice_flags,
            scrollback=scrollback,
        )
        if meta == "ok":
            # If we just ran :view, the nested pager Application emitted
            # ``\x1b[?1049l`` on its exit, kicking us out of the alt screen
            # buffer. Re-enter it and reset the outer renderer so the next
            # paint goes into the fresh alt buffer instead of leaking into
            # main-screen scrollback.
            if line.strip().lower().startswith(":view"):
                try:
                    sys.__stdout__.write("\x1b[?1049h")
                    sys.__stdout__.flush()
                except Exception:
                    pass
                try:
                    app.renderer.reset()
                except Exception:
                    pass
                try:
                    app.invalidate()
                except Exception:
                    pass
            # Splice the dim echo line ABOVE whatever the meta-handler
            # printed during its run. Fall back to appending if the
            # rich-render or insert path fails.
            try:
                from prompt_toolkit.formatted_text import (
                    ANSI as _ANSI,
                    to_formatted_text as _tft,
                )
                from io import StringIO as _SIO
                from rich.console import Console as _RC
                _buf = _SIO()
                _c = _RC(
                    file=_buf, force_terminal=True, color_system="truecolor",
                    highlight=False, width=200,
                )
                _echo_t = Text()
                _echo_t.append("❯ ", style=BEE_DIM)
                _echo_t.append(line, style=BEE_DIM)
                _c.print(_echo_t, end="")
                _echo_fragments = list(_tft(_ANSI(_buf.getvalue())))
                scrollback.insert_line(meta_echo_idx, _echo_fragments)
            except Exception:
                _echo_to_scrollback(line)
            return True
        if meta == "quit":  # belt-and-braces; key binding usually catches it
            return True

        # `!shell command` — run a shell command in a worker thread,
        # streaming output into scrollback. Gated by the same unsafe-mode
        # check used by --post-process / --on-complete / schedule.
        if line.startswith("!"):
            shell_cmd = line[1:].strip()
            shell_echo_idx = scrollback.current_length()
            if not shell_cmd:
                err_console.print(
                    f"  [{BEE_DIM}]usage: ![/]"
                    f"[bold {BEE_YELLOW}]<shell command>[/]"
                )
            else:
                from .exec_gate import (
                    is_command_whitelisted,
                    is_exec_enabled,
                    is_whitelist_enabled,
                )

                if not is_exec_enabled():
                    err_console.print(
                        f"  [bold {BEE_RED}]Shell execution disabled.[/] "
                        f"[{BEE_DIM}]Enable it with `auth --unsafe` "
                        f"(requires SCRAPINGBEE_ALLOW_EXEC=1).[/]"
                    )
                elif is_whitelist_enabled() and not is_command_whitelisted(shell_cmd):
                    err_console.print(
                        f"  [bold {BEE_RED}]Blocked:[/] "
                        f"[{BEE_DIM}]command not in whitelist or contains "
                        f"shell-injection patterns.[/]"
                    )
                else:
                    _execute_shell(shell_cmd, line, shell_echo_idx)
                    return True
            # Echo the typed line above whatever error we just printed.
            try:
                from prompt_toolkit.formatted_text import (
                    ANSI as _ANSI,
                    to_formatted_text as _tft,
                )
                from io import StringIO as _SIO
                from rich.console import Console as _RC
                _buf = _SIO()
                _c = _RC(
                    file=_buf, force_terminal=True, color_system="truecolor",
                    highlight=False, width=200,
                )
                _echo_t = Text()
                _echo_t.append("❯ ", style=BEE_DIM)
                _echo_t.append(line, style=BEE_DIM)
                _c.print(_echo_t, end="")
                _echo_fragments = list(_tft(_ANSI(_buf.getvalue())))
                scrollback.insert_line(shell_echo_idx, _echo_fragments)
            except Exception:
                _echo_to_scrollback(line)
            return True

        # Tolerate users typing `scrapingbee ...` out of muscle memory.
        if line.lower().startswith("scrapingbee "):
            line = line[len("scrapingbee "):].strip()

        original_line = line  # what to echo after completion

        try:
            args = shlex.split(line)
        except ValueError as e:
            # Parse error — DO NOT consume the buffer. The user almost
            # certainly has an unclosed quote; let them fix it in-place.
            err_console.print(f"  [bold {BEE_RED}]parse error:[/] {e}")
            return False
        if not args:
            return True

        cmd_name = args[0]
        if cmd_name not in command_flags:
            _echo_to_scrollback(original_line)
            suggestion = _suggest(cmd_name, command_names)
            if suggestion:
                err_console.print(
                    f"  [bold {BEE_RED}]unknown:[/] {cmd_name}   "
                    f"[{BEE_DIM}]did you mean[/] "
                    f"[bold {BEE_YELLOW}]{suggestion}[/][{BEE_DIM}]?[/]"
                )
            else:
                err_console.print(f"  [bold {BEE_RED}]unknown:[/] {cmd_name}")
            return True

        # Bare ``auth`` in the REPL (no flags) is best served by flipping
        # the bottom prompt into first-run mode instead of routing through
        # ``run_in_terminal`` — the suspend/resume cycle to read a key in
        # the bare terminal feels jarring, and the masked in-place prompt
        # is the same flow the user just learned at startup. Variants
        # like ``auth --api-key KEY`` or ``auth --unsafe`` still go
        # through click normally.
        if cmd_name == "auth" and len(args) == 1:
            _echo_to_scrollback(original_line)
            _first_run_needs_key[0] = True
            try:
                input_buffer.reset()
            except Exception:
                pass
            err_console.print(
                f"  [{BEE_DIM}]Enter your API key below.[/]"
            )
            try:
                app.invalidate()
            except Exception:
                pass
            return True

        args = state.apply_settings_to_args(args)

        # Mark the scrollback position where this command's output will
        # start. We DO NOT echo here — while the command runs, only the
        # shimmering running line is the live indicator. After the
        # command finishes, _finish inserts the dim echo at this index
        # so the rendered order becomes:
        #     ❯ scrape https://…    (echo, inserted post-completion)
        #       <output>             (was streamed in during execution)
        #       ✓ 0.45s              (footer, appended in _finish)
        # i.e. echo + output + footer atomically appear together at the
        # moment of completion, without doubling up the live shimmer.
        output_start_index = scrollback.current_length()

        start = time.monotonic()
        status_ref = ["ok"]
        state.is_running = True
        state.running_command = cmd_name
        state.running_command_text = original_line  # used by shimmer above input
        state.run_start = start

        def _run() -> None:
            try:
                cli_group.main(args, standalone_mode=False)
            except click.UsageError as e:
                msg = str(e)
                err_console.print(f"  [bold {BEE_RED}]usage:[/] {msg}")
                if "no such option" in msg.lower():
                    m = re.search(r"--?[A-Za-z0-9-]+", msg)
                    if m:
                        bad = m.group(0)
                        suggestion = _suggest(bad, command_flags.get(cmd_name, []))
                        if suggestion:
                            err_console.print(
                                f"  [{BEE_DIM}]did you mean[/] "
                                f"[bold {BEE_YELLOW}]{suggestion}[/][{BEE_DIM}]?[/]"
                            )
                status_ref[0] = "fail"
            except click.ClickException as e:
                e.show()
                status_ref[0] = "fail"
            except (KeyboardInterrupt, _asyncio_mod.CancelledError):
                # Ctrl+C while running — the keybinding either cancelled
                # our asyncio tasks (CancelledError propagates out of the
                # await chain) or injected KeyboardInterrupt via
                # PyThreadState_SetAsyncExc. Either way surface it as a
                # deliberate stop in the footer rather than a generic
                # failure. (CancelledError is a BaseException since
                # Python 3.8 and won't be caught by ``except Exception``.)
                err_console.print(f"  [{BEE_DIM}]stopped[/]")
                status_ref[0] = "stopped"
            except SystemExit as e:
                code = e.code if e.code is not None else 0
                if code not in (0, None):
                    status_ref[0] = "fail"
            except Exception as e:
                err_console.print(f"  [bold {BEE_RED}]error:[/] {e}")
                status_ref[0] = "fail"

        def _finish() -> None:
            duration = time.monotonic() - start
            # Stop the shimmer first so the echo + footer commit cleanly to
            # scrollback without competing with the live above-input line.
            state.is_running = False
            state.running_command = None
            state.running_command_text = None
            state.run_start = None
            # Splice the dim echo line in *front of* the output rows that
            # streamed into scrollback during execution. We marked the
            # position at the start of _execute (output_start_index); any
            # rows past that index belong to this command. Inserting at
            # that index puts the echo right above its output.
            try:
                from prompt_toolkit.formatted_text import (
                    ANSI as _ANSI,
                    to_formatted_text as _tft,
                )
                from io import StringIO as _SIO
                from rich.console import Console as _RC

                _buf = _SIO()
                _c = _RC(
                    file=_buf, force_terminal=True, color_system="truecolor",
                    highlight=False, width=200,
                )
                _echo_t = Text()
                _echo_t.append("❯ ", style=BEE_DIM)
                _echo_t.append(original_line, style=BEE_DIM)
                _c.print(_echo_t, end="")
                _echo_fragments = list(_tft(_ANSI(_buf.getvalue())))
                scrollback.insert_line(output_start_index, _echo_fragments)
            except Exception:
                # Defensive fallback: if anything goes wrong with the rich
                # render, drop the echo rather than crash the REPL.
                pass
            _print_command_footer(status_ref[0], duration)
            state.last_command = cmd_name
            state.last_status = status_ref[0]
            state.last_duration = duration
            state.refresh_credits_from_cache()
            is_input_locked[0] = False
            # State mutations triggered by auth/logout need to be visible to
            # the asyncio loop's _usage_refresher and the toolbar render —
            # both run on the main loop thread while we're in the worker
            # thread. Bouncing the writes through call_soon_threadsafe
            # guarantees a happens-before edge with the loop's next tick.
            #
            # We deliberately keep ``used_credits_at_start`` across logout —
            # if the user re-authenticates with the *same* key, the next
            # refresh detects an unchanged ``api_key_hash`` and continues the
            # session counter. A *different* key triggers a reset there.
            def _apply_post_cmd_state() -> None:
                if cmd_name == "auth":
                    if get_api_key_if_set(None):
                        state.api_key_set = True
                elif cmd_name == "logout":
                    state.api_key_set = False
                    state.credits = None
                    state.credits_total = None
                    state.used_credits = None
                    state.max_concurrency = None
                    state.current_concurrency = None
                    state.last_usage_refresh_mono = None
                    # Flip back into first-run mode in place — the prompt
                    # transitions to ``API key: `` and the input is masked
                    # so the user can paste a new key without re-running
                    # ``auth`` (which would suspend the REPL via
                    # ``run_in_terminal`` and feel jarring).
                    _first_run_needs_key[0] = True
                    err_console.print(
                        f"  [{BEE_DIM}]Enter a new API key to continue, or "
                        f"[bold {BEE_YELLOW}]:q[/][{BEE_DIM}] to exit.[/]"
                    )
                # Clear the input buffer only on success — failed or
                # cancelled commands leave the line in place so the user
                # can edit and re-run without re-typing. Buffer mutations
                # have to run on the main thread (this callback is
                # already marshalled there via call_soon_threadsafe).
                if status_ref[0] == "ok":
                    try:
                        input_buffer.reset()
                    except Exception:
                        pass
                try:
                    app.invalidate()
                except Exception:
                    pass

            try:
                loop = getattr(app, "loop", None)
                if loop is not None:
                    loop.call_soon_threadsafe(_apply_post_cmd_state)
                else:
                    _apply_post_cmd_state()
            except Exception:
                _apply_post_cmd_state()

            # `usage` and `auth` are the two commands whose completion implies
            # the live toolbar values are stale — trigger an immediate refresh
            # rather than waiting for the next 30s tick.
            if cmd_name in ("usage", "auth"):
                _signal_refresh_from_thread()
            try:
                app.invalidate()
            except Exception:
                pass

        if cmd_name in _INTERACTIVE_COMMANDS:
            # tutorial / auth use click.prompt() and need raw terminal access.
            # Suspend the persistent prompt-toolkit app, run the command in
            # the bare terminal, then resume. Synchronous — we wait for it.
            is_input_locked[0] = True
            try:
                run_in_terminal(_run, in_executor=False)
            finally:
                _finish()
            return True

        # Network commands run in a worker thread so they don't fight
        # prompt_toolkit's asyncio loop. (scrape, google, etc. each call
        # `asyncio.run(...)` internally — and asyncio.run refuses to start
        # when a loop is already running, which is the case while
        # prompt_toolkit's Application is alive.) Locking the input
        # prevents the user from submitting a second command on top.
        is_input_locked[0] = True
        try:
            app.invalidate()
        except Exception:
            pass

        def _worker() -> None:
            try:
                _run()
            finally:
                # Always clear the worker reference first — the Ctrl+C handler
                # uses it to decide between "cancel command" and "exit REPL".
                # Stale references would make a quick second Ctrl+C target
                # a thread that's already finished.
                current_worker[0] = None
                # Cleanup MUST always run, even if _finish itself raises — a
                # broken finish would leave is_running=True and is_input_locked=True
                # forever, making the REPL unusable until restart.
                try:
                    _finish()
                except Exception:
                    state.is_running = False
                    state.running_command = None
                    state.running_command_text = None
                    state.run_start = None
                    is_input_locked[0] = False
                    try:
                        app.invalidate()
                    except Exception:
                        pass

        worker_thread = threading.Thread(target=_worker, daemon=True)
        current_worker[0] = worker_thread
        worker_thread.start()
        return True

    # ── Key bindings ────────────────────────────────────────────────────────
    _QUIT_TOKENS = {":q", ":quit", "exit", "quit", "q"}

    kb = KeyBindings()

    @kb.add("enter", filter=has_completions)
    def _accept(event):
        event.current_buffer.complete_state = None

    @kb.add("enter", filter=~has_completions)
    def _submit(event):
        text = input_buffer.text
        stripped = text.strip()
        if not stripped:
            # ``reset()`` clears the buffer AND the history-navigation
            # cursor (``working_index``). A plain set_document keeps the
            # cursor, so an Up press after an empty Enter would resume
            # whatever the user was previously browsing in history rather
            # than starting fresh from the most recent command.
            input_buffer.reset()
            return
        # First-run API key entry path — text in the buffer is the raw key
        # the user just pasted. Validate against /usage and, on success,
        # persist + transition to normal command mode in place.
        if _first_run_needs_key[0]:
            input_buffer.reset()
            _handle_first_run_key(stripped, text)
            return
        if stripped.lower() in _QUIT_TOKENS:
            input_buffer.reset()
            event.app.exit()
            return
        # Persist the submitted line into the FileHistory before we kick off
        # execution. ``append_string`` is the right call (not
        # ``store_string``): the latter only writes to disk, leaving the
        # in-memory ``_loaded_strings`` stale, so newly-submitted commands
        # don't show up on the next Up press until the REPL restarts and
        # reloads from disk. ``append_string`` does both.
        if history is not None:
            try:
                history.append_string(stripped)
            except Exception:
                pass
        # Don't clear the buffer here — we want the typed command to
        # stay visible if it fails or is cancelled (Ctrl+C), so the user
        # can edit and retry without re-typing. ``_finish`` clears it
        # only when the command succeeded. Shlex parse errors return
        # False from ``_execute`` and the text stays in place naturally.
        _execute(stripped)

    @kb.add("c-c")
    def _ctrl_c(event):
        # If a worker thread is running, Ctrl+C stops that command rather
        # than exiting the REPL. We try two mechanisms in parallel:
        #
        #   1. Cancel all tasks on the worker's asyncio loop via
        #      ``call_soon_threadsafe``. This wakes the selector
        #      immediately and raises ``CancelledError`` on the in-flight
        #      await (e.g. an aiohttp request blocked on socket recv).
        #      This is the only thing that produces a *fast* stop for
        #      network commands — without it, a long ScrapingBee request
        #      would hold the worker until it returns naturally.
        #
        #   2. Inject ``KeyboardInterrupt`` into the worker thread via
        #      ``PyThreadState_SetAsyncExc``. Fires at the next Python
        #      bytecode boundary; covers commands that aren't currently
        #      blocked in asyncio (sync post-processing, slow loops, ...).
        worker = current_worker[0]
        if state.is_running and worker is not None and worker.is_alive():
            loop = _active_worker_loop[0]
            if loop is not None:
                def _cancel_all_tasks() -> None:
                    try:
                        for task in _asyncio_mod.all_tasks(loop):
                            if not task.done():
                                task.cancel()
                    except Exception:
                        pass
                try:
                    loop.call_soon_threadsafe(_cancel_all_tasks)
                except Exception:
                    pass

            # If a ``!shell`` command is running, terminate the subprocess
            # directly — the worker thread is blocked in a C-level read()
            # on the child's stdout pipe, so a Python-level
            # KeyboardInterrupt won't fire until the read returns.
            # ``terminate()`` sends SIGTERM; closing the pipe also frees
            # the readline() loop.
            proc = current_subprocess[0]
            if proc is not None:
                try:
                    proc.terminate()
                except Exception:
                    pass

            import ctypes

            tid = worker.ident
            if tid is None:
                event.app.exit()
                return
            try:
                res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_ulong(tid), ctypes.py_object(KeyboardInterrupt)
                )
                # If we managed to flip exception state in more than one
                # thread, the docs say to undo it — otherwise we leave a
                # dangling pending exception on an unrelated thread.
                if res > 1:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        ctypes.c_ulong(tid), None
                    )
            except Exception:
                # ctypes path failed (PyPy? embedded?) — fall back to
                # exiting; daemon worker dies with the process.
                event.app.exit()
            return
        event.app.exit()

    @kb.add("c-d")
    def _ctrl_d(event):
        # Ctrl+D on empty input is "logout from shell" → exit. While a
        # command is running, ignore it to avoid yanking the REPL out from
        # under the user mid-scrape; they have :q or a second Ctrl+C.
        if state.is_running:
            return
        if not input_buffer.text:
            event.app.exit()

    # Right arrow / End accept the ghost-text suggestion. We're using
    # ``Application`` directly (not ``PromptSession``), so the default
    # ``load_auto_suggest_bindings`` are NOT in the merged binding set —
    # without these, the ghost text appears but no key consumes it.
    # (Ctrl-F is intentionally NOT bound — it would be redundant with Right
    # arrow and a small minority of users expect it to mean "find".)
    @Condition
    def _suggestion_at_eol() -> bool:
        try:
            buf = input_buffer
            return (
                buf.suggestion is not None
                and len(buf.suggestion.text) > 0
                and buf.document.is_cursor_at_the_end
            )
        except Exception:
            return False

    def _do_accept_suggestion(event):
        buf = event.current_buffer
        sug = buf.suggestion
        if sug:
            buf.insert_text(sug.text)

    kb.add("right", filter=_suggestion_at_eol, eager=True)(_do_accept_suggestion)
    kb.add("end", filter=_suggestion_at_eol, eager=True)(_do_accept_suggestion)
    kb.add(
        "tab",
        filter=~has_completions & _suggestion_at_eol,
        eager=True,
    )(_do_accept_suggestion)

    _not_first_run = Condition(lambda: not _first_run_needs_key[0])

    @kb.add("tab", filter=~has_completions & ~_suggestion_at_eol & _not_first_run)
    def _tab_open(event):
        # Tab opens the completion popup when no ghost suggestion is
        # visible. Shift+Tab is the mode toggle. Suppressed during the
        # first-run API key prompt — command-name completions are
        # irrelevant there.
        event.current_buffer.start_completion(select_first=False)

    @kb.add("tab", filter=has_completions)
    def _tab_next(event):
        event.current_buffer.complete_next()

    # Shift+Tab — when the completion popup is open, navigate backwards;
    # when it's not, toggle Scroll ↔ Select mouse mode.
    @kb.add("s-tab", filter=has_completions)
    def _shift_tab_in_completions(event):
        event.current_buffer.complete_previous()

    @kb.add("s-tab", filter=~has_completions)
    def _shift_tab_toggle_mode(event):
        _toggle_mouse_mode(event)

    @kb.add("escape", filter=has_completions, eager=True)
    def _esc(event):
        event.current_buffer.cancel_completion()

    # ── History navigation ─────────────────────────────────────────────────
    # Plain Up/Down navigate the FileHistory at ~/.config/scrapingbee-cli/
    # .history. When the completion menu is open these keys instead
    # navigate the menu (prompt_toolkit's default behaviour); the
    # ``~has_completions`` filter ensures we don't compete.
    @kb.add("up", filter=~has_completions)
    def _history_back(event):
        buf = event.current_buffer
        # prompt_toolkit loads history asynchronously via a background
        # task scheduled at first render. After our ``buffer.reset()`` on
        # submit, that task is cancelled and ``_working_lines`` is just
        # ``[""]`` — the next Up press lands before the task re-runs, so
        # ``history_backward`` has nothing to walk and is a no-op. Load
        # the history strings synchronously here as a fallback so the
        # first Up after a submit actually shows the newest entry.
        try:
            if len(buf._working_lines) <= 1:
                # ``get_strings()`` returns newest-first. prompt_toolkit's
                # built-in ``_load_history`` calls ``appendleft`` for each
                # yielded item in that order — newest gets pushed left
                # FIRST, ending up closest to the current-edit slot at the
                # right. Walking Up then visits newest before older. We
                # mirror that exact order here so the first Up after a
                # submit lands on the freshly-submitted command, not the
                # oldest entry on disk.
                strings = list(buf.history.get_strings())
                if strings:
                    for s in strings:
                        buf._working_lines.appendleft(s)
                    buf.working_index = len(buf._working_lines) - 1
            elif not buf.text and buf.working_index != len(buf._working_lines) - 1:
                # User has browsed back and erased to empty: jump the
                # cursor to the newest entry so this Up restarts there
                # instead of continuing from the previous browse point.
                buf.working_index = len(buf._working_lines) - 1
        except Exception:
            pass
        buf.history_backward()

    @kb.add("down", filter=~has_completions)
    def _history_forward(event):
        event.current_buffer.history_forward()

    # ── Scrollback navigation ──────────────────────────────────────────────
    # Keyboard-only scrolling of the virtual buffer. We don't enable mouse
    # capture (so native drag-select stays usable), so these keys are the
    # primary way to scroll history. Familiar to vim/less/htop users.
    #
    # ``eager=True`` is critical here: prompt_toolkit's Buffer has its own
    # default bindings for PgUp/PgDn (history navigation in some modes) and
    # the completion menu also consumes PgUp/PgDn when open. Eager bindings
    # fire BEFORE buffer-level handlers, so our scrollback scroll wins
    # whenever no completion popup is showing.
    @kb.add("pageup", eager=True, filter=~has_completions)
    def _sb_pageup(_e):
        scrollback.scroll_up(10)
        try:
            app.invalidate()
        except Exception:
            pass

    @kb.add("pagedown", eager=True, filter=~has_completions)
    def _sb_pagedown(_e):
        scrollback.scroll_down(10)
        try:
            app.invalidate()
        except Exception:
            pass

    @kb.add("c-up", eager=True)
    def _sb_lineup(_e):
        scrollback.scroll_up(1)
        try:
            app.invalidate()
        except Exception:
            pass

    @kb.add("c-down", eager=True)
    def _sb_linedown(_e):
        scrollback.scroll_down(1)
        try:
            app.invalidate()
        except Exception:
            pass

    @kb.add("c-home", eager=True)
    def _sb_top(_e):
        scrollback.scroll_to_top()
        try:
            app.invalidate()
        except Exception:
            pass

    @kb.add("c-end", eager=True)
    def _sb_bottom(_e):
        scrollback.scroll_to_bottom()
        try:
            app.invalidate()
        except Exception:
            pass

    # ── Mouse mode toggle (Alt+S = Esc S in terminal protocol) ─────────────
    # Flips between "scroll mode" (mouse_support on — wheel scrolls our
    # virtual buffer, drag-select needs per-terminal modifier like
    # Option/Shift) and "select mode" (mouse_support off — drag-select
    # works without any modifier on every terminal, wheel scrolling falls
    # back to PgUp/PgDn/Ctrl-arrows). Toolbar shows the active mode.
    @kb.add("escape", "s", eager=True)
    def _toggle_mouse_mode(_event):
        if state.mouse_mode == "scroll":
            state.mouse_mode = "select"
            try:
                app.output.disable_mouse_support()
                app.output.flush()
            except Exception:
                pass
        else:
            state.mouse_mode = "scroll"
            try:
                app.output.enable_mouse_support()
                app.output.flush()
            except Exception:
                pass
        try:
            app.invalidate()
        except Exception:
            pass

    # ── Application (full_screen=True: own the alt buffer cleanly) ─────────
    # Owning the alternate screen buffer eliminates the wrap-fragment /
    # orphan-toolbar artifacts we got with full_screen=False (where the
    # terminal could reflow content under us on resize).
    #
    # Mouse support is enabled so trackpad / wheel scroll events reach our
    # scrollback handler. prompt_toolkit uses mode 1000 — button events
    # only, NO motion tracking — so the terminal still owns drag-selection
    # (Mac Terminal / iTerm / kitty all keep native select with mode 1000;
    # on a few terminals users may need to hold Option/Shift while
    # dragging to bypass mouse capture).
    app = Application(
        layout=layout,
        key_bindings=kb,
        style=Style.from_dict(_style_dict_for(keep_bg)),
        full_screen=True,
        mouse_support=True,
    )
    # 50ms escape-sequence timeout (default 500ms). Snappy Esc for
    # cancel-completion etc. — modern terminals deliver escape sequences
    # as one read, so 50ms is plenty. Set on the instance because
    # ``ttimeoutlen`` isn't a constructor parameter.
    app.ttimeoutlen = 0.05

    # ── Periodic invalidate while a command is in flight ───────────────────
    # The shimmer on the running command line + the elapsed-time counter
    # need a tick ~10× per second to feel live. Without this, the live area
    # would only redraw on stdout writes (sparse for long-running scrapes).
    # When idle, 1Hz is enough — the "Next Update Xs" countdown only changes
    # once per second, and the paged toolbar carousel rotates on 5-second
    # boundaries.
    async def _ticker():
        import asyncio

        from .theme import has_progress_state, tick_progress_render

        idle_counter = 0
        # Track terminal width and trigger a fresh invalidate on resize.
        # No manual resize-detection needed any more — in full_screen
        # mode prompt_toolkit owns the entire screen, so SIGWINCH is
        # handled cleanly by the framework: the next render uses the
        # new size and the alt buffer has no scrollback-vs-logical-row
        # mismatch to worry about.

        while True:
            await asyncio.sleep(0.1)
            # Re-render the honeycomb progress widget while a batch is in
            # flight so the boundary hex shimmers between completion
            # events. ``tick_progress_render`` is a no-op when no batch
            # state is set, so the cost is negligible when idle.
            if has_progress_state():
                try:
                    tick_progress_render()
                except Exception:
                    pass
                try:
                    app.invalidate()
                except Exception:
                    pass
            if state.is_running:
                state.tick += 1
                try:
                    app.invalidate()
                except Exception:
                    pass
                idle_counter = 0
            else:
                idle_counter += 1
                if idle_counter >= 10:  # 1Hz idle redraw
                    idle_counter = 0
                    try:
                        app.invalidate()
                    except Exception:
                        pass

    # ── Background usage refresher ──────────────────────────────────────────
    # Polls the usage API on a 30s interval so the toolbar's "available",
    # "used (session)" and "conc" values stay roughly current. The user can
    # force an immediate refresh by signalling _refresh_event (used after the
    # `usage` and `auth` commands complete — see _execute). The first call
    # is fire-and-forget right after the task starts, so the toolbar
    # populates within a beat of REPL startup rather than after a 30s wait.
    import asyncio as _asyncio  # local alias avoids shadowing module-level usage

    _refresh_event = _asyncio.Event()

    async def _do_usage_refresh() -> None:
        import hashlib as _hashlib
        import json as _json

        from .batch import write_usage_file_cache
        from .client import Client, parse_usage
        from .config import BASE_URL, get_api_key

        try:
            key = get_api_key(None)
        except ValueError:
            return  # No key set yet — quietly skip; toolbar stays N/A.
        # Short non-reversible hash of the key — used to detect logout/relogin
        # with the *same* key vs a different one, so the session counter
        # continues for the former and resets for the latter.
        key_hash = _hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        try:
            async with Client(key, BASE_URL) as client:
                data, _hdrs, status_code = await client.usage(retries=1, backoff=1.0)
            if status_code != 200:
                return
            try:
                raw = _json.loads(data)
            except Exception:
                return
            state.update_from_usage_response(raw, key_hash=key_hash)
            try:
                write_usage_file_cache(key, parse_usage(data))
            except Exception:
                pass
            try:
                app.invalidate()
            except Exception:
                pass
        except Exception:
            # Network errors must not kill the refresher — just skip this
            # tick and try again on the next interval.
            return

    async def _usage_refresher() -> None:
        while True:
            if state.api_key_set:
                await _do_usage_refresh()
            try:
                await _asyncio.wait_for(
                    _refresh_event.wait(),
                    timeout=SessionState.USAGE_REFRESH_INTERVAL,
                )
                _refresh_event.clear()
            except _asyncio.TimeoutError:
                pass

    def _signal_refresh_from_thread() -> None:
        """Request an immediate usage refresh from a non-loop thread.

        ``asyncio.Event.set`` is not thread-safe, so we hop back onto the
        application's event loop. Used after the worker thread finishes
        ``usage`` (data just arrived) or ``auth`` (api_key may have just
        become set) so the toolbar updates without waiting for the next
        scheduled 30s tick.
        """
        try:
            loop = app.loop  # type: ignore[attr-defined]
            if loop is not None:
                loop.call_soon_threadsafe(_refresh_event.set)
        except Exception:
            pass

    # Track background tasks so we can cancel them cleanly on shutdown
    # instead of letting them run until the process exits (they would keep
    # firing app.invalidate() against a dead app and leak the asyncio loop
    # if the REPL is ever embedded in a larger program).
    _bg_tasks: list[Any] = []

    def _pre_run() -> None:
        _bg_tasks.append(app.create_background_task(_ticker()))
        _bg_tasks.append(app.create_background_task(_usage_refresher()))

    # ── Run inside patch_stdout so command output flows above the prompt ────
    def _restore_bg():
        if _set_black_bg:
            try:
                sys.stdout.write("\033]111\007")  # reset bg to user default
                sys.stdout.write("\033]110\007")  # reset fg to user default
                sys.stdout.flush()
            except Exception:
                pass

    # Pipe every stdout / stderr write into the virtual scrollback buffer.
    # The renderer (FormattedTextControl on the output Window) reads from
    # the buffer each frame. We don't touch the real terminal at all
    # while the app runs — that's the alt buffer's job, and it'll be
    # dismissed cleanly on exit.
    def _on_buffer_write() -> None:
        # Auto-follow: a write while user is at the bottom keeps them at
        # the bottom (scroll_offset stays 0). A user who's scrolled up
        # stays put — they explicitly asked to read history.
        try:
            app.invalidate()
        except Exception:
            pass

    sb_writer = ScrollbackWriter(scrollback, on_write=_on_buffer_write)
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout = sb_writer  # type: ignore[assignment]
    sys.stderr = sb_writer  # type: ignore[assignment]
    # Some callers (cli_utils.write_output) call ``sys.stdout.buffer.write(bytes)``.
    # Expose a binary-decoding adapter so those routes still land in our
    # scrollback as text. Truly binary output is decoded with errors=replace.
    if not hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer = _BinaryAdapter(sys.stdout)  # type: ignore[attr-defined]
    if not hasattr(sys.stderr, "buffer"):
        sys.stderr.buffer = _BinaryAdapter(sys.stderr)  # type: ignore[attr-defined]
    # err_console (rich.Console used by theme.py) caches a file= reference
    # at module import time — point it at our buffer too.
    _orig_err_console_file = err_console.file
    err_console.file = sb_writer  # type: ignore[assignment]
    try:
        app.run(pre_run=_pre_run)
    finally:
        # Cancel background tasks (ticker + usage refresher) so they stop
        # invalidating the now-dead app and release the loop they live on.
        for task in _bg_tasks:
            try:
                task.cancel()
            except Exception:
                pass
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        try:
            err_console.file = _orig_err_console_file
        except Exception:
            pass
        _restore_bg()
        set_repl_mode(False)
