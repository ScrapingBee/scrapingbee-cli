# ScrapingBee CLI Installation (for AI)

**Requires:** Python 3.10+.

**Command name:** The installed command is `scrapingbee` (the package name is `scrapingbee-cli`). Use `scrapingbee` in all commands.

## Install

- **pip** – Use when the AI is working inside a project or existing venv (most common). Ensures the CLI is available in that environment.
- **pipx** – Use when the CLI should be available globally without a project venv.

```bash
pip install scrapingbee-cli          # scrape, batch, search, Amazon, Walmart, YouTube, ChatGPT
pip install "scrapingbee-cli[crawl]" # adds the crawl command (requires Scrapy)
# or globally:
pipx install scrapingbee-cli
pipx install "scrapingbee-cli[crawl]"
```

> **`crawl` command:** The `scrapingbee crawl` command requires the `[crawl]` extra (Scrapy). If Scrapy is not installed the command prints an error and exits. Install with `pip install "scrapingbee-cli[crawl]"` before using `crawl`.

In a virtual environment: create/activate the venv, then `pip install scrapingbee-cli`.

## Verify

```bash
scrapingbee --help
scrapingbee usage
```

## Authentication

**Resolution order** (where the CLI gets the API key):

1. **Environment** – `SCRAPINGBEE_API_KEY` in the shell.
2. **.env in current directory** – `SCRAPINGBEE_API_KEY` in a `.env` file in the project/cwd.
3. **.env in config** – `~/.config/scrapingbee-cli/.env`. `scrapingbee auth` writes the key to this file only (not to project `.env`). Load order: env wins, then cwd `.env`, then that file (load_dotenv uses setdefault).

**Store API key (recommended):**

```bash
scrapingbee auth
# Non-interactive (user provides key):
scrapingbee auth --api-key <key>
# Show config path only (no write):
scrapingbee auth --show
```

The user must provide the API key. Use the key the user supplies with `scrapingbee auth --api-key <key>`.

**Documentation URL:** `scrapingbee docs` prints the ScrapingBee API docs URL; `scrapingbee docs --open` opens it in the default browser.

**Environment only:**

```bash
export SCRAPINGBEE_API_KEY=your_api_key_here
```

**Remove stored key:** Only run `scrapingbee logout` if the user explicitly asks to remove or clear the stored API key.

```bash
scrapingbee logout
```

## If authentication fails

1. Run `scrapingbee auth --api-key <key>` with the key the user provides (if not provided, ask the user)
2. Or set `SCRAPINGBEE_API_KEY` in the shell or in a `.env` file in the project or in `~/.config/scrapingbee-cli/.env` (CLI config module).

## Command not found

If `scrapingbee` is not found after install:

1. Activate the environment where `pip install scrapingbee-cli` was run (e.g. `source .venv/bin/activate`). Pip puts the `scrapingbee` script in that env’s bin (e.g. `.venv/bin`), so it’s on PATH only when that env is active.
2. Reinstall: `pip install --force-reinstall scrapingbee-cli`.

**See also:** [rules/security.md](rules/security.md) (credits, output safety, shell safety).
