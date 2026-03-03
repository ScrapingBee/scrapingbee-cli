# Contributing

## Setup

```bash
git clone https://github.com/ScrapingBee/scrapingbee-cli
cd scrapingbee-cli
pip install -e ".[dev,crawl]"
```

## Running tests

```bash
pytest -m "not integration"          # unit tests only (no API key needed)
pytest                               # all tests (requires SCRAPINGBEE_API_KEY)
```

## Linting

```bash
ruff check src tests
ruff format src tests
```

## Versioning

Keep these in sync whenever you bump the version:
- `pyproject.toml` → `[project] version`
- `src/scrapingbee_cli/__init__.py` → `__version__`
- `.claude-plugin/marketplace.json` → `plugins[0].version`
- `.claude-plugin/plugin.json` → `version`
- `skills/scrapingbee-cli/SKILL.md` → frontmatter `version`

The CI `check-version` job enforces that `pyproject.toml` and `__init__.py` stay in sync.

## Updating skill and agent docs

`skills/scrapingbee-cli/` is the canonical source for all skill documentation. After editing it, run:

```bash
./sync-skills.sh
```

This propagates changes to `.agents/skills/scrapingbee-cli/` (Amp, RooCode, OpenCode, Gemini CLI) and `.kiro/skills/scrapingbee-cli/` (Kiro IDE), and copies the agent file to all tool-specific agent directories.

The Amazon Q agent (`.amazonq/cli-agents/scraping-pipeline.json`) uses JSON format and must be updated manually.

## Adding a new command

1. Create `src/scrapingbee_cli/commands/<name>.py` following the pattern of an existing command (e.g. `fast_search.py`).
2. Register it in `src/scrapingbee_cli/commands/__init__.py`.
3. Add a reference doc under `skills/scrapingbee-cli/reference/<name>/`.
4. Add the command to the index table in `skills/scrapingbee-cli/SKILL.md`.
5. Run `./sync-skills.sh`.
