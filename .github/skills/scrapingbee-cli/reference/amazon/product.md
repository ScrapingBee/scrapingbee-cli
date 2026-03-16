# Amazon Product API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

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
| `--country` | string | Country code (e.g. gb, de). **Must not match domain** — e.g. don't use `--country us` with `--domain com`. Use `--zip-code` instead when the country matches the domain. |
| `--zip-code` | string | ZIP/postal code for local availability/pricing. Use this instead of `--country` when targeting the domain's own country. |
| `--language` | string | e.g. en_US, es_US, fr_FR. |
| `--currency` | string | USD, EUR, GBP, etc. |
| `--add-html` | true/false | Include full HTML. |
| `--light-request` | true/false | Light request. |
| `--screenshot` | true/false | Take screenshot. |

## Batch

`--input-file` (one ASIN per line) + `--output-dir`. Output: `N.json`.

## Output

JSON: asin, brand, title, description, bullet_points, price, currency, rating, reviews_count, stock, category, delivery, images, url, reviews, variations, buybox, product_details, sales_rank, rating_stars_distribution, product_overview, technical_details, discount_percentage, is_prime, parent_asin, etc. Batch: output is `N.json` in batch folder.

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
  "reviews_count": 1234,
  "stock": "In Stock",
  "category": "Electronics",
  "images": ["https://m.media-amazon.com/images/..."],
  "url": "https://www.amazon.com/dp/B0DPDRNSXV",
  "reviews": [{"title": "Great product", "rating": 5, "body": "..."}],
  "is_prime": true,
  "discount_percentage": 10
}
```
