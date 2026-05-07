"""ScrapingBee CLI theme: colors, styled output, and flapping-bee spinner.

The spinner shows a single-line coloured bee with flapping wings and rotating
fun status messages tailored to each command.
"""

from __future__ import annotations

import os
import sys
import threading

from rich.console import Console
from rich.text import Text
from rich.theme import Theme

# -- ScrapingBee brand colours -----------------------------------------------

BEE_YELLOW = "#FFCD23"
BEE_DARK = "#0F0F0E"
BEE_WHITE = "#FFFFFF"
BEE_AMBER = "#E5A800"
BEE_GREEN = "#22C55E"
BEE_RED = "#EF4444"
BEE_DIM = "#888888"

SCRAPINGBEE_THEME = Theme(
    {
        "bee": f"bold {BEE_YELLOW}",
        "bee.dim": BEE_AMBER,
        "info": f"bold {BEE_YELLOW}",
        "success": f"bold {BEE_GREEN}",
        "error": f"bold {BEE_RED}",
        "warn": f"bold {BEE_AMBER}",
        "dim": BEE_DIM,
        "header": f"bold {BEE_WHITE}",
        "key": f"bold {BEE_YELLOW}",
        "value": BEE_WHITE,
    }
)


def _want_color() -> bool | None:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return None


_color = _want_color()

err_console = Console(stderr=True, theme=SCRAPINGBEE_THEME, highlight=False, force_terminal=_color)
console = Console(theme=SCRAPINGBEE_THEME, highlight=False, force_terminal=_color)

# -- REPL mode flag -----------------------------------------------------------
# When True, fancy visuals (panels, honeycomb, personality errors, styled help)
# are enabled.  Direct CLI commands (scrapingbee scrape ...) keep plain output.

_repl_mode = False


def set_repl_mode(enabled: bool = True) -> None:
    """Enable or disable REPL-mode visuals."""
    global _repl_mode  # noqa: PLW0603
    _repl_mode = enabled


def is_repl_mode() -> bool:
    """Return True when running inside the interactive REPL."""
    return _repl_mode


# -- Single-line bee frames --------------------------------------------------

# Each frame is a tuple of (segment, style) pairs rendered inline.
# The bee body is yellow, wings are white, and they alternate to create a flap.
_BEE_INLINE_FRAMES: list[list[tuple[str, str]]] = [
    [
        ("\\", "bold white"),
        ("(", "dim"),
        ("◉", f"bold {BEE_YELLOW}"),
        ("ω", "dim"),
        ("◉", f"bold {BEE_YELLOW}"),
        (")", "dim"),
        ("/", "bold white"),
    ],
    [
        ("᎑", "bold white"),
        ("(", "dim"),
        ("◉", f"bold {BEE_YELLOW}"),
        ("ω", "dim"),
        ("◉", f"bold {BEE_YELLOW}"),
        (")", "dim"),
        ("᎑", "bold white"),
    ],
    [
        ("/", "bold white"),
        ("(", "dim"),
        ("◉", f"bold {BEE_YELLOW}"),
        ("ω", "dim"),
        ("◉", f"bold {BEE_YELLOW}"),
        (")", "dim"),
        ("\\", "bold white"),
    ],
    [
        ("᎑", "bold white"),
        ("(", "dim"),
        ("◉", f"bold {BEE_YELLOW}"),
        ("ω", "dim"),
        ("◉", f"bold {BEE_YELLOW}"),
        (")", "dim"),
        ("᎑", "bold white"),
    ],
]


def _render_inline_bee(frame_idx: int) -> Text:
    """Return a single-line bee Text for the given frame."""
    parts = _BEE_INLINE_FRAMES[frame_idx % len(_BEE_INLINE_FRAMES)]
    text = Text()
    for content, style in parts:
        text.append(content, style=style)
    return text


# -- Contextual status messages per command ----------------------------------

_BEE_FACTS = [
    "Did you know? Bees can fly up to 15 mph",
    "Did you know? A bee visits 50-100 flowers per trip",
    "Did you know? Bees have 5 eyes",
    "Did you know? Honey never spoils",
    "Did you know? Bees communicate by dancing",
    "Did you know? A hive can have 60,000 bees",
    "Did you know? Bees flap 200 times per second",
    "Did you know? Bees can recognize human faces",
    "Did you know? One bee makes 1/12 tsp of honey in its life",
    "Did you know? Bees navigate using the sun",
]

MESSAGES: dict[str, list[str]] = {
    "scrape": [
        "Scraping",
        "Extracting honey",
        "Buzzing through HTML",
        "Parsing the nectar",
        "Dodging bot traps",
        *_BEE_FACTS[:3],
    ],
    "google": [
        "Googling",
        "Searching the hive",
        "Pollinating results",
        "Crawling the web",
        "Fetching SERPs",
        *_BEE_FACTS[3:6],
    ],
    "fast-search": [
        "Searching",
        "Speed-buzzing",
        "Zipping through results",
        "Lightning fast",
        *_BEE_FACTS[6:8],
    ],
    "crawl": [
        "Crawling",
        "Following the trail",
        "Exploring links",
        "Mapping the web",
        "Discovering pages",
        *_BEE_FACTS[1:4],
    ],
    "usage": [
        "Checking the honeypot",
        "Counting credits",
        "Buzzing to the API",
        *_BEE_FACTS[4:6],
    ],
    "amazon-product": [
        "Fetching product",
        "Browsing the jungle",
        "Hunting for deals",
        "Reading reviews",
        *_BEE_FACTS[7:9],
    ],
    "amazon-search": [
        "Searching Amazon",
        "Flying through the jungle",
        "Comparing prices",
        "Scanning listings",
        *_BEE_FACTS[0:2],
    ],
    "walmart-search": [
        "Searching Walmart",
        "Rolling back prices",
        "Scanning the shelves",
        *_BEE_FACTS[5:7],
    ],
    "walmart-product": [
        "Fetching product",
        "Checking the aisle",
        "Reading the label",
        *_BEE_FACTS[8:10],
    ],
    "youtube-search": [
        "Searching YouTube",
        "Streaming honey",
        "Tuning in",
        "Browsing videos",
        *_BEE_FACTS[2:4],
    ],
    "youtube-metadata": [
        "Fetching metadata",
        "Reading the description",
        "Counting views",
        *_BEE_FACTS[9:10],
    ],
    "chatgpt": [
        "Querying ChatGPT",
        "Consulting the hive mind",
        "Thinking bee thoughts",
        "Processing prompt",
        *_BEE_FACTS[4:6],
    ],
    "sitemap": [
        "Fetching sitemap",
        "Reading the map",
        "Charting the course",
        *_BEE_FACTS[6:8],
    ],
    "_default": [
        "Working",
        "Buzzing",
        "zZZzzzZZ",
        "Bee patient",
        "Almost done",
        *_BEE_FACTS[:5],
    ],
}

# How many spinner ticks before rotating to the next message.
_MSG_ROTATE_TICKS = 18  # ~0.9s at 50ms per tick


# -- Flapping-bee spinner (single-line) --------------------------------------


class MiniBeeSpinner:
    """Single-line flapping-bee spinner with rotating contextual messages.

    Usage::

        with MiniBeeSpinner("scrape"):
            await do_request()

    The *message* argument is a command key into ``MESSAGES``.  If the key is
    not found it is used as a literal first message with ``_default`` extras.
    """

    def __init__(self, message: str = "scrape") -> None:
        # Resolve message list.
        if message in MESSAGES:
            self._messages = MESSAGES[message]
        else:
            self._messages = [message] + MESSAGES["_default"]
        self._messages = self._messages + _time_flavor()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _animate(self) -> None:
        idx = 0
        msg_idx = 0
        while not self._stop.is_set():
            # Rotate message every N ticks.
            if idx > 0 and idx % _MSG_ROTATE_TICKS == 0:
                msg_idx = (msg_idx + 1) % len(self._messages)

            bee = _render_inline_bee(idx)
            msg = self._messages[msg_idx]
            dots = "." * ((idx % 3) + 1)

            line = Text()
            line.append(" ")
            line.append_text(bee)
            line.append("  ")
            line.append(msg, style=f"bold {BEE_YELLOW}")
            line.append(dots.ljust(4), style="dim")

            with err_console.capture() as capture:
                err_console.print(line, end="")
            sys.stderr.write("\r\033[K" + capture.get())
            sys.stderr.flush()

            idx += 1
            self._stop.wait(0.05)

        # Clear the spinner line.
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()

    def start(self) -> None:
        if not sys.stderr.isatty():
            return
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def __enter__(self) -> MiniBeeSpinner:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()


# -- Styled output helpers ---------------------------------------------------


def print_banner() -> None:
    """Print the ScrapingBee CLI banner to stderr."""
    banner = Text()
    bee = _render_inline_bee(0)
    banner.append(" ")
    banner.append_text(bee)
    banner.append("  ScrapingBee", style=f"bold {BEE_YELLOW}")
    banner.append(" CLI", style="bold white")
    err_console.print(banner)


def styled_echo(message: str, *, style: str = "info", err: bool = True) -> None:
    c = err_console if err else console
    c.print(f"[{style}]{message}[/{style}]")


def echo_success(message: str) -> None:
    err_console.print(f"[success]{message}[/success]")


def echo_error(message: str) -> None:
    err_console.print(f"[error]{message}[/error]")


def echo_warning(message: str) -> None:
    err_console.print(f"[warn]{message}[/warn]")


def echo_key_value(key: str, value: str) -> None:
    text = Text()
    text.append(f"  {key}: ", style=f"bold {BEE_YELLOW}")
    text.append(value, style="white")
    err_console.print(text)


def echo_separator() -> None:
    err_console.print(f"[dim]{'─' * 40}[/dim]")


def format_progress_line(
    completed: int,
    total: int,
    *,
    rps: float | None = None,
    eta: str | None = None,
    failure_pct: float | None = None,
) -> Text:
    width = 20
    filled = int(width * completed / total) if total > 0 else 0
    bar = "█" * filled + "░" * (width - filled)

    text = Text()
    text.append("  ")
    text.append(bar, style=f"bold {BEE_YELLOW}")
    text.append(f" {completed}/{total}", style="bold white")
    if rps is not None:
        text.append(f"  {rps:.0f} req/s", style="dim")
    if eta is not None:
        text.append(f"  ETA {eta}", style="dim")
    if failure_pct is not None and failure_pct > 0:
        text.append(f"  Failures: {failure_pct:.0f}%", style=f"bold {BEE_RED}")
    return text


# -- Live credit tracker (polls usage API during batch/crawl) ----------------


class LiveCreditTracker:
    """Background thread that polls the usage API every 20 seconds and prints
    an updating honeycomb credit line to stderr.  Only active in REPL mode.

    Usage::

        with LiveCreditTracker(api_key, initial_remaining=33_000_000, total=50_000_000):
            run_batch(...)
    """

    _POLL_INTERVAL = 20  # seconds (safe: 3× per minute, limit is 6×)

    def __init__(
        self,
        api_key: str,
        *,
        initial_remaining: int | None = None,
        total: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._remaining = initial_remaining
        self._total = total
        self._start_remaining = initial_remaining
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- internal ------------------------------------------------------------

    def _fetch(self) -> tuple[int, int] | None:
        """Return (remaining, total) or None on error."""
        import asyncio
        import json as _json

        from .client import Client
        from .config import BASE_URL

        try:
            async def _go() -> tuple[int, int] | None:
                async with Client(self._api_key, BASE_URL, timeout=10) as c:
                    body, _, code = await c.usage()
                    if code == 200:
                        raw = _json.loads(body)
                        used = raw.get("used_api_credit", 0) or 0
                        total = raw.get("max_api_credit", 0) or 0
                        return total - used, total
                return None

            return asyncio.run(_go())
        except Exception:
            return None

    def _print_meter(self) -> None:
        if self._remaining is None or self._total is None:
            return
        line = Text()
        line.append("  ⬡ Credits: ", style=f"bold {BEE_YELLOW}")
        line.append_text(format_honeycomb_meter(
            self._total - self._remaining, self._total
        ))
        if self._start_remaining is not None:
            consumed = self._start_remaining - self._remaining
            if consumed > 0:
                line.append(f"  (−{consumed:,} this session)", style="dim")
        err_console.print(line)

    def _run(self) -> None:
        while not self._stop.wait(self._POLL_INTERVAL):
            if self._stop.is_set():
                break
            result = self._fetch()
            if result:
                self._remaining, self._total = result
                self._print_meter()

    # -- public --------------------------------------------------------------

    def start(self) -> None:
        if not _repl_mode:
            return
        # Print initial meter immediately if we have data
        if self._remaining is not None:
            self._print_meter()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def __enter__(self) -> LiveCreditTracker:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()


# -- Honeycomb credit meter --------------------------------------------------


def format_honeycomb_meter(used: int, total: int) -> Text:
    """Render a honeycomb-style credit meter. ⬡ = used, ⬢ = remaining."""
    width = 20
    if total <= 0:
        pct = 0.0
    else:
        pct = (total - used) / total
    remaining = total - used
    filled = int(width * pct)  # remaining portion (yellow)
    empty = width - filled  # used portion (dim)

    text = Text()
    text.append("  ")
    text.append("⬡" * filled, style=f"bold {BEE_YELLOW}")
    text.append("⬢" * empty, style="dim")
    text.append(f"  {remaining:,} / {total:,} credits remaining", style="bold white")

    # Color the percentage based on health
    pct_val = pct * 100
    if pct_val > 50:
        pct_style = f"bold {BEE_GREEN}"
    elif pct_val > 20:
        pct_style = f"bold {BEE_AMBER}"
    else:
        pct_style = f"bold {BEE_RED}"
    text.append(f"  ({pct_val:.0f}%)", style=pct_style)
    return text


# -- Completion summary panel ------------------------------------------------


def print_completion_summary(
    *,
    succeeded: int,
    failed: int,
    duration_s: float | None = None,
    credits_used: int | None = None,
    output_path: str | None = None,
    is_crawl: bool = False,
) -> None:
    """Print a styled completion summary panel to stderr."""
    from rich.panel import Panel
    from rich.table import Table

    total = succeeded + failed
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style=f"bold {BEE_YELLOW}", min_width=12)
    table.add_column(style="bold white")

    # Status line
    if failed == 0:
        status = Text()
        status.append(" \\(◉ω◉)/  ", style=f"bold {BEE_YELLOW}")
        status.append("Mission accomplished!", style=f"bold {BEE_GREEN}")
    else:
        status = Text()
        status.append(" /(◉ω◉)\\  ", style=f"bold {BEE_YELLOW}")
        status.append(f"{succeeded} succeeded, {failed} failed", style=f"bold {BEE_AMBER}")

    table.add_row(
        "Items",
        f"{succeeded}/{total} succeeded" + (f"  ({failed} failed)" if failed else ""),
    )
    if credits_used is not None:
        table.add_row("Credits", f"{credits_used:,} used")
    if duration_s is not None:
        if duration_s < 60:
            dur_str = f"{duration_s:.1f}s"
        else:
            m, s = divmod(int(duration_s), 60)
            dur_str = f"{m}m {s}s"
        table.add_row("Duration", dur_str)
        if total > 0 and duration_s > 0:
            table.add_row("Avg speed", f"{total / duration_s:.1f} req/s")
    if output_path:
        table.add_row("Output", output_path)
    if failed > 0:
        tip = (
            "Tip: Retry failures with --resume"
            if not is_crawl
            else "Tip: Re-run with --resume to retry"
        )
        table.add_row("", Text(tip, style="dim"))

    title = "Crawl Complete" if is_crawl else "Batch Complete"
    panel = Panel(
        table,
        title=f"[bold {BEE_YELLOW}]{title}[/]",
        subtitle=str(status),
        border_style=BEE_YELLOW,
        padding=(1, 2),
    )
    err_console.print(panel)


# -- Honeycomb trail progress ------------------------------------------------


def format_honeycomb_trail(
    completed: int,
    total: int,
    *,
    rps: float | None = None,
    eta: str | None = None,
    failure_pct: float | None = None,
) -> Text:
    """Bee flying across a honeycomb trail: ⬡⬡⬡\\(◉ω◉)/⬢⬢⬢"""
    width = 25
    if total <= 0:
        pos = 0
    else:
        pos = int(width * completed / total)
    pos = min(pos, width)

    trail_done = "⬡" * pos
    trail_left = "⬢" * (width - pos)

    bee_frames = ["\\(◉ω◉)/", "᎑(◉ω◉)᎑", "/(◉ω◉)\\", "᎑(◉ω◉)᎑"]
    bee = bee_frames[completed % len(bee_frames)]

    text = Text()
    text.append("  ")
    text.append(trail_done, style=f"bold {BEE_YELLOW}")
    text.append(bee, style=f"bold {BEE_YELLOW}")
    text.append(trail_left, style="dim")
    text.append(f" {completed}/{total}", style="bold white")
    if rps is not None:
        text.append(f"  {rps:.1f} req/s", style="dim")
    if eta is not None:
        text.append(f"  ETA {eta}", style="dim")
    if failure_pct is not None and failure_pct > 0:
        text.append(f"  Failures: {failure_pct:.0f}%", style=f"bold {BEE_RED}")
    return text


# -- Notification helper (cross-platform) ------------------------------------


def notify_completion(title: str, body: str) -> None:
    """Send a desktop notification + terminal bell. Cross-platform."""
    import shutil
    import subprocess

    # Terminal bell
    sys.stderr.write("\a")
    sys.stderr.flush()

    try:
        if sys.platform == "darwin":
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{body}" with title "{title}"',
                ],
                capture_output=True,
                timeout=5,
            )
        elif sys.platform == "win32":
            # PowerShell toast notification
            ps_cmd = (
                f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                f"ContentType = WindowsRuntime] > $null; "
                f"$template = [Windows.UI.Notifications.ToastNotificationManager]::"
                f"GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
                f"$textNodes = $template.GetElementsByTagName('text'); "
                f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{title}')) > $null; "
                f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{body}')) > $null; "
                f"$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
                f"[Windows.UI.Notifications.ToastNotificationManager]::"
                f"CreateToastNotifier('ScrapingBee CLI').Show($toast)"
            )
            subprocess.run(
                ["powershell", "-Command", ps_cmd],
                capture_output=True,
                timeout=10,
            )
        elif shutil.which("notify-send"):
            subprocess.run(
                ["notify-send", title, body, "-i", "dialog-information"],
                capture_output=True,
                timeout=5,
            )
    except Exception:
        pass  # Notification is best-effort


# -- Styled version output ---------------------------------------------------


def print_styled_version(version: str) -> None:
    """Print a branded version line to stderr."""
    import platform

    bee = _render_inline_bee(0)
    text = Text()
    text.append(" ")
    text.append_text(bee)
    text.append("  ScrapingBee CLI ", style=f"bold {BEE_YELLOW}")
    text.append(f"v{version}", style="bold white")
    err_console.print(text)
    err_console.print(f"  [dim]Python {platform.python_version()} | {sys.platform}[/dim]")
    # Try to show credit balance
    try:
        from .config import get_api_key

        api_key = get_api_key(None)
        if api_key:
            import asyncio

            from .client import Client
            from .config import BASE_URL

            async def _check():
                async with Client(api_key, BASE_URL, timeout=10) as c:
                    body, _, code = await c.usage()
                    if code == 200:
                        from .client import parse_usage

                        return parse_usage(body)
                return None

            usage = asyncio.run(_check())
            if usage:
                remaining = usage.get("credits", 0)
                err_console.print(
                    f"  [dim]API credits remaining:[/dim] [bold {BEE_GREEN}]{remaining:,}[/bold {BEE_GREEN}]"
                )
    except Exception:
        pass


# -- Welcome banner with grouped commands ------------------------------------


def print_welcome_banner(version: str, commands: dict[str, list[tuple[str, str]]]) -> None:
    """Print a branded welcome screen with grouped commands.

    commands: dict mapping group name to list of (cmd_name, description) tuples.
    """
    # Header
    bee = _render_inline_bee(0)
    header = Text()
    header.append(" ")
    header.append_text(bee)
    header.append("  ScrapingBee CLI ", style=f"bold {BEE_YELLOW}")
    header.append(f"v{version}", style="bold white")
    err_console.print(header)
    err_console.print("  [dim]Web scraping from the terminal, powered by bees.[/dim]")
    err_console.print()

    # Command groups
    for group_name, cmds in commands.items():
        err_console.print(f"  [bold {BEE_YELLOW}]~~ {group_name} ~~[/]")
        for cmd_name, description in cmds:
            err_console.print(f"    [bold {BEE_YELLOW}]{cmd_name:<20}[/] [dim]{description}[/dim]")
        err_console.print()

    err_console.print(
        "  [dim]Run[/dim] [bold white]scrapingbee <command> --help[/] [dim]for details.[/dim]"
    )
    err_console.print()


# -- Personality error messages ----------------------------------------------

_ERROR_MESSAGES: dict[int, tuple[str, str]] = {
    401: ("Bzzt! Invalid API key", "Run: scrapingbee auth"),
    403: (
        "The page stung back! (403 Forbidden)",
        "Try --premium-proxy or --stealth-proxy",
    ),
    404: ("The page flew away! (404 Not Found)", "Double-check your URL"),
    429: (
        "Whoa, too fast! The hive needs a breather (429)",
        "Use --concurrency to slow down, or wait a moment",
    ),
    500: (
        "Something went wrong on their end (500)",
        "Use --retries to try again automatically",
    ),
    502: ("The upstream hive is down (502)", "Try again in a moment"),
    503: (
        "Service temporarily unavailable (503)",
        "The target is overloaded — retry shortly",
    ),
}


def echo_bee_error(status_code: int, fallback_msg: str = "") -> None:
    """Print a bee-personality error with actionable tip."""
    if status_code in _ERROR_MESSAGES:
        msg, tip = _ERROR_MESSAGES[status_code]
        bee = _render_inline_bee(2)  # wings-down frame for errors
        line = Text()
        line.append(" ")
        line.append_text(bee)
        line.append(f"  {msg}", style=f"bold {BEE_RED}")
        err_console.print(line)
        err_console.print(f"  [dim]Tip: {tip}[/dim]")
    else:
        echo_error(fallback_msg or f"Error: HTTP {status_code}")


# -- Time-aware messages -----------------------------------------------------


def _time_flavor() -> list[str]:
    """Return extra messages based on time of day."""
    from datetime import datetime

    hour = datetime.now().hour
    day = datetime.now().weekday()

    extras: list[str] = []
    if 0 <= hour < 6:
        extras = ["The web never sleeps", "Late night data hunt", "Nocturnal bee mode"]
    elif 6 <= hour < 12:
        extras = [
            "Rise and scrape!",
            "Fresh morning data",
            "Early bird gets the data",
        ]
    elif 12 <= hour < 18:
        extras = ["Afternoon buzz", "Peak pollination hours"]
    else:
        extras = ["Evening crawl session", "Burning the midnight nectar"]

    if day == 0:
        extras.append("Monday motivation: fresh data!")
    elif day == 4:
        extras.append("TGIF — last scrape of the week?")
    return extras
