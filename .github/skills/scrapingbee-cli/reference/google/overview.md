# Google Search API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

Structured Google SERP (classic, news, maps, images, etc.). **Credit:** 10–15 per request. JSON output; use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee google --output-file serp.json "pizza new york" --country-code us
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--search-type` | string | `classic`, `news`, `maps`, `lens`, `shopping`, `images`, `ai-mode`. |
| `--country-code` | string | ISO 3166-1 (e.g. us, gb, de). |
| `--device` | string | `desktop` or `mobile`. |
| `--page` | int | Page number (default 1). |
| `--language` | string | Language code (e.g. en, fr, de). |
| `--nfpr` | true/false | Disable autocorrection. |
| `--extra-params` | string | Extra URL params (URL-encoded). |
| `--add-html` | true/false | Include full HTML. |
| `--light-request` | true/false | Light request. |

## Extract URLs for piping

Use `--extract-field` to get just the URLs from organic results — no `jq` needed:

```bash
scrapingbee google --extract-field organic_results.url "python web scraping" > urls.txt
scrapingbee scrape --output-dir pages --input-file urls.txt --return-page-markdown true
```

`ai-mode` returns an AI-generated answer instead of the usual organic listing:

```json
{
  "ai_mode_answer": {
    "response_text": "Python is a high-level, interpreted programming language...",
    "links": [{"title": "Python.org", "url": "https://www.python.org/"}],
    "prompt": "what is python"
  },
  "meta_data": {"url": "https://www.google.com/search?q=..."}
}
```

## Batch

`--input-file` (one query per line) + `--output-dir`. Output: `N.json` in batch folder.

## Output

**`classic` (default):** JSON with `organic_results` (position, title, url, description, domain, date, rich_snippet, sitelinks), `local_results`, `knowledge_graph`, `top_ads`, `bottom_ads`, `related_searches`, `meta_data`. Optional `add_html` adds full HTML.

**Other search types** change the primary result key:

| `--search-type` | Primary result key |
|-----------------|-------------------|
| `news` | `news_results` (title, link, source, date) |
| `images` | `images_results` (title, link, thumbnail) |
| `shopping` | `organic_results` (title, url, price, price_str, currency, merchant, delivery, thumbnail) |
| `maps` | `maps_results` (title, address, rating, phone) |
| `lens` | `lens_results` (image_url, title, link) |
| `ai-mode` | `ai_mode_answer.response_text` + `ai_mode_answer.links` |

```json
{
  "organic_results": [
    {
      "position": 1,
      "title": "Result Title",
      "url": "https://example.com/page",
      "description": "Page description...",
      "domain": "example.com",
      "date": null,
      "rich_snippet": {},
      "sitelinks": []
    }
  ],
  "local_results": [],
  "knowledge_graph": {},
  "bottom_ads": [],
  "meta_data": {"url": "https://www.google.com/search?q=...", "total_results": 1000000}
}
```
