# Amazon Product API

Fetch a single product by **ASIN**. JSON output. **Credit:** 5–15 per request. Use **`--output-file file.json`** (before command).

## Command

```bash
scrapingbee --output-file product.json amazon-product B0DPDRNSXV --domain com
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--device` | string | `desktop`, `mobile`, or `tablet`. |
| `--domain` | string | Amazon domain: `com`, `co.uk`, `de`, `fr`, etc. |
| `--country` | string | Country code (e.g. us, gb, de). |
| `--zip-code` | string | ZIP for local availability/pricing. |
| `--language` | string | e.g. en_US, es_US, fr_FR. |
| `--currency` | string | USD, EUR, GBP, etc. |
| `--add-html` | true/false | Include full HTML. |
| `--light-request` | true/false | Light request. |
| `--screenshot` | true/false | Take screenshot. |

## Batch

`--input-file` (one ASIN per line) + `--output-dir`. Output: `N.json`.

## Output

JSON: asin, brand, title, description, bullet_points, price, currency, rating, review_count, availability, category, delivery, images, url, etc. With `--parse false`: raw HTML. See [reference/amazon/product-output.md](reference/amazon/product-output.md).
