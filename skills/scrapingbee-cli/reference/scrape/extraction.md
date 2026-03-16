# Scrape: extraction

Use `--extract-rules` (CSS/XPath, no extra credit) or `--ai-query` / `--ai-extract-rules` (natural language, +5 credits). Pass rules as **JSON string**.

## extract-rules

Format: `{"key": "selector"}` or `{"key": {"selector": "...", "output": "text", "type": "item"}}`. Shortcuts: `"title": "h1"` = text; `"link": "a@href"` = attribute. Selector starting with `/` = XPath.

**Full format per key:** selector (required), selector_type (auto/css/xpath), output (text, html, @attr, table_array, table_json), type (item/list), clean (true/false).

```bash
scrapingbee scrape --output-file out.json "https://example.com" --extract-rules '{"title":"h1","link":"a@href"}'
```

## ai-query

Single natural-language query. Optional `--ai-selector` limits to CSS region. +5 credits.

```bash
scrapingbee scrape --output-file out.json "https://example.com" --ai-query "price of the product" --ai-selector "#product"
```

**Response format** (raw body — no `--json-response`):

```json
{"ai_response": "29.99"}
```

With `--json-response true`, the `ai_response` key appears inside the wrapper alongside headers, cost, and body:

```json
{
  "body": "<html>...</html>",
  "ai_response": "29.99",
  "cost": 6,
  "initial-status-code": 200,
  "resolved-url": "https://example.com/product"
}
```

## ai-extract-rules

JSON: each key has description and optional type (string, number, boolean, list, item). Nested: use output with sub-keys. Optional enum. +5 credits.

```bash
--ai-extract-rules '{"title":"page title","price":{"description":"product price in dollars","type":"number"}}'
```

**Response format** (raw body):

```json
{"title": "Widget Pro", "price": "29.99"}
```

Use `--json-response true` to get extracted data in wrapper with headers/cost. See [reference/scrape/output.md](reference/scrape/output.md). Use space-separated values only, not `=value`.
