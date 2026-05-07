"""Interactive REPL mode for ScrapingBee CLI."""

from __future__ import annotations

import shlex
import sys
import time

from rich.text import Text

from .theme import BEE_DIM, BEE_RED, BEE_YELLOW, err_console

# Secondary brand colour for accents (footer, dimmed elements)
_BEE_ORANGE = "#FFB13D"

# ---------------------------------------------------------------------------
# Splash animation
# ---------------------------------------------------------------------------

_SCRAPINGBEE_LOGO = [
    "  ███████╗ ██████╗██████╗  █████╗ ██████╗ ██╗███╗   ██╗ ██████╗ ",
    "  ██╔════╝██╔════╝██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║██╔════╝ ",
    "  ███████╗██║     ██████╔╝███████║██████╔╝██║██╔██╗ ██║██║  ███╗",
    "  ╚════██║██║     ██╔══██╗██╔══██║██╔═══╝ ██║██║╚██╗██║██║   ██║",
    "  ███████║╚██████╗██║  ██║██║  ██║██║     ██║██║ ╚████║╚██████╔╝",
    "  ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═══╝ ╚═════╝ ",
]

_BEE_LOGO = [
    "  ██████╗ ███████╗███████╗",
    "  ██╔══██╗██╔════╝██╔════╝",
    "  ██████╔╝█████╗  █████╗  ",
    "  ██╔══██╗██╔══╝  ██╔══╝  ",
    "  ██████╔╝███████╗███████╗",
    "  ╚═════╝ ╚══════╝╚══════╝",
]

_BEE_FRAMES = ["\\(o_o)/", "_(o_o)_", "/(o_o)\\", "_(o_o)_"]


def play_splash(version: str) -> None:
    """Bee accelerates across screen with bounce, then logo reveal."""
    if not sys.stderr.isatty():
        return

    import shutil

    width = shutil.get_terminal_size((80, 24)).columns
    max_pos = min(width - 12, 55)

    # Phase 1: Bee accelerates right (ease-in), then bounces back slightly
    total_steps = 40
    positions: list[int] = []
    for s in range(total_steps):
        # ease-in-out cubic: accelerate → decelerate
        t = s / (total_steps - 1)
        eased = t * t * (3 - 2 * t)  # smoothstep
        positions.append(int(eased * max_pos))
    # Add a small bounce at the end
    bounce_back = max(0, max_pos - 4)
    positions.extend([bounce_back, max_pos - 2, max_pos])

    for i, pos in enumerate(positions):
        bee = _BEE_FRAMES[i % len(_BEE_FRAMES)]
        # Fading honeycomb trail
        trail_len = min(pos, 25)
        trail = Text()
        trail.append(" " * (pos - trail_len))
        for t_i in range(trail_len):
            # Fade trail: older chars dimmer
            age = trail_len - t_i
            if age > 18:
                trail.append("·", style="dim")
            elif age > 10:
                trail.append("~", style=_BEE_ORANGE)
            else:
                trail.append("~", style=f"bold {BEE_YELLOW}")
        trail.append(bee, style=f"bold {BEE_YELLOW}")

        with err_console.capture() as cap:
            err_console.print(trail, end="")
        sys.stderr.write("\r\033[K" + cap.get())
        sys.stderr.flush()
        # Speed: fast start, slow near end
        delay = 0.012 + 0.015 * (i / len(positions))
        time.sleep(delay)

    sys.stderr.write("\r\033[K")
    sys.stderr.flush()
    time.sleep(0.12)

    # Phase 2: Logo appears line by line
    err_console.print()
    for logo_line in _SCRAPINGBEE_LOGO:
        err_console.print(f"[bold {BEE_YELLOW}]{logo_line}[/]")
        time.sleep(0.03)
    for logo_line in _BEE_LOGO:
        err_console.print(f"[bold white]{logo_line}[/]")
        time.sleep(0.03)

    err_console.print()
    ver = Text()
    ver.append(f"  v{version}", style=f"bold {BEE_YELLOW}")
    ver.append("  \u2502  ", style="dim")
    ver.append("Web scraping from the terminal", style="dim")
    err_console.print(ver)
    err_console.print()
    time.sleep(0.15)


# ---------------------------------------------------------------------------
# Command registry & help
# ---------------------------------------------------------------------------

_COMMANDS = [
    "scrape",
    "crawl",
    "google",
    "fast-search",
    "amazon-product",
    "amazon-search",
    "walmart-product",
    "walmart-search",
    "youtube-search",
    "youtube-metadata",
    "chatgpt",
    "tutorial",
    "auth",
    "logout",
    "usage",
    "schedule",
    "export",
    "docs",
    "unsafe",
]

_COMMAND_HELP: dict[str, str] = {
    "scrape": "Scrape a web page (single or batch)",
    "crawl": "Crawl a site following links",
    "google": "Google Search API",
    "fast-search": "Fast Search API (sub-second)",
    "amazon-product": "Amazon product details",
    "amazon-search": "Search Amazon products",
    "walmart-product": "Walmart product details",
    "walmart-search": "Search Walmart products",
    "youtube-search": "Search YouTube videos",
    "youtube-metadata": "YouTube video metadata",
    "chatgpt": "Query ChatGPT API",
    "tutorial": "Interactive tutorial walkthrough",
    "auth": "Save your API key",
    "logout": "Remove stored API key",
    "usage": "Check credits and concurrency",
    "schedule": "Schedule recurring scrapes",
    "export": "Merge batch output files",
    "docs": "Open ScrapingBee documentation",
    "unsafe": "Run an arbitrary scrapingbee URL",
    "help": "Show this command list",
    "clear": "Clear the screen",
    "exit": "Quit the REPL",
}

_COMMON_FLAGS = [
    "--verbose",
    "--output-file",
    "--retries",
    "--backoff",
    "--render-js",
    "--premium-proxy",
    "--stealth-proxy",
    "--country-code",
    "--return-page-markdown",
    "--return-page-text",
    "--extract-rules",
    "--ai-extract-rules",
    "--ai-query",
    "--input-file",
    "--output-dir",
    "--output-format",
    "--concurrency",
    "--screenshot",
    "--json-response",
    "--help",
]


def _print_repl_help() -> None:
    err_console.print()
    groups = {
        "Scraping": ["scrape", "crawl"],
        "Search": ["google", "fast-search"],
        "Marketplaces": [
            "amazon-product",
            "amazon-search",
            "walmart-product",
            "walmart-search",
        ],
        "Media": ["youtube-search", "youtube-metadata"],
        "AI": ["chatgpt"],
        "Learn": ["tutorial"],
        "Account": ["auth", "logout", "usage", "schedule", "export", "docs", "unsafe"],
    }
    for group_name, cmds in groups.items():
        err_console.print(f"  [{BEE_DIM}]{group_name}[/]")
        for cmd in cmds:
            err_console.print(
                f"    [bold {BEE_YELLOW}]{cmd:<20}[/]  [dim]{_COMMAND_HELP.get(cmd, '')}[/]"
            )
    err_console.print()
    err_console.print(f"  [{BEE_DIM}]Session[/]")
    for cmd in ("help", "clear", "exit"):
        err_console.print(
            f"    [bold {BEE_YELLOW}]{cmd:<20}[/]  [dim]{_COMMAND_HELP.get(cmd, '')}[/]"
        )
    err_console.print()


# ---------------------------------------------------------------------------
# prompt_toolkit setup  (ScrapingBee brand theme)
# ---------------------------------------------------------------------------

_STYLE_DICT = {
    # Prompt: powerline arrow tag
    "prompt.tag": "bg:#FFCD23 #000000 bold",
    "prompt.arrow": "#FFCD23 bold",
    "prompt.space": "",
    # Completion dropdown
    "completion-menu": "bg:#1a1400",
    "completion-menu.completion": "bg:#1a1400 #FFCD23",
    "completion-menu.completion.current": "bg:#FFCD23 #000000 bold",
    "completion-menu.meta.completion": "bg:#1a1400 #886600",
    "completion-menu.meta.completion.current": "bg:#FFCD23 #000000",
    "scrollbar.background": "bg:#1a1400",
    "scrollbar.button": "bg:#FFCD23",
    # Ghost text
    "auto-suggestion": "fg:#554400 italic",
    # Hint line (above prompt)
    "prompt.hint": "#665500 italic",
}

def _build_static_prompt() -> list[tuple[str, str]]:
    """Build the prompt segments.

    Default: a single unified yellow tag \u2014 ` ScrapingBee \u276f ` \u2014 with the
    chevron rendered *inside* the tag. Identical in every terminal/font:
    no protruding shape, no Private Use Area glyphs.

    Set SCRAPINGBEE_POWERLINE=1 to use the classic Powerline arrow that
    *protrudes* from the tag (requires a patched font like a Nerd Font).
    """
    import os

    hint = (
        "class:prompt.hint",
        "  Tab complete  \u2502  \u2191\u2193 history  \u2502  \u2192 accept  \u2502  Ctrl+C exit\n",
    )
    blank = ("", "\n")
    space = ("class:prompt.space", " ")

    if os.environ.get("SCRAPINGBEE_POWERLINE", "").lower() in ("1", "true", "yes"):
        return [
            hint,
            blank,
            ("class:prompt.tag", " ScrapingBee "),
            ("class:prompt.arrow", "\ue0b0"),
            space,
        ]

    return [
        hint,
        blank,
        ("class:prompt.tag", " ScrapingBee \u276f "),
        space,
    ]


# ---------------------------------------------------------------------------
# Flag value completions
# ---------------------------------------------------------------------------

_BOOL_FLAGS = frozenset(
    {
        "--render-js",
        "--block-ads",
        "--block-resources",
        "--premium-proxy",
        "--stealth-proxy",
        "--forward-headers",
        "--forward-headers-pure",
        "--json-response",
        "--screenshot",
        "--screenshot-full-page",
        "--return-page-source",
        "--return-page-markdown",
        "--return-page-text",
        "--custom-google",
        "--transparent-status-code",
        "--add-html",
        "--light-request",
        "--deduplicate",
        "--resume",
        "--autothrottle",
    }
)

_CHOICE_FLAGS: dict[str, list[str]] = {
    "--device": ["desktop", "mobile"],
    "--output-format": ["files", "csv", "ndjson"],
    "--method": ["GET", "POST", "PUT"],
    "--wait-browser": ["domcontentloaded", "load", "networkidle0", "networkidle2"],
    "--sort-by": ["best-match", "price-low", "price-high", "best-seller", "most-recent"],
    "--search-type": ["web", "images", "news", "videos", "shopping"],
    "--type": ["video", "channel", "playlist", "movie"],
    "--duration": ["short", "medium", "long"],
    "--upload-date": ["today", "last-hour", "this-week", "this-month", "this-year"],
    "--preset": [
        "screenshot",
        "screenshot-and-html",
        "fetch",
        "extract-links",
        "extract-emails",
        "extract-phones",
        "scroll-page",
    ],
}


def _make_completer():
    from prompt_toolkit.completion import Completer, Completion

    class BeeCompleter(Completer):
        def get_completions(self, document, complete_event):
            stripped = document.text_before_cursor.lstrip()
            words = stripped.split()

            on_first_word = (not stripped) or (len(words) == 1 and not stripped.endswith(" "))
            if on_first_word:
                partial = words[0].lower() if words else ""
                for cmd in sorted(_COMMANDS + ["help", "clear", "exit"]):
                    if cmd.startswith(partial):
                        yield Completion(
                            cmd,
                            start_position=-len(partial),
                            display_meta=_COMMAND_HELP.get(cmd, ""),
                        )
                return

            last = words[-1] if words else ""
            prev = words[-2] if len(words) >= 2 else ""

            if stripped.endswith(" ") and prev in _BOOL_FLAGS:
                yield Completion("true", display_meta="enable")
                yield Completion("false", display_meta="disable")
                return
            if stripped.endswith(" ") and prev in _CHOICE_FLAGS:
                for val in _CHOICE_FLAGS[prev]:
                    yield Completion(val)
                return
            if len(words) >= 2 and not last.startswith("-"):
                flag = words[-2]
                if flag in _BOOL_FLAGS:
                    for val in ("true", "false"):
                        if val.startswith(last.lower()):
                            yield Completion(val, start_position=-len(last))
                    return
                if flag in _CHOICE_FLAGS:
                    for val in _CHOICE_FLAGS[flag]:
                        if val.startswith(last.lower()):
                            yield Completion(val, start_position=-len(last))
                    return
            if last.startswith("-"):
                for flag in _COMMON_FLAGS:
                    if flag.startswith(last):
                        yield Completion(flag, start_position=-len(last))

    return BeeCompleter()


def _make_key_bindings():
    from prompt_toolkit.filters import has_completions
    from prompt_toolkit.key_binding import KeyBindings

    kb = KeyBindings()

    @kb.add("enter", filter=has_completions)
    def _accept_completion(event):
        """Enter with completion menu: keep current selection, close menu."""
        # prompt_toolkit already applies the selected completion as a preview
        # in the buffer during navigation. Just dismiss the menu.
        event.current_buffer.complete_state = None

    @kb.add("enter", filter=~has_completions)
    def _submit_or_ignore(event):
        """Enter without completion menu: submit if non-empty, else do nothing."""
        buf = event.current_buffer
        if buf.text.strip():
            buf.validate_and_handle()
        # Empty buffer: do nothing — cursor stays, no duplicate prompt

    return kb


def _build_session(history_path: str):
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
        completer=_make_completer(),
        complete_while_typing=False,
        auto_suggest=AutoSuggestFromHistory(),
        style=Style.from_dict(_STYLE_DICT),
        key_bindings=_make_key_bindings(),
        mouse_support=False,
        enable_history_search=False,
        vi_mode=False,
    )


# ---------------------------------------------------------------------------
# REPL main loop
# ---------------------------------------------------------------------------


def run_repl(cli_group: object, version: str) -> None:
    from pathlib import Path

    import click

    from .theme import set_repl_mode

    set_repl_mode(True)

    play_splash(version)
    _print_repl_help()

    history_path = str(Path.home() / ".config" / "scrapingbee-cli" / ".history")
    Path(history_path).parent.mkdir(parents=True, exist_ok=True)

    session = _build_session(history_path)
    static_prompt = _build_static_prompt()

    while True:
        try:
            line = session.prompt(static_prompt).strip()
        except KeyboardInterrupt:
            err_console.print()
            err_console.print(f"  [bold {BEE_YELLOW}]Buzz off! See you next time.[/]")
            break
        except EOFError:
            continue

        if not line:
            continue

        lower = line.lower()
        if lower in ("exit", "quit", "q"):
            err_console.print(f"  [bold {BEE_YELLOW}]Buzz off! See you next time.[/]")
            break

        if lower in ("help", "?"):
            _print_repl_help()
            continue

        if lower == "clear":
            import shutil

            rows = shutil.get_terminal_size((80, 24)).lines
            # Print enough blank lines to scroll old content off screen,
            # then move cursor up a few rows so prompt lands near the bottom
            # (where the toolbar is) rather than stuck at the very top.
            sys.stderr.write("\n" * rows)
            sys.stderr.write(f"\033[{rows}A\033[J")
            sys.stderr.flush()
            continue

        if lower.startswith("scrapingbee "):
            line = line[len("scrapingbee ") :].strip()

        try:
            args = shlex.split(line)
        except ValueError as e:
            err_console.print(f"  [bold {BEE_RED}]Parse error: {e}[/]")
            continue

        if not args:
            continue

        # Gap between prompt and command output
        sys.stderr.write("\n")

        # No outer spinner: commands that benefit show their own MiniBeeSpinner
        # via is_repl_mode() (network calls). An outer spinner here would also
        # block interactive commands like `tutorial` / `auth` from prompting.
        try:
            cli_group.main(args, standalone_mode=False)  # type: ignore[union-attr]
        except click.ClickException as e:
            e.show()
        except SystemExit:
            pass
        except Exception as e:
            err_console.print(f"  [bold {BEE_RED}]Error: {e}[/]")
