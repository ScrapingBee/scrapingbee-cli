#!/usr/bin/env bash
# Syncs skills and agent files from the canonical source to all tool-specific directories.
#
# Source of truth:
#   plugins/scrapingbee-cli/skills/scrapingbee-cli/              → canonical skill (Claude Code plugin)
#   plugins/scrapingbee-cli/skills/scrapingbee-cli/.claude/agents/scraping-pipeline.md  → canonical agent
#
# Skills destinations:
#   .agents/skills/scrapingbee-cli/      (Amp, RooCode, Gemini CLI)
#   .github/skills/scrapingbee-cli/      (GitHub Copilot)
#   .kiro/skills/scrapingbee-cli/        (Kiro IDE)
#   .opencode/skills/scrapingbee-cli/    (OpenCode)
#
# Agent destinations (markdown):
#   .gemini/agents/scraping-pipeline.md
#   .github/agents/scraping-pipeline.agent.md  (note: .agent.md extension for Copilot)
#   .augment/agents/scraping-pipeline.md
#   .factory/droids/scraping-pipeline.md
#   .kiro/agents/scraping-pipeline.md
#   .opencode/agents/scraping-pipeline.md
#
# NOT synced (different format, update manually):
#   .amazonq/cli-agents/scraping-pipeline.json  (JSON format)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
SOURCE_SKILL="$REPO_ROOT/plugins/scrapingbee-cli/skills/scrapingbee-cli"
SOURCE_AGENT="$SOURCE_SKILL/.claude/agents/scraping-pipeline.md"

# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
echo "Syncing skills..."

SKILL_DIRS=(
    "$REPO_ROOT/.agents/skills/scrapingbee-cli"
    "$REPO_ROOT/.github/skills/scrapingbee-cli"
    "$REPO_ROOT/.kiro/skills/scrapingbee-cli"
    "$REPO_ROOT/.opencode/skills/scrapingbee-cli"
)

for dest in "${SKILL_DIRS[@]}"; do
    rsync -a --delete \
        --exclude='.claude' \
        --exclude='.DS_Store' \
        "$SOURCE_SKILL/" "$dest/"
    echo "  Updated: $dest"
done

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------
echo "Syncing agents..."

AGENT_DESTINATIONS=(
    "$REPO_ROOT/.gemini/agents/scraping-pipeline.md"
    "$REPO_ROOT/.github/agents/scraping-pipeline.agent.md"
    "$REPO_ROOT/.augment/agents/scraping-pipeline.md"
    "$REPO_ROOT/.factory/droids/scraping-pipeline.md"
    "$REPO_ROOT/.kiro/agents/scraping-pipeline.md"
    "$REPO_ROOT/.opencode/agents/scraping-pipeline.md"
)

for dest in "${AGENT_DESTINATIONS[@]}"; do
    cp "$SOURCE_AGENT" "$dest"
    echo "  Updated: $dest"
done

# ---------------------------------------------------------------------------
echo ""
echo "Note: .amazonq/cli-agents/scraping-pipeline.json uses JSON format — update manually."
echo "Done."
