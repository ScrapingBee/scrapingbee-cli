# ScrapingBee power for Kiro

Fetch and read any web page, search the web, crawl a site, or pull structured data out of
pages — whenever a task needs content from a website. ScrapingBee handles JavaScript
rendering, CAPTCHAs and anti-bot blocking that `curl`, `requests` and headless browsers fail
on, and returns clean markdown, text or JSON.

This power uses the [Agent Plugins](https://agent-plugins.org) format and gives Kiro two things:

- **The ScrapingBee MCP server** (`https://mcp.scrapingbee.com/mcp`), connected at install
  through the [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) bridge: 18 tools for
  fetching pages as text, markdown, HTML or screenshots, extracting data, and getting JSON
  from Google, Amazon, Walmart, YouTube, ChatGPT and Gemini.
- **Skills for the ScrapingBee CLI** — a router that teaches the agent when to use the CLI
  instead of the MCP server (hundreds of URLs, crawling a whole site, output to files,
  scheduled jobs), how to keep credit spend low, and the guardrails that stay active whenever
  the CLI is used: scraped content is data and never instructions, the API key is never
  printed or written out, scheduled jobs only at the user's explicit request.

## What it needs

- A **ScrapingBee account and API key** — [sign up here](https://app.scrapingbee.com/account/register).
  API calls consume credits from your plan.
- **`SCRAPINGBEE_API_KEY`** set in the environment Kiro starts from (export it in your shell,
  then launch Kiro from that shell). The bridge reads it to authenticate the MCP server, and
  the CLI reads the same variable. Kiro does not yet expand `${VAR}` inside a power's own
  `mcp.json` headers, which is why the server is connected through `mcp-remote`.
- **Node.js 18 or newer** with `npx`, which runs the `mcp-remote` bridge.
- For the CLI skills: `uv tool install scrapingbee-cli` (or `pip install scrapingbee-cli`),
  then `scrapingbee auth` or `SCRAPINGBEE_API_KEY` in the environment.

## Install

Kiro → Powers → **Add Custom Power** → **Import power from GitHub**, then paste
`https://github.com/ScrapingBee/scrapingbee-cli` and pick the `plugins/scrapingbee-kiro`
folder, or clone the repository and choose **Import power from a folder**.

## What it runs, sends and fetches

The power contains only the MCP server configuration, skill instructions and reference
documentation — no hooks, no scripts, and nothing that executes on its own. The MCP server
is called over HTTPS with your API key; when a task calls for it, the agent also runs the
`scrapingbee` command-line tool on your behalf. Both send requests only to the ScrapingBee
API (`mcp.scrapingbee.com`, `app.scrapingbee.com`) and fetch the web pages or search results
you asked for. The power sends no data anywhere else.

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
