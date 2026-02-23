# Walmart search output

**`scrapingbee walmart-search`** returns JSON: `meta_data` (url, number_of_results, page, total_pages), `products` (position, title, price, url, brand, etc.), `facets`, `location`.

With **`--parse false`**: raw HTML.

Batch: output is `N.json` in batch folder. See [reference/batch/output.md](reference/batch/output.md).
