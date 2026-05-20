"""ScrapingBee CLI theme: colours and styled output helpers used by the
REPL renderer."""

from __future__ import annotations

import os
import sys

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


# -- Bee facts (rotating trivia shown while a command is in flight) ---------
# Surfaced on the dim row above the input in the REPL. Kept short so they
# fit on a single line even on narrow terminals.

BEE_FACTS: list[str] = [
    "Did you know? Bees can fly up to 15 mph.",
    "Did you know? A bee visits 50–100 flowers per trip.",
    "Did you know? Bees have 5 eyes — two compound, three simple.",
    "Did you know? Honey never spoils — jars from ancient Egypt are still edible.",
    "Did you know? Bees communicate by dancing — the famous waggle dance.",
    "Did you know? A single hive can house up to 60,000 bees.",
    "Did you know? Bees flap their wings about 200 times per second.",
    "Did you know? Bees can recognize individual human faces.",
    "Did you know? One bee makes about 1/12 of a teaspoon of honey in its life.",
    "Did you know? Bees navigate using the sun's position in the sky.",
    "Did you know? Bees pollinate about one third of the food we eat.",
    "Did you know? A queen bee can lay up to 2,000 eggs per day.",
    "Did you know? Worker bees are all female.",
    "Did you know? Bees see ultraviolet patterns we can't.",
    "Did you know? Honeycomb hexagons tile flat space using the least wax — a property mathematicians proved only in 1999.",
    "Did you know? Worker bees in a hive are about 75% genetically related to each other — human siblings are only 50%.",
    "Did you know? A bee's brain is the size of a sesame seed.",
    "Did you know? Bees have been around for more than 100 million years — older than most flowering plants.",
    "Did you know? The buzzing sound is the rapid beat of a bee's wings.",
    "Did you know? Bees can sense the Earth's magnetic field.",
    "Did you know? In ancient Babylon, newlyweds drank honey-wine for a month — the likely origin of the word 'honeymoon'.",
    "Did you know? A queen bee can live up to 5 years; a worker, only 6 weeks in summer.",
    "Did you know? Drones (male bees) have no stinger.",
    "Did you know? Bees fan their wings to cool the hive on hot days.",
    "Did you know? Bees can tell time using internal circadian rhythms.",
    "Did you know? A foraging bee can carry nectar weighing nearly half her body weight.",
    "Did you know? Bumblebees can fly in the rain.",
    "Did you know? Honeybees evolved from ancient predatory wasps.",
    "Did you know? A swarm of bees can contain over 50,000 individuals.",
    "Did you know? Bees regulate hive temperature within a degree of 35°C / 95°F.",
    "Did you know? The queen's pheromones hold a colony together.",
    "Did you know? Bees can recognize the smell of TNT — they're used in landmine detection.",
    "Did you know? Bees make beeswax from special glands on their abdomen.",
    "Did you know? Royal jelly is what turns a regular larva into a queen.",
    "Did you know? Bees do a 'cleansing flight' after winter to relieve themselves.",
    "Did you know? Honey is naturally antibacterial.",
    "Did you know? Bees can travel up to 6 miles from their hive in a single trip.",
    "Did you know? A bee colony collectively visits about 2 million flowers to make one pound of honey.",
    "Did you know? Bees have hair on their eyes to collect more pollen.",
    "Did you know? Worker bees switch jobs as they age — nurse, builder, guard, then forager.",
    "Did you know? The bee was a heraldic emblem of Napoleon's imperial regime.",
    "Did you know? Honey has been found preserved in pharaohs' tombs.",
    "Did you know? Bees can be trained to detect cancer in human breath.",
    "Did you know? The phrase 'busy as a bee' first appeared in Chaucer's Canterbury Tales.",
    "Did you know? Stingless bees exist — about 500 species worldwide.",
    "Did you know? The mason bee is a far more efficient pollinator than honeybees.",
    "Did you know? Bees produce six different products: honey, beeswax, pollen, propolis, royal jelly, and venom.",
    "Did you know? 'Propolis' is Greek for 'before the city' — bees seal the hive entrance with it to keep out invaders.",
    "Did you know? Bees prefer flowers with caffeine — it boosts their memory.",
    "Did you know? Bees actually build round cells first — surface tension in the warm wax reshapes them into hexagons.",
    "Did you know? Worker bees flap their wings to evaporate water from nectar, making honey.",
    "Did you know? Bumblebees are excellent at 'buzz pollination' — vibrating flowers to release pollen.",
    "Did you know? Honey's color depends on which flowers the bees visited.",
    "Did you know? A bee's stomach holds 70 mg of nectar — nearly its own weight.",
    "Did you know? Africanized 'killer' bees came from a 1957 lab accident in Brazil.",
    "Did you know? Honeybees are not native to the Americas — they were brought from Europe.",
    "Did you know? A bee's alarm pheromone smells like banana — isoamyl acetate, the very same compound.",
    "Did you know? The smallest bee in the world is just 2 mm long (Perdita minima).",
    "Did you know? The largest bee is Wallace's giant bee, about the length of a thumb.",
    "Did you know? Foraging bees find efficient routes between flowers using simple flight-rule heuristics.",
    "Did you know? Honey takes 7 days to ripen from nectar inside the hive.",
    "Did you know? Bees were used in ancient warfare — Greeks catapulted hives over castle walls.",
    "Did you know? Bees use 'undertakers' — workers whose job is to remove dead bees from the hive.",
    "Did you know? Bees can count up to four.",
    "Did you know? A single bee can produce only about half a gram of wax in her lifetime.",
    "Did you know? Bumblebees can carry a load close to their own body weight in pollen and nectar.",
    "Did you know? In Mycenaean Greece, priestesses of the goddess Demeter were called 'Melissai' — the bees.",
    "Did you know? Mead — honey wine — may be humanity's oldest fermented drink.",
    "Did you know? A worker bee can sting only once; the stinger is barbed.",
    "Did you know? Honey contains hydrogen peroxide, produced by an enzyme bees add to nectar.",
    "Did you know? Bees can be left-handed or right-handed when entering flowers.",
    "Did you know? Beekeeping appears in Egyptian wall art dating back 4,500 years.",
    "Did you know? The 'Queen of the Hive' is actually selected by worker bees in larval stage.",
    "Did you know? Without bees, most almonds, blueberries, and apples wouldn't exist as we know them.",
    "Did you know? A bee's wings beat fast enough to generate static electricity, which attracts pollen.",
    "Did you know? Bees have two stomachs — one for eating, one for storing nectar.",
    "Did you know? Killer bees are not particularly venomous — they're just very aggressive.",
    "Did you know? Honey crystallization is normal — gentle warming returns it to liquid.",
    "Did you know? Bees prefer blue, purple, and yellow flowers — red appears black to them.",
    "Did you know? Nearly 90% of wild plants depend on animal pollinators, mostly bees.",
    "Did you know? Bees take orientation flights before becoming foragers, memorizing landmarks.",
    "Did you know? Some bee species are solitary — they don't form colonies at all.",
    "Did you know? A bee scientist is called a melittologist.",
    "Did you know? Bees were the totem of the Egyptian pharaohs.",
    "Did you know? The Mayans practiced beekeeping with stingless Melipona bees.",
    "Did you know? Bees use propolis to mummify intruders they can't carry out of the hive.",
    "Did you know? In rural England, 'telling the bees' of a death in the family was tradition — leave them out and they'd reportedly abandon the hive.",
    "Did you know? A queen bee mates with up to 20 drones in a single flight.",
    "Did you know? Honey from different regions tastes completely different — manuka, acacia, clover, lavender.",
    "Did you know? Bees can teach each other to use tools.",
    "Did you know? Some bees sleep — even with their tongues sticking out.",
    "Did you know? Honeycomb cells tilt slightly upward — about 13 degrees — so liquid honey doesn't drip out before it ripens.",
    "Did you know? Drones die immediately after mating with the queen.",
    "Did you know? Bee venom is being researched as a cancer treatment.",
    "Did you know? In Slovenia, beekeeping is so culturally important it's on UNESCO's heritage list.",
    "Did you know? Bees can be tracked individually using tiny radio tags.",
    "Did you know? The waggle dance can encode distance, direction, and quality of a food source.",
    "Did you know? Bees can perceive flower humidity to estimate nectar quality.",
    "Did you know? Hive bees fan their wings in coordinated rows to ventilate the colony.",
    "Did you know? Pollen is the bee's only source of protein.",
    "Did you know? Bees are the only insects that produce food eaten by humans.",
    "Did you know? Some orchids look and smell like female bees to trick males into pollinating them.",
    "Did you know? Bees recognize their hive entrance by its exact location, not by smell alone.",
    "Did you know? Aristotle wrote one of the earliest scientific treatises on beekeeping.",
    "Did you know? The hum of a healthy hive is around 250 Hz.",
    "Did you know? Bees prefer warm nectar — they're cold-blooded but warm their flight muscles to 35°C.",
    "Did you know? Honey contains pinocembrin, an antioxidant studied for its links to brain health.",
    "Did you know? In winter, honeybees cluster tightly and shiver their wing muscles to keep the hive warm.",
    "Did you know? A worker bee's lifespan in winter is up to 6 months — much longer than summer bees.",
    "Did you know? The queen bee produces over 30 different pheromones to manage the colony.",
    "Did you know? A pound of honey requires bees to fly the equivalent of three orbits around Earth.",
]


def current_bee_fact(tick: int, period_ticks: int = 50) -> str:
    """Pick a bee fact from the list, rotating once every ``period_ticks``
    ticks of the REPL's 10 Hz ticker. Default 50 → a new fact every 5s.
    """
    if not BEE_FACTS:
        return ""
    return BEE_FACTS[(tick // max(1, period_ticks)) % len(BEE_FACTS)]


# -- Bee-themed action verbs (rotate in place of the static "running") ------
# Used as the toolbar status label while a command is in flight. Plain
# -ing verbs so they slot grammatically into ``<verb>  ·  12.3s``.

BEE_VERBS: list[str] = [
    "pollinating",
    "buzzing",
    "foraging",
    "gathering nectar",
    "scouting flowers",
    "waggle-dancing",
    "tending the hive",
    "building combs",
    "harvesting honey",
    "on the wing",
    "working the field",
    "humming along",
    "fanning the hive",
    "guarding the entrance",
    "swarming",
    "courting flowers",
    "loading pollen baskets",
    "patrolling petals",
    "communing with clover",
    "sipping nectar",
    "weaving wax",
    "circling the queen",
    "ferrying nectar",
    "cleaning cells",
    "warming brood",
    "deciphering scent trails",
    "navigating by sun",
    "feeding the queen",
    "polishing the comb",
    "humming homeward",
    "tasting petals",
    "marking flowers",
    "scouting territories",
    "buzzing through HTML",
    "extracting honey",
    "pollinating pages",
    "harvesting data",
    "chasing redirects",
    "weaving CSS",
    "decoding selectors",
    "rendering blossoms",
    "sniffing user agents",
    "scrubbing trackers",
]


def current_bee_verb(tick: int, period_ticks: int = 25) -> str:
    """Pick a bee verb from the list, rotating once every ``period_ticks``
    ticks. Default 25 → a new verb every 2.5s on the 10 Hz ticker — fast
    enough to feel alive on quick scrapes, slow enough not to flicker.
    """
    if not BEE_VERBS:
        return "running"
    return BEE_VERBS[(tick // max(1, period_ticks)) % len(BEE_VERBS)]


def current_bee_blurb(tick: int, period_ticks: int = 50) -> str:
    """Pick the dim-row content while a command is in flight, alternating
    between a "…" bee verb and a "Did you know? ..." fact every
    ``period_ticks`` ticks (default 50 → a 5-second switch on the 10 Hz
    ticker). The FIRST slot is always a verb so quick commands
    (``usage``, ``docs``, fast scrapes) show a natural action label
    rather than a flash of trivia. Subsequent slots alternate
    verb → fact → verb → fact for the user to read while they wait.

    The fact index and verb index are independent, so the rotation
    doesn't cycle the same fact/verb pair together — the lists have
    different lengths and advance on their own slot counters.
    """
    slot = tick // max(1, period_ticks)
    if slot % 2 == 0:
        if not BEE_VERBS:
            return ""
        verb_idx = (slot // 2) % len(BEE_VERBS)
        return BEE_VERBS[verb_idx] + "…"
    if not BEE_FACTS:
        return ""
    fact_idx = (slot // 2) % len(BEE_FACTS)
    return BEE_FACTS[fact_idx]


# -- Crawl live-status state (current URL, fetched count, phase) ------------
# The Scrapy spider's signal handlers push updates here from the worker
# thread; the REPL's ticker reads them on the main thread to repaint the
# dim row above the input. ``_crawl_status`` is intentionally a plain
# dict mutation since (a) Python dict assignments are atomic and (b) the
# update pattern is single-key writes from one writer at a time, so no
# explicit lock is needed.

_crawl_status: dict | None = None


def update_crawl_status(
    *,
    current_url: str | None = None,
    fetched: int | None = None,
    queued: int | None = None,
    saved: int | None = None,
    phase: str | None = None,
) -> None:
    """Update one or more fields of the crawl status. Any field left as
    ``None`` keeps its previous value (so a per-signal handler can update
    just the field it knows about).

    Subprocess crawl mode: the REPL parent runs each crawl in a child
    Python process so it gets a fresh Twisted reactor. The child has no
    way to push into the parent's in-memory ``_crawl_status``, so when
    the env var ``SCRAPINGBEE_CRAWL_STATUS_FILE`` is set we *also*
    mirror the current dict to that JSON file. The parent's ticker
    polls the file and forwards updates back into its own
    ``_crawl_status`` so the layout window keeps showing live progress.
    """
    global _crawl_status  # noqa: PLW0603
    if _crawl_status is None:
        _crawl_status = {
            "current_url": None,
            "fetched": 0,
            "queued": 0,
            "saved": 0,
            "phase": "starting",
        }
    if current_url is not None:
        _crawl_status["current_url"] = current_url
    if fetched is not None:
        _crawl_status["fetched"] = fetched
    if queued is not None:
        _crawl_status["queued"] = queued
    if saved is not None:
        _crawl_status["saved"] = saved
    if phase is not None:
        _crawl_status["phase"] = phase
    _maybe_mirror_to_status_file()


def _maybe_mirror_to_status_file() -> None:
    """Atomic write of ``_crawl_status`` + progress state to
    ``$SCRAPINGBEE_CRAWL_STATUS_FILE`` so a polling parent process sees
    updates without read/write races. Atomic-rename pattern (write to
    ``.tmp``, ``os.replace``) keeps the parent from ever reading a
    half-flushed JSON file.

    Progress data (``_progress_state``) rides on the same payload —
    that's how the parent learns about a known total (sitemap mode,
    ``--max-pages N``) and can show the honeycomb bar above the URL
    line in its fixed widget.
    """
    sf = os.environ.get("SCRAPINGBEE_CRAWL_STATUS_FILE")
    if not sf:
        return
    if _crawl_status is None and _progress_state is None:
        return
    try:
        import json as _json
        payload: dict = {}
        if _crawl_status is not None:
            payload.update(_crawl_status)
        if _progress_state is not None:
            payload["progress_completed"] = _progress_state.get("completed")
            payload["progress_total"] = _progress_state.get("total")
            payload["progress_rps"] = _progress_state.get("rps")
            payload["progress_eta"] = _progress_state.get("eta")
            payload["progress_failure_pct"] = _progress_state.get("failure_pct")
        tmp = sf + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            _json.dump(payload, fh)
        os.replace(tmp, sf)
    except Exception:
        pass


def get_crawl_status() -> dict | None:
    return _crawl_status


def has_crawl_status() -> bool:
    return _crawl_status is not None


def clear_crawl_status() -> None:
    global _crawl_status  # noqa: PLW0603
    _crawl_status = None
    sf = os.environ.get("SCRAPINGBEE_CRAWL_STATUS_FILE")
    if sf:
        try:
            os.unlink(sf)
        except Exception:
            pass


def tick_crawl_render() -> None:
    """Re-render the dedicated crawl status widget in scrollback. Same
    in-place mechanism as the batch honeycomb (``emit_progress_lines``
    replaces the last N lines), but rendering the crawl-specific
    content: a status line with ``<phase>: <url>  (X fetched[/Y])``
    plus, when a total is known (sitemap mode), the honeycomb
    progress bar above it.

    Safe to call when no crawl is in flight — early-exits if
    ``_crawl_status`` is None.
    """
    if _crawl_status is None:
        return
    import io
    from rich.console import Console as _RC

    lines_text: list[Text] = []
    progress = _progress_state
    if progress is not None:
        # Sitemap-mode batch-style bar, identical to the batch widget.
        rows = format_honeycomb_grid(
            completed=progress["completed"],
            total=progress["total"],
            rps=progress.get("rps"),
            eta=progress.get("eta"),
            failure_pct=progress.get("failure_pct"),
            animate=True,
        )
        lines_text.extend(rows)

    # Always include the live URL / fetched-count line below the bar.
    status_text = Text()
    status_text.append("  ")
    phase = _crawl_status.get("phase") or "fetching"
    url = _crawl_status.get("current_url")
    fetched = _crawl_status.get("fetched") or 0
    saved = _crawl_status.get("saved") or 0
    if url and len(url) > 80:
        url = url[:48] + "…" + url[-25:]
    status_text.append(f"{phase}: ", style=f"bold {BEE_YELLOW}")
    if url:
        status_text.append(url, style=BEE_WHITE)
    else:
        status_text.append("…", style="dim")
    status_text.append(f"  ({fetched} fetched", style="dim")
    if saved:
        status_text.append(f", {saved} saved", style="dim")
    status_text.append(")", style="dim")
    lines_text.append(status_text)

    rendered: list[str] = []
    for row in lines_text:
        buf = io.StringIO()
        _c = _RC(
            file=buf, force_terminal=True, color_system="truecolor",
            highlight=False, width=200,
        )
        _c.print(row, end="")
        rendered.append(buf.getvalue())
    emit_progress_lines(rendered)


def crawl_status_line() -> str | None:
    """Build a single-line status string. Kept around for any caller
    that wants a one-line crawl summary; the live in-scrollback widget
    uses ``tick_crawl_render`` instead.
    """
    if _crawl_status is None:
        return None
    phase = _crawl_status.get("phase") or "fetching"
    url = _crawl_status.get("current_url")
    fetched = _crawl_status.get("fetched") or 0
    saved = _crawl_status.get("saved") or 0
    # Trim very long URLs so the line fits on narrow terminals — keep the
    # prefix (scheme + host + start of path) and the tail (last 25 chars)
    # so users can still recognise the page.
    if url and len(url) > 80:
        url = url[:48] + "…" + url[-25:]
    if url:
        suffix = f"  ({fetched} fetched"
        if saved:
            suffix += f", {saved} saved"
        suffix += ")"
        return f"{phase}: {url}{suffix}"
    return f"{phase}…  ({fetched} fetched)"


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
    # In the crawl subprocess we hand state to the parent via the
    # status file (``_maybe_mirror_to_status_file`` reads
    # ``_progress_state`` alongside ``_crawl_status``). Rendering here
    # would emit honeycomb rows via ``emit_progress_lines`` → the
    # stderr fallback (no ``_progress_renderer`` is installed in the
    # child), and the parent would then ingest those rows into
    # scrollback as duplicates because each Scrapy log line displaces
    # the ``replace_last_n_lines`` anchor.
    if os.environ.get("SCRAPINGBEE_CRAWL_STATUS_FILE"):
        _maybe_mirror_to_status_file()
        return
    # In the REPL parent during a crawl (``_crawl_status`` non-None),
    # the fixed crawl_status widget reads ``_progress_state`` directly
    # and renders the honeycomb in place. Rendering through
    # ``tick_progress_render`` here would ALSO write to scrollback
    # (the batch path), giving the same duplicate-rows problem the
    # child fix already solved.
    if _crawl_status is not None:
        return
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


