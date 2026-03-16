# Auth (API key, login, logout)

Manage API key. Auth is unified: config → environment → `.env`. Credits/concurrency are separate: see [reference/usage/overview.md](reference/usage/overview.md).

## Set API key

**1. Store in config (recommended)** — Key in `~/.config/scrapingbee-cli/.env`.

```bash
scrapingbee auth
scrapingbee auth --api-key your_api_key_here   # non-interactive
```

**Show config path only (no write):** `scrapingbee auth --show` prints the path where the key is or would be stored.

## Documentation URL

```bash
scrapingbee docs              # print ScrapingBee API documentation URL
scrapingbee docs --open       # open it in the default browser
```

**2. Environment:** `export SCRAPINGBEE_API_KEY=your_key`

**3. .env file:** `SCRAPINGBEE_API_KEY=your_key` in cwd or `~/.config/scrapingbee-cli/.env`. Cwd loaded first; env not overwritten.

**Resolution order** (which key is used): env → `.env` in cwd → `.env` in `~/.config/scrapingbee-cli/.env` (stored by `scrapingbee auth`). Existing env is not overwritten by .env (setdefault).

## Remove stored key

Only run `scrapingbee logout` if the user explicitly requests removal of the stored API key.

```bash
scrapingbee logout
```

Does not unset `SCRAPINGBEE_API_KEY` in shell; use `unset SCRAPINGBEE_API_KEY` for that.

## Verify

```bash
scrapingbee --help
scrapingbee usage
```

Install and troubleshooting: [rules/install.md](rules/install.md). Security: [rules/security.md](rules/security.md).
