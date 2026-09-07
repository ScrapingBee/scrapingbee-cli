#!/usr/bin/env python3
"""Check that every `scrapingbee` command in the docs is real.

Extracts commands from fenced code blocks and inline code in SKILL.md, AGENTS.md
and the skill's reference pages, then validates each subcommand and flag against
`scrapingbee --help`. A documented command with a flag that does not exist
teaches agents to run something that fails.

    python3 scripts/check_examples.py            # check
    python3 scripts/check_examples.py --list     # also print what was checked

Exits non-zero if anything does not resolve.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO / "plugins/scrapingbee-cli/skills/scrapingbee-cli"
GUARD_DIR = REPO / "plugins/scrapingbee-cli/skills/scrapingbee-cli-guard"
TARGETS = [
    REPO / "AGENTS.md",
    SKILL_DIR / "SKILL.md",
    *sorted(SKILL_DIR.rglob("reference/**/*.md")),
    *sorted(SKILL_DIR.rglob("rules/*.md")),
    *sorted(GUARD_DIR.rglob("*.md")),
]

# Placeholders that appear in prose to illustrate a form, not a real command.
IGNORED_FLAGS = {"--option", "--flag"}
COMMAND_RE = re.compile(r"\bscrapingbee\s+((?:[^\n`|>]|\\\n)+)")


def cli_available() -> bool:
    return shutil.which("scrapingbee") is not None


def help_text(*args: str) -> str:
    try:
        proc = subprocess.run(
            ["scrapingbee", *args, "--help"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    return proc.stdout + proc.stderr


def flags_in(text: str) -> set[str]:
    return set(re.findall(r"--[a-z0-9][a-z0-9-]*", text))


def subcommands() -> set[str]:
    root = help_text()
    # The Commands: section lists one subcommand per line, indented.
    tail = root.split("Commands:", 1)[-1]
    return {m.group(1) for m in re.finditer(r"^\s{2,}([a-z][a-z0-9-]*)\s{2,}", tail, re.M)}


def extract(path: Path) -> list[tuple[int, str]]:
    """Every `scrapingbee ...` invocation in a file, with its line number.

    Only code counts: fenced blocks, and inline spans in prose. Scanning raw
    prose matches sentences like "lists all scrapingbee schedules with ...".
    """
    found: list[tuple[int, str]] = []
    in_fence = False
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        if raw.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        candidates = [raw] if in_fence else re.findall(r"`([^`]+)`", raw)
        for candidate in candidates:
            for match in COMMAND_RE.finditer(candidate):
                command = match.group(1).strip().rstrip("\\").strip()
                if command:
                    found.append((lineno, command))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate documented scrapingbee commands")
    ap.add_argument("--list", action="store_true", help="print every command checked")
    args = ap.parse_args()

    if not cli_available():
        print("scrapingbee is not on PATH — install it to run this check", file=sys.stderr)
        return 2

    known_subs = subcommands()
    if not known_subs:
        print("could not parse the subcommand list from `scrapingbee --help`", file=sys.stderr)
        return 2
    root_flags = flags_in(help_text())
    flag_cache: dict[str, set[str]] = {}
    # Bare `scrapingbee --resume` / `--scraping-config NAME` auto-route to a
    # subcommand, so their flags are valid without one but absent from root help.
    all_flags = root_flags.union(*(flags_in(help_text(s)) for s in sorted(known_subs)))

    problems: list[str] = []
    checked = 0

    for path in TARGETS:
        if not path.is_file():
            continue
        for lineno, command in extract(path):
            tokens = command.split()
            if not tokens:
                continue
            sub = tokens[0] if not tokens[0].startswith("-") else None
            rel = path.relative_to(REPO)

            if sub and sub not in known_subs:
                # Could be a placeholder like `scrapingbee [command] --help`.
                if not re.fullmatch(r"[\[<].*[\]>]", sub):
                    problems.append(f"{rel}:{lineno}: unknown subcommand '{sub}' — {command[:70]}")
                continue

            # A command can name more than one subcommand — `schedule ... scrape
            # URL --output-file x` carries flags belonging to the inner one.
            present = [t for t in tokens if t in known_subs]
            for name in present:
                if name not in flag_cache:
                    flag_cache[name] = flags_in(help_text(name))
            valid = root_flags.union(*(flag_cache[n] for n in present)) if present else all_flags

            for flag in flags_in(" ".join(t for t in tokens if t.startswith("--"))):
                if flag in IGNORED_FLAGS or flag in valid:
                    continue
                problems.append(f"{rel}:{lineno}: '{sub}' has no {flag} — {command[:70]}")
            checked += 1
            if args.list:
                print(f"  ok  {rel}:{lineno}  scrapingbee {command[:80]}")

    print(f"\nchecked {checked} documented command(s) across {len(TARGETS)} file(s)")
    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("all documented commands resolve against the installed CLI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
