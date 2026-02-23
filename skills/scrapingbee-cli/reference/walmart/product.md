# Walmart Product API

Fetch a single product by **Walmart product ID**. JSON output. **Credit:** 10–15 per request. Use **`--output-file file.json`** (before command).

## Command

```bash
scrapingbee --output-file product.json walmart-product 123456789 --domain com
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

Structured product object. With `--parse false`: HTML. See [reference/walmart/product-output.md](reference/walmart/product-output.md).
