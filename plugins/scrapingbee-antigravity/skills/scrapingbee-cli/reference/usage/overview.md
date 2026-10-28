# Usage (credits and concurrency)

Check credits and max concurrency. Auth is separate (see [reference/auth/overview.md](reference/auth/overview.md)).

## Command

```bash
scrapingbee usage
```

Shows available credits and max concurrency. Run **before large batches or crawls**. CLI **won't start a batch** if credits are below the minimum required (100); see [rules/security.md](rules/security.md).

**Retries:** `--retries N` and `--backoff F` are available on this command and on every other API command (google, amazon, walmart, youtube, chatgpt, etc.), but they belong to the subcommand — pass them after it. Example: `scrapingbee usage --retries 2`.

## When to use

- Before running batch (scrape, google, amazon, etc. with `--input-file`).
- Before crawl.
- To confirm plan limits (concurrency, credits).

Install and troubleshooting: [rules/install.md](rules/install.md). Security: [rules/security.md](rules/security.md).
