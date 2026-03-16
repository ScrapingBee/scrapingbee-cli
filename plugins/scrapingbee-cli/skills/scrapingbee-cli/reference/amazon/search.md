# Amazon Search API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

Search Amazon products. JSON output. **Credit:** 5–15 per request. Use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee amazon-search --output-file search.json "laptop" --domain com --sort-by bestsellers
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--start-page` | int | Starting page. |
| `--pages` | int | Number of pages. |
| `--sort-by` | string | `most-recent`, `price-low-to-high`, `price-high-to-low`, `average-review`, `bestsellers`, `featured`. |
| `--device` | string | `desktop`, `mobile`, or `tablet`. |
| `--domain` | string | com, co.uk, de, etc. |
| `--country` | string | Country code. **Must not match domain** (e.g. don't use `--country de` with `--domain de`). Use `--zip-code` instead when country matches domain. |
| `--zip-code` / `--language` / `--currency` | — | Locale options. |
| `--category-id` / `--merchant-id` | string | Category or seller. |
| `--autoselect-variant` | true/false | Auto-select variants. |
| `--add-html` / `--light-request` / `--screenshot` | true/false | Optional. |

## Pipeline: search → product details

```bash
# Extract ASINs and feed directly into amazon-product batch (no jq)
scrapingbee amazon-search --extract-field products.asin "mechanical keyboard" > asins.txt
scrapingbee amazon-product --output-dir products --input-file asins.txt
scrapingbee export --output-file products.csv --input-dir products --format csv
```

Use `--extract-field products.url` to pipe product page URLs into `scrape` for deeper extraction.

## Batch

`--input-file` (one query per line) + `--output-dir`. Output: `N.json`.

## Output

Structured products array. Batch: output is `N.json` in batch folder.

```json
{
  "meta_data": {"url": "https://www.amazon.com/s?k=laptop", "total_results": 500},
  "products": [
    {
      "position": 1,
      "asin": "B0DPDRNSXV",
      "title": "Product Name",
      "price": 299.99,
      "currency": "USD",
      "rating": 4.5,
      "review_count": 1234,
      "url": "https://www.amazon.com/dp/B0DPDRNSXV",
      "image": "https://m.media-amazon.com/images/..."
    }
  ]
}
```
