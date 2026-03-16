# Walmart Search API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

Search Walmart products. JSON output. **Credit:** 10–15 per request. Use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee walmart-search --output-file search.json "headphones" --min-price 20 --max-price 100
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--min-price` / `--max-price` | int | Price filter. |
| `--sort-by` | string | `best-match`, `price-low`, `price-high`, `best-seller`. |
| `--device` | string | `desktop`, `mobile`, or `tablet`. |
| `--domain` | string | Walmart domain. |
| `--fulfillment-speed` | string | `today`, `tomorrow`, `2-days`, `anytime`. |
| `--fulfillment-type` | string | e.g. `in_store`. |
| `--delivery-zip` / `--store-id` | string | Delivery or store. |
| `--add-html` / `--light-request` / `--screenshot` | true/false | Optional. |

## Pipeline: search → product details

```bash
# Extract product IDs and fetch full product details for each (no jq)
scrapingbee walmart-search --extract-field products.id "laptop" > ids.txt
scrapingbee walmart-product --output-dir products --input-file ids.txt

# Export to CSV for spreadsheet analysis
scrapingbee export --output-file products.csv --input-dir products --format csv
```

Use `--extract-field products.id` or `--fields id,title,price,rating` to narrow output.

## Batch

`--input-file` (one query per line) + `--output-dir`. Output: `N.json`.

## Output

JSON: `products` (array), `products_count`, `page`, `url`, `location`, `html`, `screenshot`. Batch: output is `N.json` in batch folder.

```json
{
  "url": "https://www.walmart.com/search?q=headphones",
  "page": 1,
  "products_count": 40,
  "products": [
    {
      "id": "921722537",
      "position": 1,
      "title": "Product Name",
      "price": 29.97,
      "url": "/ip/product-name/921722537",
      "rating": 4.3,
      "rating_count": 567,
      "seller_name": "Walmart.com"
    }
  ],
  "location": "United States"
}
```
