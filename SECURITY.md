# Security Policy

## Supported versions

Security fixes are released for the latest minor version of `scrapingbee-cli` on PyPI and for the plugins and skills in this repository on the `main` branch.

| Version | Supported |
| ------- | --------- |
| 1.6.x   | Yes       |
| < 1.6   | No — upgrade with `pip install --upgrade scrapingbee-cli` |

## Scope

This policy covers the code in this repository:

- the `scrapingbee` command-line tool (`src/scrapingbee_cli/`)
- the agent plugins under `plugins/` (Claude Code, Codex, Cursor, Kiro, Antigravity)
- the Agent Skills under `.agents/skills/` and their mirrors

Issues in the ScrapingBee API or the hosted MCP server (`https://mcp.scrapingbee.com/mcp`) can be reported the same way; we will route them to the right team.

## Reporting a vulnerability

Please do not open a public GitHub issue for security problems.

Email **contact@scrapingbee.com** with the subject "Security: scrapingbee-cli" and include:

- a description of the issue and its impact
- steps or a minimal command to reproduce it
- the CLI version (`scrapingbee --version`) and your OS

We acknowledge reports within 3 business days and aim to ship a fix for confirmed high-severity issues within 30 days. We will credit you in the release notes unless you prefer otherwise.

## Handling of API keys

The CLI reads your ScrapingBee API key from the `SCRAPINGBEE_API_KEY` environment variable, a `.env` file, or the file written by `scrapingbee auth`. It never prints the key or sends it anywhere except the ScrapingBee API. If you believe a key was exposed, rotate it in your ScrapingBee dashboard.
