# Fast Search API

Sub-second SERP results. Simpler than Google. **Credit:** per request. JSON output; use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee fast-search --output-file fast.json "ai news today" --country-code us --language en
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--page` | int | Page number (default 1). |
| `--country-code` | string | ISO 3166-1 country. |
| `--language` | string | Language code (e.g. en, fr). |

## Pipeline: fast search → scrape result pages

```bash
# Extract result URLs and scrape each page (no jq)
scrapingbee fast-search --extract-field organic.link "ai news today" > urls.txt
scrapingbee scrape --output-dir pages --input-file urls.txt --return-page-markdown true
```

## Batch

`--input-file` (one query per line) + `--output-dir`. Output: `N.json` in batch folder.

## Output

JSON: `organic` array; each item: `title`, `link`, `description`, `rank`, `extensions`.

```json
{
  "organic": [
    {
      "rank": 1,
      "title": "Result Title",
      "link": "https://example.com/page",
      "description": "Page description...",
      "extensions": {}
    }
  ]
}
```
