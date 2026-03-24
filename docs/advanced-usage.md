# Advanced Usage Examples

Real-world workflows combining `scrapingbee` with standard shell tools. For basic usage and installation, see [README.md](../README.md).

---

## Piping and Text Processing

### Extract titles and filter by keyword

```bash
scrapingbee scrape "https://news.ycombinator.com/" \
  --extract-rules '{"titles":{"selector":".titleline > a","type":"list"}}' \
  --extract-field titles \
  | grep -i "python\|rust\|linux\|ai"
```

### Count links on a page

```bash
scrapingbee scrape "https://example.com" --preset extract-links \
  --extract-field links | wc -l
```

### Extract domains from Google results

```bash
scrapingbee google "web scraping tools" \
  --extract-field "organic_results.url" \
  | awk -F/ '{print $3}' | sort -u
```

### Format extraction output as markdown list

```bash
scrapingbee scrape "https://news.ycombinator.com/" \
  --extract-rules '{"titles":{"selector":".titleline > a","type":"list"}}' \
  --extract-field titles \
  | sed 's/^/- /'
```

---

## Chaining Commands

### Google search → scrape each result as markdown

```bash
scrapingbee google "scrapingbee tutorial" \
  --extract-field "organic_results.url" \
  | head -3 \
  | scrapingbee scrape --input-file - \
      --render-js false --return-page-markdown true \
      --output-dir tutorial_pages/
```

### Google search → scrape → extract with AI

```bash
scrapingbee google "best restaurants paris" \
  --extract-field "organic_results.url" \
  | head -5 \
  | scrapingbee scrape --input-file - \
      --render-js false \
      --ai-query "list of restaurant names and addresses" \
      --output-format ndjson
```

---

## Batch Processing

### Scrape URLs from a file

```bash
scrapingbee scrape --input-file urls.txt \
  --render-js false \
  --return-page-text true \
  --output-dir scraped_text/ \
  --concurrency 10
```

### Process CSV input, augment in-place

```bash
# Input CSV has columns: url,company_name
# --update-csv adds extracted data as new columns
scrapingbee scrape --input-file companies.csv \
  --input-column url \
  --render-js false \
  --extract-rules '{"title":"h1","description":"meta[name=description]@content"}' \
  --update-csv
```

### Random sample from large URL list

```bash
scrapingbee scrape --input-file 10k_urls.txt \
  --render-js false --sample 50 \
  --output-format ndjson \
  | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    print(f\"{d['status_code']} {d['latency_ms']}ms {d['input']}\")
"
```

### Deduplicate and resume interrupted batches

```bash
cat urls_*.txt \
  | scrapingbee scrape --input-file - \
      --render-js false --deduplicate \
      --output-dir deduped_results/ \
      --resume
```

`--resume` skips items already saved in `--output-dir` from a previous run.

---

## NDJSON Streaming Pipelines

### Stream results and process each line

```bash
scrapingbee scrape --input-file urls.txt \
  --render-js false --output-format ndjson \
  | while IFS= read -r line; do
      url=$(echo "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['input'])")
      status=$(echo "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['status_code'])")
      echo "$status $url"
    done
```

### Transform each result with --post-process

```bash
# Extract just the page title from each scraped page
scrapingbee scrape --input-file urls.txt \
  --render-js false --output-format ndjson \
  --post-process 'python3 -c "
import sys, re
html = sys.stdin.read()
m = re.search(r\"<title>(.*?)</title>\", html, re.IGNORECASE)
print(m.group(1) if m else \"(no title)\")
"'
```

---

## Monitoring and Diffing

### Detect content changes on a page

```bash
#!/bin/bash
URL="https://news.ycombinator.com/"
SNAP="/tmp/hn_snapshot.txt"
RULES='{"titles":{"selector":".titleline > a","type":"list"}}'

new=$(scrapingbee scrape "$URL" --extract-rules "$RULES" --extract-field titles 2>/dev/null)

if [ -f "$SNAP" ]; then
  diff <(cat "$SNAP") <(echo "$new") && echo "No changes" || echo "Page updated!"
fi
echo "$new" > "$SNAP"
```

### Monitor price changes

```bash
#!/bin/bash
URL="https://example.com/product"
PREV="/tmp/price_prev.txt"

price=$(scrapingbee scrape "$URL" \
  --ai-query "current price of the product" \
  --render-js false 2>/dev/null)

if [ -f "$PREV" ] && [ "$(cat "$PREV")" != "$price" ]; then
  echo "Price changed: $(cat "$PREV") → $price"
fi
echo "$price" > "$PREV"
```

---

## Screenshots

### Screenshot to file via redirect

```bash
scrapingbee scrape "https://example.com" \
  --screenshot true 2>/dev/null > page.png
```

### Full-page screenshot

```bash
scrapingbee scrape "https://example.com" \
  --screenshot true --screenshot-full-page true \
  --output-file fullpage.png
```

### Screenshot + HTML in one request

```bash
scrapingbee scrape "https://example.com" \
  --preset screenshot-and-html \
  --output-file result.json

# Extract the screenshot:
python3 -c "
import json, base64
with open('result.json') as f:
    data = json.load(f)
with open('screenshot.png', 'wb') as f:
    f.write(base64.b64decode(data['screenshot']))
print(f\"HTML length: {len(data['body'])} chars\")
"
```

---

## Scripting Patterns

### Credit budget check before batch

```bash
#!/bin/bash
set -e

credits=$(scrapingbee usage 2>/dev/null \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['max_api_credit']-d['used_api_credit'])")
url_count=$(wc -l < urls.txt)
cost=$((url_count * 1))  # 1 credit each with render_js=false

echo "Need ~$cost credits, have $credits"
if [ "$cost" -gt "$credits" ]; then
  echo "Not enough credits!" >&2
  exit 1
fi

scrapingbee scrape --input-file urls.txt --render-js false --output-dir results/
```

### Custom retry logic

```bash
#!/bin/bash
URL="https://example.com"
MAX_RETRIES=3

for i in $(seq 1 $MAX_RETRIES); do
  if result=$(scrapingbee scrape "$URL" --render-js false 2>/dev/null); then
    echo "$result"
    exit 0
  fi
  echo "Attempt $i failed, retrying..." >&2
  sleep $((i * 2))
done
echo "All $MAX_RETRIES attempts failed" >&2
exit 1
```

> **Note:** The CLI has built-in `--retries` and `--backoff` flags, so manual retry is only needed for custom logic.

---

## Google Search Workflows

### Compare search results across countries

```bash
for cc in us gb de fr; do
  echo "=== $cc ==="
  scrapingbee google "best vpn" --country-code $cc \
    --extract-field "organic_results.title" 2>/dev/null | head -3
done
```

### Search and summarize with AI

```bash
scrapingbee google "climate change" --search-type news \
  --extract-field "organic_results.url" 2>/dev/null \
  | head -3 \
  | scrapingbee scrape --input-file - --render-js false \
      --ai-query "one-sentence summary of the article" \
      --output-format ndjson 2>/dev/null \
  | python3 -c "
import sys, json
for line in sys.stdin:
    d = json.loads(line)
    print(f\"[{d['input'][:60]}]\")
    print(f\"  {d['body']}\")
    print()
"
```

### Google AI mode

```bash
scrapingbee google "how does CRISPR work" --search-type ai-mode \
  --extract-field "ai_mode_answer.response_text"
```

---

## Export and Format Conversion

### Merge batch output to single NDJSON file

```bash
scrapingbee export --input-dir batch_results/ --format ndjson --output-file all.ndjson
```

### Flatten nested JSON to CSV

```bash
scrapingbee export --input-dir batch_results/ --format csv --flatten --output-file flat.csv
```

### Select specific CSV columns

```bash
scrapingbee export --input-dir batch_results/ --format csv --flatten \
  --columns "_url,title,description" --output-file selected.csv
```

---

## LLM / RAG Chunking

### Split page into chunks for embeddings

```bash
scrapingbee scrape "https://en.wikipedia.org/wiki/Web_scraping" \
  --return-page-markdown true \
  --chunk-size 1000 --chunk-overlap 100 \
  | python3 -c "
import sys, json
for line in sys.stdin:
    chunk = json.loads(line)
    print(f\"Chunk {chunk['chunk_index']}/{chunk['total_chunks']}: {len(chunk['content'])} chars\")
"
```

---

## Presets

```bash
# Fastest possible scrape (no JS rendering, 1 credit)
scrapingbee scrape URL --preset fetch

# Get all links on a page
scrapingbee scrape URL --preset extract-links --extract-field links

# Get all emails on a page
scrapingbee scrape URL --preset extract-emails --extract-field emails

# Screenshot only
scrapingbee scrape URL --preset screenshot --output-file page.png

# Screenshot + HTML in one request
scrapingbee scrape URL --preset screenshot-and-html --output-file both.json
```

---

## Tips

- **Use `--render-js false`** whenever possible — 1 credit vs 5, and faster. `--preset fetch` is a shorthand.
- **Use `--verbose`** to see credit costs — output goes to stderr so it won't break pipes.
- **Use `--extract-field`** for pipe-friendly output (one value per line) instead of parsing JSON manually.
- **Use `--output-format ndjson`** for streaming batch results to stdout.
- **Use `--deduplicate`** to avoid wasting credits on duplicate URLs in batch input.
- **Use `--sample N`** to test your pipeline on a small subset before running a full batch.
- **Use `--resume`** to restart interrupted batches without re-fetching completed items.
- **Use `--post-process`** to transform each batch result with a shell command.
- **Use `SCRAPINGBEE_API_KEY` env var** in scripts and CI instead of `scrapingbee auth`.
