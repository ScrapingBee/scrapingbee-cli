# Walmart Search API

Search Walmart products. JSON output. **Credit:** 10–15 per request. Use **`--output-file file.json`** (before command).

## Command

```bash
scrapingbee --output-file search.json walmart-search "headphones" --min-price 20 --max-price 100
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--min-price` / `--max-price` | int | Price filter. |
| `--sort-by` | string | `best_match`, `price_low`, `price_high`, `best_seller`. |
| `--device` | string | `desktop`, `mobile`, or `tablet`. |
| `--domain` | string | Walmart domain. |
| `--fulfillment-speed` | string | `today`, `tomorrow`, `2_days`, `anytime`. |
| `--fulfillment-type` | string | e.g. `in_store`. |
| `--delivery-zip` / `--store-id` | string | Delivery or store. |
| `--add-html` / `--light-request` / `--screenshot` | true/false | Optional. |

## Batch

`--input-file` (one query per line) + `--output-dir`. Output: `N.json`.

## Output

JSON: `meta_data` (url, number_of_results, page, total_pages), `products` (position, title, price, url, brand, etc.), `facets`, `location`. With `--parse false`: HTML. See [reference/walmart/search-output.md](reference/walmart/search-output.md).
