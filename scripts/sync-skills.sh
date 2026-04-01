#!/usr/bin/env bash
# sync-skills.sh — sync the canonical skill tree to all AI platform directories.
#
# Source of truth: .agents/skills/
# Targets: .github/skills/, .kiro/skills/, .opencode/skills/, plugins/scrapingbee-cli/skills/
#
# Usage: bash scripts/sync-skills.sh [--dry-run]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_ROOT/.agents/skills"

TARGETS=(
  "$REPO_ROOT/.github/skills"
  "$REPO_ROOT/.kiro/skills"
  "$REPO_ROOT/.opencode/skills"
  "$REPO_ROOT/plugins/scrapingbee-cli/skills"
)

DRY_RUN=0
for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=1
done

RSYNC_OPTS=(-a --delete --exclude='.DS_Store')
[[ $DRY_RUN -eq 1 ]] && RSYNC_OPTS+=(--dry-run -v)

echo "Source: $SRC"
for target in "${TARGETS[@]}"; do
  echo "Syncing → $target"
  rsync "${RSYNC_OPTS[@]}" "$SRC/" "$target/"
done

echo "Done."

echo ""
echo "NOTE: .amazonq/cli-agents/scraping-pipeline.json uses Amazon Q's JSON format"
echo "and cannot be synced automatically. Update it manually when agent content changes."
