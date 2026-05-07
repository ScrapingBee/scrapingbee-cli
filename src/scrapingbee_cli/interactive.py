"""Interactive REPL — Claude-style bordered input box with status toolbar.

Built on prompt_toolkit's `Application` API (not `PromptSession`) so we can
custom-layout the input area as a `Frame` with a chevron prompt mark, a
bottom-anchored toolbar showing live state (credits, last cmd, settings),
and a per-input syntax-highlighting lexer.

Output from each command flows above the input box; the box stays anchored
where the cursor was when the prompt opened.

Goals (revised; the previous version drifted from these):
- Bordered input box, anchored bottom of the prompt area.
- Restrained palette: yellow accent, soft amber chrome, dim greys, semantic
  green / red. No yellow-on-yellow, no mascot, no animation.
- Slash-prefixed REPL meta-commands (`:help`, `:q`, `:clear`, `:set`, ...).
- Per-command tab completion driven by walking the click tree.
- Toolbar with credits gauge, last status icon, `:set` chips, hint line.
- Inline syntax highlighting: command, flags, URLs, quoted strings.
- "Did you mean?" on typos. Multi-line input via trailing backslash.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
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
    # Lexer (input syntax highlighting)
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
    "auto-suggestion": "fg:#554400 italic",
}


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

    def __init__(self) -> None:
        self.last_command: str | None = None
        self.last_status: str | None = None     # "ok" | "fail"
        self.last_duration: float | None = None
        self.credits: int | None = None
        self.credits_total: int | None = None
        self.settings: dict[str, str] = {}

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
        try:
            import json
            from pathlib import Path

            cache = Path.home() / ".config" / "scrapingbee-cli" / "usage_cache.json"
            if not cache.exists():
                return
            data = json.loads(cache.read_text(encoding="utf-8"))
            entries = data.values() if isinstance(data, dict) else []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if isinstance(entry.get("credits"), int):
                    self.credits = entry["credits"]
                if isinstance(entry.get("max_api_credit"), int):
                    self.credits_total = entry["max_api_credit"]
                if self.credits is not None:
                    return
        except Exception:
            return


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
    """

    def render() -> list[tuple[str, str]]:
        import shutil

        width = shutil.get_terminal_size((80, 24)).columns
        segs: list[tuple[str, str]] = [("class:toolbar", "  ")]

        # --- Credits + gauge --------------------------------------------------
        segs.append(("class:toolbar.label", "credits "))
        if state.credits is not None:
            segs.append(("class:toolbar.value", _format_credits(state.credits)))
            if state.credits_total:
                used_pct = max(
                    0,
                    min(100, 100 - int(state.credits / state.credits_total * 100)),
                )
                segs.append(("class:toolbar", " "))
                segs.append(("class:toolbar.gauge", _credit_gauge(used_pct)))
        else:
            segs.append(("class:toolbar.value", "—"))

        # --- Last command -----------------------------------------------------
        if state.last_command:
            segs.append(("class:toolbar", "   ·   "))
            segs.append(("class:toolbar.label", "last "))
            segs.append(("class:toolbar.value", state.last_command))
            segs.append(("class:toolbar", " "))
            if state.last_status == "ok":
                segs.append(("class:toolbar.ok", "✓"))
            elif state.last_status == "fail":
                segs.append(("class:toolbar.fail", "✗"))
            if state.last_duration is not None:
                segs.append(("class:toolbar", f" {state.last_duration:.1f}s"))

        # --- Session setting chips (with overflow handling) -------------------
        if state.settings:
            # Estimate space already used + reserved for hint
            so_far = sum(len(text) for _, text in segs)
            hint_len = 24  # roughly "tab · ↑↓ · :help · :q" + spacing
            budget = max(0, width - so_far - hint_len - 4)

            chips = list(state.settings.items())
            shown = 0
            for k, v in chips:
                chip_text = f" {k}={v} "
                if budget < len(chip_text) + 2 and shown > 0:
                    break
                segs.append(("class:toolbar", "  "))
                segs.append(("class:toolbar.chip", chip_text))
                budget -= len(chip_text) + 2
                shown += 1
            remaining = len(chips) - shown
            if remaining > 0:
                segs.append(("class:toolbar", "  "))
                segs.append(("class:toolbar.hint", f"+{remaining} more"))

        # --- Hint (rightmost, but only if there's room) -----------------------
        used = sum(len(text) for _, text in segs)
        if width - used > 26:
            segs.append(("class:toolbar", " " * max(2, width - used - 24)))
            segs.append(("class:toolbar.hint", "tab · ↑↓ · :help · :q"))

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


def _print_banner(version: str) -> None:
    line = Text()
    line.append(" ScrapingBee ", style=f"bold black on {BEE_YELLOW}")
    line.append("  ")
    line.append(f"v{version}", style=f"bold {BEE_YELLOW}")
    line.append("  ")
    line.append("Type ", style=BEE_DIM)
    line.append(":help", style=f"bold {BEE_YELLOW}")
    line.append(" for commands", style=BEE_DIM)
    err_console.print()
    err_console.print(line)
    err_console.print()


def _print_help(commands: dict[str, str]) -> None:
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
    for group_name, cmds in groups.items():
        err_console.print(f"  [{BEE_DIM}]{group_name}[/]")
        for cmd in cmds:
            err_console.print(
                f"    [bold {BEE_YELLOW}]{cmd:<20}[/]  [dim]{commands.get(cmd, '')}[/]"
            )
    err_console.print()
    err_console.print(f"  [{BEE_DIM}]REPL[/]")
    for cmd, desc in [
        (":help, :?",   "Show this command list"),
        (":clear",      "Clear the screen"),
        (":view",       "Scroll through the last command's full output"),
        (":set K=V ...", "Set one or more session defaults"),
        (":unset K",    "Remove a session default ('all' or '*' clears every)"),
        (":reset",      "Clear every session default"),
        (":show",       "Show current session defaults"),
        (":q, :quit",   "Quit the REPL"),
    ]:
        err_console.print(f"    [bold {BEE_YELLOW}]{cmd:<20}[/]  [dim]{desc}[/]")
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
    `q` or `Esc` exits back to the REPL.
    """
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

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    line_count = text.count("\n") + 1

    buffer = Buffer(read_only=Condition(lambda: True))
    buffer.set_document(Document(text=text, cursor_position=0), bypass_readonly=True)

    text_window = Window(
        content=BufferControl(buffer=buffer),
        wrap_lines=False,
    )

    def _status_line():
        cursor_line = buffer.document.cursor_position_row + 1
        pct = int(cursor_line / max(1, line_count) * 100)
        return [
            ("class:pager.bar", "  "),
            ("class:pager.value", f"{cursor_line}/{line_count}"),
            ("class:pager.bar", f"  ({pct}%)  ·  "),
            ("class:pager.label", path),
            ("class:pager.bar", "    "),
            ("class:pager.hint", "↑↓ PgUp/PgDn Home/End scroll  ·  q / Esc to exit"),
        ]

    status_window = Window(
        content=FormattedTextControl(_status_line),
        height=D.exact(1),
    )

    layout = Layout(HSplit([text_window, status_window]))

    kb = KeyBindings()

    @kb.add("q")
    @kb.add("escape")
    @kb.add("c-c")
    def _exit(event):
        event.app.exit()

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

    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=True,
        mouse_support=True,
    )
    app.run()


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

        cache_path = Path.home() / ".cache" / "scrapingbee-cli" / "last-output"
        if not cache_path.exists():
            err_console.print(f"  [{BEE_DIM}]no recent output to view[/]")
            return "ok"
        try:
            _open_pager(str(cache_path))
        except Exception as e:
            err_console.print(f"  [bold {BEE_RED}]pager error:[/] {e}")
            err_console.print(
                f"  [{BEE_DIM}]full output saved at[/] "
                f"[bold {BEE_YELLOW}]{cache_path}[/]"
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
            flags_for_cmd = command_flags.get(cmd_name, [])
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
                for flag in flags_for_cmd:
                    if flag.startswith(last):
                        yield Completion(flag, start_position=-len(last))

    return BeeCompleter()


# ---------------------------------------------------------------------------
# Multi-line: trailing backslash continues the next line
# ---------------------------------------------------------------------------


def _prompt_once(state: SessionState, completer: Any, history_path: str) -> str | None:
    app, _buffer = _build_application(state, completer, history_path)
    return app.run()


def _read_input(state: SessionState, completer: Any, history_path: str) -> str | None:
    line = _prompt_once(state, completer, history_path)
    if line is None:
        return None
    while line.rstrip().endswith("\\"):
        more = _prompt_once(state, completer, history_path)
        if more is None:
            return line.rstrip().rstrip("\\").rstrip()
        line = line.rstrip().rstrip("\\").rstrip() + " " + more
    return line


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_repl(cli_group: Any, version: str) -> None:
    from pathlib import Path

    import click

    from .theme import set_repl_mode

    set_repl_mode(True)

    command_help, command_flags, bool_flags, choice_flags = _walk_click_tree(cli_group)
    command_names = sorted(command_flags.keys())

    _print_banner(version)

    state = SessionState()
    state.refresh_credits_from_cache()

    history_path = str(Path.home() / ".config" / "scrapingbee-cli" / ".history")
    Path(history_path).parent.mkdir(parents=True, exist_ok=True)

    completer = _make_completer(
        command_names, command_flags, bool_flags, choice_flags, command_help
    )

    # Flat set of every known flag across all commands — used by `:set` to
    # validate keys and surface "did you mean?" suggestions for typos.
    all_known_flags: set[str] = set()
    for flags_list in command_flags.values():
        all_known_flags.update(flags_list)

    while True:
        try:
            line = _read_input(state, completer, history_path)
        except (KeyboardInterrupt, EOFError):
            err_console.print()
            break

        if line is None:
            err_console.print()
            break

        line = line.strip()
        if not line:
            continue

        # The prompt area is erased on submit (erase_when_done=True), so echo
        # what the user typed into scrollback. Single line, ❯ + dim text —
        # cleaner and more resize-safe than the old `─── cmd ──` divider.
        echo = Text()
        echo.append("❯ ", style=f"bold {BEE_YELLOW}")
        echo.append(line, style="dim")
        err_console.print(echo)

        # Slash / bare meta-commands
        meta = _handle_meta(
            line, state, command_help, all_known_flags, bool_flags, choice_flags
        )
        if meta == "quit":
            break
        if meta == "ok":
            continue

        # Tolerate users typing `scrapingbee ...` out of muscle memory
        if line.lower().startswith("scrapingbee "):
            line = line[len("scrapingbee "):].strip()

        try:
            args = shlex.split(line)
        except ValueError as e:
            err_console.print(f"  [bold {BEE_RED}]parse error:[/] {e}")
            continue
        if not args:
            continue

        cmd_name = args[0]
        if cmd_name not in command_flags:
            suggestion = _suggest(cmd_name, command_names)
            if suggestion:
                err_console.print(
                    f"  [bold {BEE_RED}]unknown:[/] {cmd_name}   "
                    f"[{BEE_DIM}]did you mean[/] [bold {BEE_YELLOW}]{suggestion}[/][{BEE_DIM}]?[/]"
                )
            else:
                err_console.print(f"  [bold {BEE_RED}]unknown:[/] {cmd_name}")
            continue

        args = state.apply_settings_to_args(args)
        start = time.monotonic()
        status = "ok"

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
            status = "fail"
        except click.ClickException as e:
            e.show()
            status = "fail"
        except SystemExit as e:
            code = e.code if e.code is not None else 0
            if code not in (0, None):
                status = "fail"
        except Exception as e:
            err_console.print(f"  [bold {BEE_RED}]error:[/] {e}")
            status = "fail"

        duration = time.monotonic() - start
        _print_command_footer(status, duration)

        state.last_command = cmd_name
        state.last_status = status
        state.last_duration = duration
        state.refresh_credits_from_cache()
