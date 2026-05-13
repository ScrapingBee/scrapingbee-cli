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


# -- Multi-line progress renderer hook ---------------------------------------
# The REPL installs a renderer here at startup that knows how to replace
# the last N lines of its virtual scrollback in place. Batch operations
# call ``emit_progress_lines`` to update the honeycomb progress bar —
# in REPL mode it overwrites the previous frame; outside the REPL it
# falls back to printing the lines normally.

_progress_renderer = None  # type: ignore[var-annotated]


def set_progress_renderer(fn) -> None:
    """Install a function ``fn(lines)`` where ``lines`` is a list of
    ANSI-rendered strings. Called by the REPL to wire up in-place updates.
    """
    global _progress_renderer  # noqa: PLW0603
    _progress_renderer = fn


def emit_progress_lines(lines: list[str]) -> None:
    """Emit a multi-line progress update. In REPL mode this overwrites
    the previous frame; otherwise it falls back to writing to stderr.
    ``lines`` is a list of already-rendered ANSI strings (one per row,
    no trailing newlines).
    """
    if _progress_renderer is not None:
        try:
            _progress_renderer(lines)
            return
        except Exception:
            pass
    # Fallback: plain stderr append.
    for line in lines:
        sys.stderr.write(line + "\n")
    sys.stderr.flush()


# -- Shared progress state for the REPL ticker animation ---------------------
# batch.py calls ``update_progress_state`` on each completion to record
# latest counts/rates. The REPL ticker calls ``tick_progress_render`` at
# ~10 Hz so the in-progress (boundary) hex shimmers between frames even
# when no new completion has fired. ``clear_progress_state`` is called
# when the batch finishes so the ticker stops re-rendering.

_progress_state: dict | None = None


def update_progress_state(
    completed: int,
    total: int,
    *,
    rps: float | None = None,
    eta: str | None = None,
    failure_pct: float | None = None,
) -> None:
    global _progress_state  # noqa: PLW0603
    _progress_state = {
        "completed": completed,
        "total": total,
        "rps": rps,
        "eta": eta,
        "failure_pct": failure_pct,
    }
    tick_progress_render()


def clear_progress_state() -> None:
    global _progress_state  # noqa: PLW0603
    _progress_state = None


def has_progress_state() -> bool:
    return _progress_state is not None


def tick_progress_render() -> None:
    """Re-render the progress widget with the latest state. Safe to call
    when no batch is in progress (becomes a no-op). The shimmer phase
    is derived from ``time.monotonic()`` inside ``format_honeycomb_grid``.
    """
    if _progress_state is None:
        return
    rows = format_honeycomb_grid(
        completed=_progress_state["completed"],
        total=_progress_state["total"],
        rps=_progress_state["rps"],
        eta=_progress_state["eta"],
        failure_pct=_progress_state["failure_pct"],
        animate=True,
    )
    import io
    from rich.console import Console as _RC

    rendered: list[str] = []
    for row in rows:
        buf = io.StringIO()
        _c = _RC(
            file=buf, force_terminal=True, color_system="truecolor",
            highlight=False, width=200,
        )
        _c.print(row, end="")
        rendered.append(buf.getvalue())
    emit_progress_lines(rendered)


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


# -- Spinner -----------------------------------------------------------------


# Hex bloom — a "honey crystallising" cycle expressed as a 3-cell-wide
# animation that radiates from the centre outward. Pure geometry, no
# mascot: dot grows into a honeycomb cell, peaks at a four-pointed
# sparkle (the moment crystals form), then drains back.
#
# The middle cell is the focal point and stays anchored; "halo" cells
# appear and disappear symmetrically so the bloom feels like it's growing
# in all directions, not rightward.
#
# Each frame pairs a 3-character composition with a colour from a
# dim→bright→warm gradient so the eye reads a glowing, breathing shape.
#
# Frames (centre + halo, always 3 cells wide):
#   " · "  dust        (dim grey)
#   " • "  speck       (dim amber)
#   "·⬡·"  outline + halo  (amber)
#   "·⬢·"  honeycomb + halo (bright yellow)
#   "⬡✦⬡"  sparkle + halo   (warm yellow-orange — PEAK / crystallised)
#   "·⬢·"  descending
#   "·⬡·"
#   " • "
_HEX_BLOOM_FRAMES: list[tuple[str, str]] = [
    (" · ", "#555555"),
    (" • ", "#886600"),
    ("·⬡·", "#BAA000"),
    ("·⬢·", "#FFCD23"),
    ("⬡✦⬡", "#FFB13D"),
    ("·⬢·", "#FFCD23"),
    ("·⬡·", "#BAA000"),
    (" • ", "#886600"),
]

# Per-command verbs that rotate during the pulse — keep them short and active.
_PHRASES: dict[str, list[str]] = {
    "scrape":           ["Fetching", "Rendering", "Extracting"],
    "crawl":            ["Crawling", "Following links", "Discovering"],
    "google":           ["Searching", "Querying"],
    "fast-search":      ["Searching"],
    "amazon-product":   ["Fetching product"],
    "amazon-search":    ["Searching Amazon"],
    "walmart-product":  ["Fetching product"],
    "walmart-search":   ["Searching Walmart"],
    "youtube-search":   ["Searching"],
    "youtube-metadata": ["Fetching metadata"],
    "chatgpt":          ["Querying", "Thinking"],
    "usage":            ["Checking credits"],
    "sitemap":          ["Fetching sitemap"],
}

_FRAME_INTERVAL = 0.08          # seconds per frame ⇒ ~12 fps, smooth bloom
_PHRASE_DURATION_FRAMES = 30    # rotate verb every ~2.4s
_SHIMMER_DIVISOR = 2            # shimmer advances every N bloom frames

# Shimmer palette — one bright "peak" cell sweeps across the verb, with two
# flank cells receiving softer highlights so the glim feels like a wave
# instead of a hard cursor.
_SHIMMER_PEAK  = "#FFFFFF"
_SHIMMER_FLANK = "#FFE780"


def _shimmer_text(text: str, position: int, base_color: str) -> Text:
    """Render `text` with a glimmer of light at `position`.

    The character at `position` is bright white; characters at ±1 are warm
    light yellow; everything else uses `base_color`. Combined with a position
    that advances each frame, this reads as a glow sweeping across the word.
    """
    out = Text()
    for i, ch in enumerate(text):
        distance = abs(i - position)
        if distance == 0:
            style = f"bold {_SHIMMER_PEAK}"
        elif distance == 1:
            style = f"bold {_SHIMMER_FLANK}"
        else:
            style = f"bold {base_color}"
        out.append(ch, style=style)
    return out


class MiniBeeSpinner:
    """Single-line pulsing-asterisk spinner with a rotating command verb.

    Usage::

        with MiniBeeSpinner("scrape"):
            await do_request()

    Renders one line: a Claude-style asterisk that blooms (· → ✻ → ·), a
    short verb that rotates every ~2.4s ("Fetching" / "Rendering" / ...),
    and an elapsed-time counter once the operation passes 0.5s.
    """

    def __init__(self, message: str = "") -> None:
        self._label = message
        # Resolve the verb cycle: per-command phrases if known, else just the
        # label as a single static verb.
        self._phrases = _PHRASES.get(message, [message] if message else ["Working"])
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _animate(self) -> None:
        import time

        start = time.monotonic()
        idx = 0
        while not self._stop.is_set():
            glyph, color = _HEX_BLOOM_FRAMES[idx % len(_HEX_BLOOM_FRAMES)]
            phrase = self._phrases[(idx // _PHRASE_DURATION_FRAMES) % len(self._phrases)]
            shimmer_pos = (idx // _SHIMMER_DIVISOR) % max(1, len(phrase))
            elapsed = time.monotonic() - start

            line = Text()
            line.append(" ")
            line.append(glyph, style=f"bold {color}")
            line.append("  ")
            line.append_text(_shimmer_text(phrase, shimmer_pos, BEE_YELLOW))
            if elapsed >= 0.5:
                line.append(f"  · {elapsed:.1f}s", style="dim")

            with err_console.capture() as capture:
                err_console.print(line, end="")
            sys.stderr.write("\r\033[K" + capture.get())
            sys.stderr.flush()

            idx += 1
            self._stop.wait(_FRAME_INTERVAL)

        # Clear the spinner line.
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()

    def start(self) -> None:
        # Disabled inside the REPL: the spinner's `\r`-rewrites would flow
        # through patch_stdout and trigger a bottom-strip redraw on every
        # frame, causing visible flicker. The REPL's toolbar conveys the
        # "running" state instead.
        if _repl_mode:
            return
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
        # Disabled inside the REPL. The REPL's bottom toolbar already shows
        # credits + a usage gauge; running this thread additionally would
        # repaint the bottom strip every ~0.5s via `\r`-rewrites that flow
        # through patch_stdout, which is exactly what we see as flicker
        # during a scrape. (Direct CLI mode — `scrapingbee scrape ...` outside
        # the REPL — still gets the live meter on stderr as before.)
        if _repl_mode:
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
    """Render a honeycomb-style credit meter.

    Filled hex (⬢) = remaining credits (ScrapingBee brand yellow).
    Outline hex (⬡) = used / consumed (dim grey).
    Intuitive "fuel gauge" semantics — yellow shows what you have left.
    """
    width = 20
    if total <= 0:
        pct = 0.0
    else:
        pct = (total - used) / total
    remaining = total - used
    filled = int(width * pct)  # remaining portion (yellow, filled hex)
    empty = width - filled  # used portion (dim, outline hex)

    text = Text()
    text.append("  ")
    text.append("⬢" * filled, style=f"bold {BEE_YELLOW}")
    text.append("⬡" * empty, style=f"dim {BEE_YELLOW}")
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


def format_honeycomb_grid(
    completed: int,
    total: int,
    *,
    rps: float | None = None,
    eta: str | None = None,
    failure_pct: float | None = None,
    animate: bool = False,
) -> list[Text]:
    """3-row honeycomb progress bar for batch operations.

    Filled hex (⬢) = completed (ScrapingBee brand yellow, bold).
    Outline hex (⬡) = remaining (brand yellow, dim — still brand-colored,
    just lower-emphasis so the difference reads visually). Cells fill in
    row order, left to right.

    Row layout (offset to look like a honeycomb):
        Row 0:  ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢
        Row 1: ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢
        Row 2:  ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢ ⬢

    Returns a list of three Text objects, one per row. The third row also
    carries the ``X/Y  N req/s  ETA …`` stats trailing the cells.
    """
    # Single row of hexes — the terminal's line-height made a 3-row stack
    # feel visually disconnected, and the user preferred a tighter
    # single-line look. The multi-line plumbing (``replace_last_n_lines``,
    # the ticker shimmer, the progress-state hook) is kept intact because
    # it costs nothing and the single line is just ``n=1``.
    width = 20
    if total <= 0:
        filled = 0
    else:
        filled = int(width * completed / total)
    filled = min(filled, width)

    filled_style = f"bold {BEE_YELLOW}"
    outline_style = f"dim {BEE_YELLOW}"

    # Boundary cell shimmer: the next-to-be-filled cell pulses between a
    # mid-bright and a soft yellow so the user can see the batch is alive
    # even when no completion has fired in the last few ms. Only active
    # when ``animate=True`` (the REPL ticker passes that) and only when
    # there is a still-empty cell at the front of the bar.
    shimmer_styles: list[str] = []
    if animate and filled < width:
        import math
        import time as _time

        # 1.2 Hz pulse — slow enough to read, fast enough to feel alive.
        phase = 0.5 + 0.5 * math.sin(_time.monotonic() * 2 * math.pi * 1.2)
        if phase > 0.55:
            shimmer_styles.append(f"bold {BEE_YELLOW}")
        else:
            shimmer_styles.append(f"{BEE_YELLOW}")

    def _render_row(row_text: Text) -> None:
        if filled > 0:
            row_text.append("⬢" * filled, style=filled_style)
        if filled < width:
            if shimmer_styles:
                # First empty cell uses the shimmer style; the rest are
                # the regular dim-yellow outline.
                row_text.append("⬡", style=shimmer_styles[0])
                if (width - filled) > 1:
                    row_text.append("⬡" * (width - filled - 1), style=outline_style)
            else:
                row_text.append("⬡" * (width - filled), style=outline_style)

    row_text = Text()
    row_text.append("  ")
    _render_row(row_text)
    # Stats trail directly off the single row.
    row_text.append(f"  {completed}/{total}", style="bold white")
    if rps is not None:
        row_text.append(f"  {rps:.1f} req/s", style="dim")
    if eta is not None:
        row_text.append(f"  ETA {eta}", style="dim")
    if failure_pct is not None and failure_pct > 0:
        row_text.append(f"  Failures: {failure_pct:.0f}%", style=f"bold {BEE_RED}")
    return [row_text]


def format_honeycomb_trail(
    completed: int,
    total: int,
    *,
    rps: float | None = None,
    eta: str | None = None,
    failure_pct: float | None = None,
) -> Text:
    """Backward-compatible single-line variant. New code should use
    :func:`format_honeycomb_grid` for the richer 3-row layout.
    """
    width = 25
    if total <= 0:
        pos = 0
    else:
        pos = int(width * completed / total)
    pos = min(pos, width)

    text = Text()
    text.append("  ")
    text.append("⬢" * pos, style=f"bold {BEE_YELLOW}")
    text.append("⬡" * (width - pos), style=f"dim {BEE_YELLOW}")
    text.append(f"  {completed}/{total}", style="bold white")
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


