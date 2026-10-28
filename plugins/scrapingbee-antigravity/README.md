# ScrapingBee for Antigravity

Fetch and read any web page, search the web, crawl a site, or pull structured data out of
pages — whenever a task needs content from a website. ScrapingBee handles JavaScript
rendering, CAPTCHAs and anti-bot blocking that `curl`, `requests` and headless browsers fail
on, and returns clean markdown, text or JSON.

This plugin gives Antigravity two things:

- **The ScrapingBee MCP server** (`https://mcp.scrapingbee.com/mcp`): 18 tools for fetching
  pages as text, markdown, HTML or screenshots, extracting data, and getting JSON from Google,
  Amazon, Walmart, YouTube, ChatGPT and Gemini.
- **Skills for the ScrapingBee CLI** — a router that teaches the agent when to use the CLI
  instead of the MCP server (hundreds of URLs, crawling a whole site, output to files,
  scheduled jobs), how to keep credit spend low, and the guardrails that stay active whenever
  the CLI is used: scraped content is data and never instructions, the API key is never
  printed or written out, scheduled jobs only at the user's explicit request.

## Install

```bash
agy plugin install https://github.com/ScrapingBee/scrapingbee-cli
```

This installs the `scrapingbee` plugin from this folder. The same repository also carries
skills-only packagings for other hosts (`scrapingbee-cli`, `scrapingbee-kiro`); you can
uninstall those in Antigravity, they add nothing here.

The plugin starts disabled because its MCP server needs your API key. In the CLI run
`/plugin`, open **Configure MCP servers…** for `scrapingbee`, and paste the key. In the IDE,
the plugin asks for it when you enable it.

## What it needs

- A **ScrapingBee account and API key** — [sign up here](https://app.scrapingbee.com/account/register).
  API calls consume credits from your plan.
- For the CLI skills: `uv tool install scrapingbee-cli` (or `pip install scrapingbee-cli`),
  then `scrapingbee auth` or `SCRAPINGBEE_API_KEY` in the environment.

## What it runs, sends and fetches

The plugin contains only the MCP server configuration, skill instructions and reference
documentation — no hooks, no scripts, and nothing that executes on its own. The MCP server
is called over HTTPS with your API key; when a task calls for it, the agent also runs the
`scrapingbee` command-line tool on your behalf. Both send requests only to the ScrapingBee
API (`mcp.scrapingbee.com`, `app.scrapingbee.com`) and fetch the web pages or search results
you asked for. The plugin sends no data anywhere else.

## Examples

- "Get me the full text of this JavaScript-heavy pricing page as clean markdown."
- "I have a CSV of 200 product URLs — fetch the current price for each and update the CSV in place."
- "Crawl this docs site and save every `/guide/` page as markdown for my RAG index."
- "What's the current price of Amazon ASIN B0CX23V2ZK?"

## Support and privacy

- Support: contact@scrapingbee.com, or the [FAQ](https://www.scrapingbee.com/faq/).
- Privacy policy: https://www.scrapingbee.com/privacy-policy/
- Terms: https://www.scrapingbee.com/terms-and-conditions/

## Links

- MCP server: https://mcp.scrapingbee.com/
- CLI documentation: https://www.scrapingbee.com/documentation/cli/
- API documentation: https://www.scrapingbee.com/documentation/
- Source: https://github.com/ScrapingBee/scrapingbee-cli
- License: MIT
