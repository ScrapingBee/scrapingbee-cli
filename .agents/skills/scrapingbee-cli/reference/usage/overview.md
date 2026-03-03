# Usage (credits and concurrency)

Check credits and max concurrency. Auth is separate (see [reference/auth/overview.md](reference/auth/overview.md)).

## Command

```bash
scrapingbee usage
```

Shows available credits and max concurrency. Run **before large batches or crawls**. CLI **won't start a batch** if credits are below the minimum required (100); see [rules/security.md](rules/security.md).

**Global retries:** `--retries N` and `--backoff F` apply to this command and all other API commands (google, amazon, walmart, youtube, chatgpt, etc.). Example: `scrapingbee --retries 2 usage`.

## When to use

- Before running batch (scrape, google, amazon, etc. with `--input-file`).
- Before crawl.
- To confirm plan limits (concurrency, credits).

Install and troubleshooting: [rules/install.md](rules/install.md). Security: [rules/security.md](rules/security.md).
