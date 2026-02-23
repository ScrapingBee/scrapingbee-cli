# Amazon Search API

Search Amazon products. JSON output. **Credit:** 5–15 per request. Use **`--output-file file.json`** (before command).

## Command

```bash
scrapingbee --output-file search.json amazon-search "laptop" --domain com --sort-by bestsellers
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--start-page` | int | Starting page. |
| `--pages` | int | Number of pages. |
| `--sort-by` | string | `most_recent`, `price_low_to_high`, `price_high_to_low`, `average_review`, `bestsellers`, `featured`. |
| `--device` | string | `desktop`, `mobile`, or `tablet`. |
| `--domain` | string | com, co.uk, de, etc. |
| `--country` / `--zip-code` / `--language` / `--currency` | — | Locale. |
| `--category-id` / `--merchant-id` | string | Category or seller. |
| `--autoselect-variant` | true/false | Auto-select variants. |
| `--add-html` / `--light-request` / `--screenshot` | true/false | Optional. |

## Batch

`--input-file` (one query per line) + `--output-dir`. Output: `N.json`.

## Output

Structured products array. With `--parse false`: raw HTML. See [reference/amazon/search-output.md](reference/amazon/search-output.md).
