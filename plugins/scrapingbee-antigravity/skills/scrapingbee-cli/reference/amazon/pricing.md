# Amazon Pricing API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

Fetch pricing details for a single product by **ASIN**. JSON output. **Credit:** 5–15 per request. Use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee amazon-pricing --output-file pricing.json B0DPDRNSXV --domain com
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--device` | string | `desktop` (only supported value). |
| `--domain` | string | Amazon domain: `com`, `co.uk`, `de`, `fr`, etc. |
| `--country` | string | Country code (e.g. gb, de). **Must not match domain** — e.g. don't use `--country us` with `--domain com`. Use `--zip-code` instead when the country matches the domain. |
| `--zip-code` | string | ZIP/postal code for local availability/pricing. Use this instead of `--country` when targeting the domain's own country. |
| `--language` | string | e.g. en_US, es_US, fr_FR. |
| `--currency` | string | USD, EUR, GBP, etc. |
| `--add-html` | true/false | Include full HTML. |
| `--light-request` | true/false | Light request. |
| `--tag` | string | Optional label included in API response headers. |

## Batch

`--input-file` (one ASIN per line) + `--output-dir`. Output: `N.json`.

## Output

JSON: pricing-focused fields including price, currency, list_price, discount, availability, seller, buybox, prime eligibility, etc. Batch: output is `N.json` in batch folder.
