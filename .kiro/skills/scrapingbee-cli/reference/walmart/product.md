# Walmart Product API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

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

JSON: id, title, price, currency, rating, review_count, out_of_stock (bool), seller_name, images, url, etc. Batch: output is `N.json` in batch folder.

```json
{
  "id": "123456789",
  "title": "Product Name",
  "price": 29.97,
  "currency": "USD",
  "rating": 4.3,
  "review_count": 567,
  "out_of_stock": false,
  "seller_name": "Walmart.com",
  "images": ["https://i5.walmartimages.com/..."],
  "url": "https://www.walmart.com/ip/product-name/123456789"
}
```
