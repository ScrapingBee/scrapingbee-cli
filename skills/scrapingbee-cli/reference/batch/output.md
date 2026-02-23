# Batch output layout

One file per input line (N = line number).

**Scrape:** Extension from body sniff then Content-Type; unknown → `N.unidentified.txt`. PNG/jpg/gif/webp → **`screenshots/`** subfolder; other binary (pdf, zip) → **`files/`**; JSON/HTML/text → batch root (`1.json`, `2.html`, etc.).

**Google, fast-search, amazon, walmart, youtube, chatgpt:** Always **`N.json`** in batch root.

**Failures:** Each failed item is reported on stderr. **`N.err`** in the batch folder contains the error message and (if the API returned a body) that response body

Completion: stdout prints `Batch complete. Output written to <absolute path>`.
