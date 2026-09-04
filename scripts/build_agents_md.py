#!/usr/bin/env python3
"""Generate AGENTS.md from the canonical SKILL.md.

AGENTS.md is what hosts that read a single file (Codex, Amp, and friends) see.
Edit SKILL.md; this derives AGENTS.md from it.

Two deliberate differences from SKILL.md:

- No YAML frontmatter. The tuned description becomes the opening paragraph, so
  the wording that decides whether an agent picks this skill still reaches hosts
  that never read frontmatter.
- No local links. SKILL.md defers to `reference/`, which only exists inside an
  installed plugin. AGENTS.md points at the public docs instead.

Run via ./sync-skills.sh, not directly.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SKILL = REPO / "plugins/scrapingbee-cli/skills/scrapingbee-cli/SKILL.md"
AGENTS = REPO / "AGENTS.md"
DOCS = "https://www.scrapingbee.com/documentation/cli/"

SUMMARY = (
    "Single-sentence summary: one CLI to scrape URLs, run batches and crawls, and call SERP, "
    "e-commerce, YouTube, and ChatGPT via the "
    "[ScrapingBee API](https://www.scrapingbee.com/documentation/)."
)

# Replaces SKILL.md's Index table, which points into a plugin directory that a
# single-file host does not have.
DEEPER = f"""## Deeper documentation

This file is the router. For anything it defers on:

- **Every option for a command:** `scrapingbee [command] --help` — authoritative, always current.
- **Full CLI documentation:** {DOCS}
- **API parameters, response formats and credit costs:** https://www.scrapingbee.com/documentation/
- **Trimming responses (`--smart-extract`), JS scenarios, proxy escalation, batch layout:** see the
  CLI documentation above, or the `reference/` directory of the installed skill.
"""


def build(skill_text: str) -> str:
    body = re.sub(r"\A---\n.*?\n---\n", "", skill_text, count=1, flags=re.S)
    description = re.search(r'^description: "(.*)"$', skill_text, re.M).group(1)

    # The canonical H1 plus the tuned description as prose, then the body from
    # its first section onward.
    body = re.sub(r"\A\s*# ScrapingBee\b.*?(?=\n## )", "", body, count=1, flags=re.S)
    out = f"# ScrapingBee CLI\n\n{description}\n\n{SUMMARY}\n\n{body.lstrip()}"

    # Swap the plugin-relative Index for docs pointers.
    out = re.sub(r"\n## Index — user need → command → reference\n.*?(?=\n## )", f"\n{DEEPER}", out, flags=re.S)

    # The subagent note is a Claude Code convention and means nothing to a host
    # reading only this file.
    out = re.sub(r"\n> \*\*Multi-step workflows:\*\*.*?(?=\n\n)", "", out, flags=re.S)

    # Any surviving local link becomes a docs link; a single-file host cannot
    # follow a path into a plugin it does not have installed. Link text that is
    # itself a path gets replaced too, so it does not read as a broken promise.
    def relink(match: re.Match) -> str:
        text = match.group(1)
        if "/" in text and text.endswith(".md"):
            text = "the CLI documentation"
        return f"[{text}]({DOCS})"

    out = re.sub(r"\[([^\]]+)\]\((?!https?:)[^)]+\)", relink, out)
    return re.sub(r"\n{3,}", "\n\n", out)


def main() -> int:
    if not SKILL.is_file():
        print(f"missing {SKILL}", file=sys.stderr)
        return 1
    generated = build(SKILL.read_text())

    leftover = [
        link
        for link in re.findall(r"\]\(([^)]+)\)", generated)
        if not link.startswith("http")
    ]
    if leftover:
        print(f"refusing to write: local links survived {leftover}", file=sys.stderr)
        return 1

    AGENTS.write_text(generated)
    print(f"  Generated: AGENTS.md ({len(generated)} bytes) from SKILL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
