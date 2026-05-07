"""Interactive REPL mode for ScrapingBee CLI.

Goals — explicit on purpose, since the previous version drifted from these:
- Get out of the user's way: no splash, no logos, no animation.
- One-line banner. Single unified prompt tag.
- Output frame uniform across every command.
- Slash-prefixed REPL meta-commands so they don't collide with click.
- Per-command tab completion driven by the click tree (no flag duplication).
- Bottom toolbar with live state (credits, last status, duration).
- "Did you mean?" on typos. Multi-line input via trailing backslash.
- Session settings via `:set KEY=VAL` and `:show`.
"""

from __future__ import annotations

import os
import shlex
import sys
import time
from typing import TYPE_CHECKING, Any, Iterable

from rich.text import Text

from .theme import BEE_DIM, BEE_RED, BEE_YELLOW, err_console

if TYPE_CHECKING:
    import click


# ---------------------------------------------------------------------------
# Banner & first-launch hint
# ---------------------------------------------------------------------------


def _print_banner(version: str) -> None:
    """One-line banner. No animation, no logo, no nonsense."""
    line = Text()
    line.append(" ScrapingBee ", style=f"bold black on {BEE_YELLOW}")
    line.append("  ")
    line.append(f"v{version}", style=f"bold {BEE_YELLOW}")
    line.append("  ")
    line.append("Type ", style=BEE_DIM)
    line.append(":help", style=f"bold {BEE_YELLOW}")
    line.append(" for commands, ", style=BEE_DIM)
    line.append(":q", style=f"bold {BEE_YELLOW}")
    line.append(" to quit.", style=BEE_DIM)
    err_console.print()
    err_console.print(line)
    err_console.print()


def _print_help(commands: dict[str, str]) -> None:
    """Print the command list, grouped, plus the slash-command meta list."""
    err_console.print()
    groups: dict[str, list[str]] = {
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
            help_text = commands.get(cmd, "")
            err_console.print(
                f"    [bold {BEE_YELLOW}]{cmd:<20}[/]  [dim]{help_text}[/]"
            )

    err_console.print()
    err_console.print(f"  [{BEE_DIM}]REPL[/]")
    meta_cmds = [
        (":help, :?", "Show this command list"),
        (":clear",    "Clear the screen"),
        (":set K=V",  "Set a session default (e.g. :set country-code=fr)"),
        (":unset K",  "Remove a session default"),
        (":show",     "Show current session defaults"),
        (":q, :quit", "Quit the REPL"),
    ]
    for cmd, desc in meta_cmds:
        err_console.print(
            f"    [bold {BEE_YELLOW}]{cmd:<20}[/]  [dim]{desc}[/]"
        )
    err_console.print()


# ---------------------------------------------------------------------------
# Click tree introspection (per-command flags / values)
# ---------------------------------------------------------------------------


def _walk_click_tree(cli_group: Any) -> tuple[
    dict[str, str],            # command -> short help
    dict[str, list[str]],      # command -> [flag, ...]
    set[str],                  # bool flags (any command)
    dict[str, list[str]],      # flag -> [choice, ...]
]:
    """Inspect the click group and return discovery data for completion + help.

    Returns (command_help, command_flags, bool_flags, choice_flags).
    """
    import click

    command_help: dict[str, str] = {}
    command_flags: dict[str, list[str]] = {}
    bool_flags: set[str] = set()
    choice_flags: dict[str, list[str]] = {}

    for name, cmd in cli_group.commands.items():
        command_help[name] = (cmd.short_help or cmd.help or "").strip().splitlines()[0:1] and \
            (cmd.short_help or cmd.help or "").strip().splitlines()[0] or ""

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
# Prompt segment builder
# ---------------------------------------------------------------------------


_STYLE_DICT = {
    # Prompt: yellow tag with chevron inside (or Powerline arrow if opted in)
    "prompt.tag":   f"bg:{BEE_YELLOW} #000000 bold",
    "prompt.arrow": f"{BEE_YELLOW} bold",
    "prompt.cont":  f"{BEE_DIM}",
    "prompt.space": "",
    # Completion dropdown
    "completion-menu":                   "bg:#1a1400",
    "completion-menu.completion":        f"bg:#1a1400 {BEE_YELLOW}",
    "completion-menu.completion.current": f"bg:{BEE_YELLOW} #000000 bold",
    "completion-menu.meta.completion":         "bg:#1a1400 #886600",
    "completion-menu.meta.completion.current": f"bg:{BEE_YELLOW} #000000",
    "scrollbar.background":              "bg:#1a1400",
    "scrollbar.button":                  f"bg:{BEE_YELLOW}",
    # Ghost text
    "auto-suggestion": f"fg:#554400 italic",
    # Bottom toolbar
    "bottom-toolbar":          f"bg:#1a1400 {BEE_DIM}",
    "bottom-toolbar.label":    f"bg:#1a1400 {BEE_DIM}",
    "bottom-toolbar.value":    f"bg:#1a1400 {BEE_YELLOW} bold",
    "bottom-toolbar.ok":       f"bg:#1a1400 #22C55E bold",
    "bottom-toolbar.fail":     f"bg:#1a1400 {BEE_RED} bold",
}


def _powerline_mode() -> bool:
    return os.environ.get("SCRAPINGBEE_POWERLINE", "").lower() in ("1", "true", "yes")


def _build_main_prompt() -> list[tuple[str, str]]:
    """Primary prompt segments. No hint line — that's only on startup."""
    if _powerline_mode():
        return [
            ("class:prompt.tag",   " ScrapingBee "),
            ("class:prompt.arrow", ""),
            ("class:prompt.space", " "),
        ]
    return [
        ("class:prompt.tag",   " ScrapingBee ❯ "),
        ("class:prompt.space", " "),
    ]


def _build_continuation_prompt() -> list[tuple[str, str]]:
    """Continuation prompt for multi-line input (after a trailing `\\`)."""
    return [("class:prompt.cont", "         … ")]


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


class SessionState:
    """REPL-wide mutable state.

    Holds the bottom-toolbar inputs and `:set` defaults. Settings keys are
    stored without the `--` prefix and applied as `--key value` if the
    user's command doesn't already include that flag.
    """

    def __init__(self) -> None:
        self.last_status: str | None = None    # "ok" | "fail" | None
        self.last_duration: float | None = None
        self.last_command: str | None = None
        self.credits: int | None = None
        self.settings: dict[str, str] = {}

    def apply_settings_to_args(self, args: list[str]) -> list[str]:
        """Inject session defaults as flags, unless the user passed them already."""
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
        """Read cached usage from disk if available — non-blocking, best-effort."""
        try:
            import json
            from pathlib import Path

            cache = Path.home() / ".config" / "scrapingbee-cli" / "usage_cache.json"
            if not cache.exists():
                return
            data = json.loads(cache.read_text(encoding="utf-8"))
            for entry in data.values() if isinstance(data, dict) else []:
                creds = entry.get("credits") if isinstance(entry, dict) else None
                if isinstance(creds, int):
                    self.credits = creds
                    return
        except Exception:
            return


# ---------------------------------------------------------------------------
# prompt_toolkit machinery
# ---------------------------------------------------------------------------


def _make_completer(
    commands: list[str],
    command_flags: dict[str, list[str]],
    bool_flags: set[str],
    choice_flags: dict[str, list[str]],
    command_help: dict[str, str],
):
    """Per-command tab completion driven by the click tree."""
    from prompt_toolkit.completion import Completer, Completion

    meta_cmds = [":help", ":?", ":clear", ":set", ":unset", ":show", ":q", ":quit"]

    class BeeCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor.lstrip()
            words = text.split()
            on_first = (not text) or (len(words) == 1 and not text.endswith(" "))

            # First word: command names + slash-commands
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

            # Inside a command: use that command's flags
            cmd_name = words[0]
            flags_for_cmd = command_flags.get(cmd_name, [])
            last = words[-1] if words else ""
            prev = words[-2] if len(words) >= 2 else ""

            # After a bool flag with trailing space: suggest true/false
            if text.endswith(" ") and prev in bool_flags:
                yield Completion("true",  display_meta="enable")
                yield Completion("false", display_meta="disable")
                return
            # After a choice flag with trailing space: suggest choices
            if text.endswith(" ") and prev in choice_flags:
                for v in choice_flags[prev]:
                    yield Completion(v)
                return
            # Mid-typing a value for a known flag (no trailing space)
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
            # Typing a flag
            if last.startswith("-"):
                for flag in flags_for_cmd:
                    if flag.startswith(last):
                        yield Completion(flag, start_position=-len(last))

    return BeeCompleter()


def _make_key_bindings():
    from prompt_toolkit.filters import has_completions
    from prompt_toolkit.key_binding import KeyBindings

    kb = KeyBindings()

    @kb.add("enter", filter=has_completions)
    def _accept_completion(event):
        event.current_buffer.complete_state = None

    @kb.add("enter", filter=~has_completions)
    def _submit_or_ignore(event):
        buf = event.current_buffer
        if buf.text.strip():
            buf.validate_and_handle()

    return kb


def _build_session(history_path: str, completer: Any, toolbar_fn: Any):
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style

    try:
        history = FileHistory(history_path)
    except Exception:
        history = None  # type: ignore[assignment]

    return PromptSession(
        history=history,
        completer=completer,
        complete_while_typing=False,
        auto_suggest=AutoSuggestFromHistory(),
        style=Style.from_dict(_STYLE_DICT),
        key_bindings=_make_key_bindings(),
        bottom_toolbar=toolbar_fn,
        mouse_support=False,
        enable_history_search=False,
        vi_mode=False,
    )


# ---------------------------------------------------------------------------
# Bottom toolbar
# ---------------------------------------------------------------------------


def _build_toolbar_fn(state: SessionState) -> Any:
    """Return a callable producing the bottom toolbar segments."""

    def render() -> list[tuple[str, str]]:
        segs: list[tuple[str, str]] = [("class:bottom-toolbar", " ")]

        # Credits (from cache)
        if state.credits is not None:
            segs.append(("class:bottom-toolbar.label", "credits "))
            segs.append(("class:bottom-toolbar.value", f"{state.credits:,}"))
        else:
            segs.append(("class:bottom-toolbar.label", "credits "))
            segs.append(("class:bottom-toolbar.value", "—"))

        segs.append(("class:bottom-toolbar", "   "))

        # Last command status
        if state.last_command:
            segs.append(("class:bottom-toolbar.label", "last "))
            segs.append(("class:bottom-toolbar.value", state.last_command))
            if state.last_status == "ok":
                segs.append(("class:bottom-toolbar", " "))
                segs.append(("class:bottom-toolbar.ok", "OK"))
            elif state.last_status == "fail":
                segs.append(("class:bottom-toolbar", " "))
                segs.append(("class:bottom-toolbar.fail", "FAIL"))
            if state.last_duration is not None:
                segs.append(
                    ("class:bottom-toolbar", f"  ({state.last_duration:.1f}s)")
                )
        else:
            segs.append(("class:bottom-toolbar", "no commands run yet"))

        # Active session settings
        if state.settings:
            segs.append(("class:bottom-toolbar", "   "))
            segs.append(("class:bottom-toolbar.label", "set "))
            joined = " ".join(f"{k}={v}" for k, v in state.settings.items())
            segs.append(("class:bottom-toolbar.value", joined))

        return segs

    return render


# ---------------------------------------------------------------------------
# Output frame: uniform divider above + status line below
# ---------------------------------------------------------------------------


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


def _print_command_footer(status: str, duration_s: float) -> None:
    line = Text()
    line.append("  ")
    if status == "ok":
        line.append("[ok]", style="bold #22C55E")
    elif status == "fail":
        line.append("[fail]", style=f"bold {BEE_RED}")
    else:
        line.append(f"[{status}]", style=BEE_DIM)
    line.append(f"  {duration_s:.2f}s", style=BEE_DIM)
    err_console.print(line)
    err_console.print()


# ---------------------------------------------------------------------------
# Slash-command meta dispatcher
# ---------------------------------------------------------------------------


def _handle_meta(line: str, state: SessionState, command_help: dict[str, str]) -> str | None:
    """Handle :slash commands (and their bare aliases). Returns:

    - "quit"  → break out of the REPL loop
    - "ok"    → handled, continue to next prompt
    - None    → not a meta-command, fall through to click
    """
    parts = line.strip().split(None, 1)
    head = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    head_low = head.lower()

    quit_aliases  = {":q", ":quit", "exit", "quit", "q"}
    help_aliases  = {":help", ":?", "help", "?"}
    clear_aliases = {":clear", "clear"}

    if head_low in quit_aliases:
        return "quit"

    if head_low in help_aliases:
        _print_help(command_help)
        return "ok"

    if head_low in clear_aliases:
        sys.stderr.write("\033[2J\033[H")
        sys.stderr.flush()
        return "ok"

    if head_low == ":show":
        if not state.settings:
            err_console.print(f"  [{BEE_DIM}]No session defaults set.[/]")
        else:
            err_console.print()
            for k, v in state.settings.items():
                err_console.print(f"  [bold {BEE_YELLOW}]{k:<20}[/]  [dim]{v}[/]")
            err_console.print()
        return "ok"

    if head_low == ":unset":
        key = rest.strip().lstrip("-")
        if not key:
            err_console.print(f"  [bold {BEE_RED}]usage:[/] :unset KEY")
            return "ok"
        if key in state.settings:
            del state.settings[key]
            err_console.print(f"  [{BEE_DIM}]unset[/] [bold {BEE_YELLOW}]{key}[/]")
        else:
            err_console.print(f"  [{BEE_DIM}]not set:[/] {key}")
        return "ok"

    if head_low == ":set":
        if "=" not in rest:
            err_console.print(f"  [bold {BEE_RED}]usage:[/] :set KEY=VALUE")
            return "ok"
        key, _, value = rest.partition("=")
        key = key.strip().lstrip("-")
        value = value.strip()
        if not key or not value:
            err_console.print(f"  [bold {BEE_RED}]usage:[/] :set KEY=VALUE")
            return "ok"
        state.settings[key] = value
        err_console.print(f"  [{BEE_DIM}]set[/] [bold {BEE_YELLOW}]{key}[/] = [dim]{value}[/]")
        return "ok"

    return None


# ---------------------------------------------------------------------------
# Did-you-mean
# ---------------------------------------------------------------------------


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
# Multi-line input via trailing `\`
# ---------------------------------------------------------------------------


def _read_input(session: Any, main_prompt: list, cont_prompt: list) -> str:
    """Read a (possibly multi-line) command. Trailing `\\` joins the next line."""
    line = session.prompt(main_prompt).rstrip()
    while line.endswith("\\"):
        more = session.prompt(cont_prompt).rstrip()
        line = line[:-1].rstrip() + " " + more
    return line


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_repl(cli_group: Any, version: str) -> None:
    from pathlib import Path

    import click

    from .theme import set_repl_mode

    set_repl_mode(True)

    # Click introspection
    command_help, command_flags, bool_flags, choice_flags = _walk_click_tree(cli_group)
    command_names = sorted(command_flags.keys())

    # Banner — once
    _print_banner(version)

    # Session state + prompt session
    state = SessionState()
    state.refresh_credits_from_cache()

    history_path = str(Path.home() / ".config" / "scrapingbee-cli" / ".history")
    Path(history_path).parent.mkdir(parents=True, exist_ok=True)

    completer = _make_completer(
        command_names, command_flags, bool_flags, choice_flags, command_help
    )
    toolbar = _build_toolbar_fn(state)
    session = _build_session(history_path, completer, toolbar)

    main_prompt = _build_main_prompt()
    cont_prompt = _build_continuation_prompt()

    while True:
        try:
            line = _read_input(session, main_prompt, cont_prompt).strip()
        except KeyboardInterrupt:
            err_console.print()
            break
        except EOFError:
            err_console.print()
            break

        if not line:
            continue

        # Meta-commands (`:help`, `:set`, `clear`, `exit`, etc.)
        meta = _handle_meta(line, state, command_help)
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

        # Unknown command + suggestion (fast path before click runs)
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

        # Apply session defaults
        args = state.apply_settings_to_args(args)

        # Output frame: divider above
        _print_command_header(args)
        start = time.monotonic()
        status = "ok"

        try:
            cli_group.main(args, standalone_mode=False)
        except click.UsageError as e:
            # Click usage error: try to suggest a flag if message is "no such option"
            msg = str(e)
            err_console.print(f"  [bold {BEE_RED}]usage:[/] {msg}")
            if "no such option" in msg.lower():
                # Extract the bad flag and suggest
                import re as _re
                m = _re.search(r"--?[A-Za-z0-9-]+", msg)
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

        # Update session state for the toolbar
        state.last_command = cmd_name
        state.last_status = status
        state.last_duration = duration
        state.refresh_credits_from_cache()
