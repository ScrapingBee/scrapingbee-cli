# Amazon Product API

Fetch a single product by **ASIN**. JSON output. **Credit:** 5–15 per request. Use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee amazon-product --output-file product.json B0DPDRNSXV --domain com
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

JSON: asin, brand, title, description, bullet_points, price, currency, rating, review_count, availability, category, delivery, images, url, etc. See [reference/amazon/product-output.md](reference/amazon/product-output.md).

```json
{
  "asin": "B0DPDRNSXV",
  "title": "Product Name",
  "brand": "Brand Name",
  "description": "Full description...",
  "bullet_points": ["Feature 1", "Feature 2"],
  "price": 29.99,
  "currency": "USD",
  "rating": 4.5,
  "review_count": 1234,
  "availability": "In Stock",
  "category": "Electronics",
  "images": ["https://m.media-amazon.com/images/..."],
  "url": "https://www.amazon.com/dp/B0DPDRNSXV"
}
```
