# Walmart Search API

Search Walmart products. JSON output. **Credit:** 10–15 per request. Use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee walmart-search --output-file search.json "headphones" --min-price 20 --max-price 100
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

JSON: `meta_data` (url, number_of_results, page, total_pages), `products` (position, title, price, url, brand, etc.), `facets`, `location`. See [reference/walmart/search-output.md](reference/walmart/search-output.md).

```json
{
  "meta_data": {"url": "https://www.walmart.com/search?q=headphones", "number_of_results": 100, "page": 1, "total_pages": 5},
  "products": [
    {
      "id": "921722537",
      "position": 1,
      "title": "Product Name",
      "price": 29.97,
      "url": "/ip/product-name/921722537",
      "brand": "Brand Name",
      "rating": 4.3,
      "rating_count": 567
    }
  ],
  "facets": [],
  "location": "United States"
}
```
