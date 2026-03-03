# Walmart Product API

Fetch a single product by **Walmart product ID**. JSON output. **Credit:** 10–15 per request. Use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee walmart-product --output-file product.json 123456789 --domain com
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--domain` | string | Walmart domain. |
| `--delivery-zip` / `--store-id` | string | Delivery or store. |
| `--add-html` / `--light-request` / `--screenshot` | true/false | Optional. |

## Batch

`--input-file` (one product ID per line) + `--output-dir`. Output: `N.json`.

## Output

Structured product object. See [reference/walmart/product-output.md](reference/walmart/product-output.md).

```json
{
  "id": "123456789",
  "title": "Product Name",
  "brand": "Brand Name",
  "price": 29.97,
  "currency": "USD",
  "rating": 4.3,
  "review_count": 567,
  "availability": "In Stock",
  "description": "Full description...",
  "images": ["https://i5.walmartimages.com/..."],
  "url": "https://www.walmart.com/ip/product-name/123456789"
}
```
