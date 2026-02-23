# Google Search API

Structured Google SERP (classic, news, maps, images, etc.). **Credit:** 10–15 per request. JSON output; use **`--output-file file.json`** (before command).

## Command

```bash
scrapingbee --output-file serp.json google "pizza new york" --country-code us
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--search-type` | string | `classic`, `news`, `maps`, `lens`, `shopping`, `images`, `ai_mode`. |
| `--country-code` | string | ISO 3166-1 (e.g. us, gb, de). |
| `--device` | string | `desktop` or `mobile`. |
| `--page` | int | Page number (default 1). |
| `--language` | string | Language code (e.g. en, fr, de). |
| `--nfpr` | true/false | Disable autocorrection. |
| `--extra-params` | string | Extra URL params (URL-encoded). |
| `--add-html` | true/false | Include full HTML. |
| `--light-request` | true/false | Light request. |

## Batch

`--input-file` (one query per line) + `--output-dir`. Output: `N.json` in batch folder.

## Output

JSON: `organic_results` (position, title, url, description, domain, date, rich_snippet, sitelinks), `local_results`, `knowledge_graph`, `bottom_ads`, `meta_data`. Optional `add_html` adds full HTML.
