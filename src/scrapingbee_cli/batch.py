"""Batch mode: read input file, run concurrent requests, write output (async)."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import click

from .client import Client, parse_usage
from .config import BASE_URL, get_api_key

# Map Content-Type (main part, lowercased) to file extension for batch output.
CONTENT_TYPE_EXTENSION: dict[str, str] = {
    "application/json": "json",
    "application/ld+json": "json",
    "text/html": "html",
    "text/markdown": "md",
    "text/plain": "txt",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "application/pdf": "pdf",
    "application/zip": "zip",
}

# HTML API (scrape) can return multiple types. Put images in screenshots/, other binary in files/.
SCREENSHOT_EXTENSIONS = frozenset({"png", "jpg", "gif", "webp"})
BINARY_FILE_EXTENSIONS = frozenset({"pdf", "zip"})

# Known file extensions for URL path detection (e.g. index.html, sitemap.xml, archive.zip).
URL_PATH_EXTENSIONS = frozenset(
    {
        "html",
        "htm",
        "xml",
        "json",
        "zip",
        "pdf",
        "md",
        "txt",
        "svg",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "ico",
        "css",
        "js",
    }
)


def _batch_subdir_for_extension(ext: str) -> str | None:
    """Return 'screenshots', 'files', or None (write to batch root). Only for scrape-like output."""
    if ext in SCREENSHOT_EXTENSIONS:
        return "screenshots"
    if ext in BINARY_FILE_EXTENSIONS:
        return "files"
    return None


def extension_from_content_type(headers: dict) -> str:
    """Return file extension from response headers, or 'bin' if unknown."""
    raw = ""
    for k, v in headers.items():
        if k.lower() == "content-type" and v:
            raw = v if isinstance(v, str) else str(v)
            break
    main = raw.split(";")[0].strip().lower()
    if main in CONTENT_TYPE_EXTENSION:
        return CONTENT_TYPE_EXTENSION[main]
    return "bin"


def _looks_like_json(body: bytes) -> bool:
    """True if body starts with { or [ and next token looks like JSON
    (not e.g. Markdown [text](url))."""
    if not body:
        return False
    body = body.lstrip()
    if body[:1] not in (b"{", b"["):
        return False
    rest = body[1:].lstrip()
    # Empty object {} or array [] or just "{" / "[" (minimal valid start)
    if not rest:
        return True
    # After [ or {, next non-whitespace must be a JSON value starter or closing } ]
    first = rest[0:1]
    return first in (
        b'"',
        b"{",
        b"[",
        b"}",
        b"]",
        b"0",
        b"1",
        b"2",
        b"3",
        b"4",
        b"5",
        b"6",
        b"7",
        b"8",
        b"9",
        b"-",
        b"n",
        b"t",
        b"f",
    )


def _looks_like_markdown(body: bytes) -> bool:
    """True if body looks like Markdown (e.g. [text](url) link syntax).
    ScrapingBee may not send correct Content-Type.

    Note: this heuristic is intentionally simple — a leading `[` followed by
    `](` anywhere in the first 2 KB.  It can produce false positives for
    unusual JSON arrays or other formats that start with `[`.  The tradeoff is
    acceptable here because (a) this is a last-resort fallback after MIME-type
    and magic-byte checks, and (b) misidentifying such a body as markdown only
    affects the output file extension, not the content.
    """
    if not body or body[:1] != b"[":
        return False
    # Markdown link pattern ]( in first 2KB is a strong signal
    chunk = body.lstrip()[:2048]
    return b"](" in chunk


def extension_from_body_sniff(body: bytes) -> str | None:
    """Return extension if body has obvious magic bytes; else None (API type can be wrong)."""
    if not body:
        return None
    body = body.lstrip()
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if body[:2] == b"\xff\xd8":
        return "jpg"
    if body[:4] == b"GIF8":
        return "gif"
    if len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "webp"
    if _looks_like_json(body):
        return "json"
    if _looks_like_markdown(body):
        return "md"
    if body.startswith(b"<!") or body.startswith(b"<html") or body.startswith(b"<HTML"):
        return "html"
    return None


def extension_for_scrape(headers: dict, body: bytes) -> str:
    """Infer extension for scrape: body sniff first, then Content-Type, else bin."""
    from_header = extension_from_content_type(headers)
    sniffed = extension_from_body_sniff(body)
    if sniffed is not None:
        return sniffed
    if from_header != "bin":
        return from_header
    return "bin"


def extension_from_url_path(url: str) -> str | None:
    """Return file extension from the last path segment of URL, or None if unknown.
    E.g. index.html -> html, sitemap.xml -> xml, archive.zip -> zip.
    """
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    last = path.split("/")[-1]
    if "." not in last:
        return None
    _, _, ext = last.rpartition(".")
    ext = ext.lower().split("?")[0]
    return ext if ext in URL_PATH_EXTENSIONS else None


def extension_for_crawl(
    url: str,
    headers: dict,
    body: bytes,
    preferred_extension: str | None,
) -> str:
    """Extension for crawl: 1) preferred (from scrape params), 2) URL path, 3) body/Content-Type."""
    if preferred_extension:
        return preferred_extension
    from_url = extension_from_url_path(url)
    if from_url is not None:
        return from_url
    return extension_for_scrape(headers, body)


def read_input_file(path: str, *, input_column: str | None = None) -> list[str]:
    """Read non-empty trimmed lines from file or stdin (use '-' for stdin).
    If path ends with .csv, read as CSV using input_column (name or 0-based index)."""
    import sys as _sys

    if path == "-":
        lines = [line.strip() for line in _sys.stdin if line.strip()]
    elif path.lower().endswith(".csv"):
        import csv

        try:
            fh = open(path, encoding="utf-8", newline="")
        except OSError as e:
            raise ValueError(f'cannot open input file "{path}": {e}') from e
        with fh:
            reader = csv.reader(fh)
            rows = list(reader)
        if not rows:
            raise ValueError(f'input file "{path}" has no rows')
        # Determine column index
        col_idx = 0
        if input_column is not None:
            if input_column.isdigit():
                col_idx = int(input_column)
            else:
                # Treat first row as header
                header = [c.strip() for c in rows[0]]
                if input_column in header:
                    col_idx = header.index(input_column)
                    rows = rows[1:]  # skip header row
                else:
                    raise ValueError(f'column "{input_column}" not found in CSV header: {header}')
        lines = []
        for row in rows:
            if col_idx < len(row) and row[col_idx].strip():
                lines.append(row[col_idx].strip())
    else:
        try:
            fh = open(path, encoding="utf-8")
        except OSError as e:
            raise ValueError(f'cannot open input file "{path}": {e}') from e
        with fh:
            lines = [line.strip() for line in fh if line.strip()]
    if not lines:
        raise ValueError(f'input file "{path}" has no non-empty lines')
    return lines


def _normalize_url_for_dedup(url: str) -> str:
    """Normalize a URL for deduplication: lowercase domain, strip fragment, strip trailing slash."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme:
            return url  # not a URL (query, ASIN, etc.) — return as-is
        normalized = parsed._replace(
            netloc=parsed.netloc.lower(),
            fragment="",
        )
        result = normalized.geturl()
        return result.rstrip("/") if result.endswith("/") else result
    except Exception:
        return url


def deduplicate_inputs(inputs: list[str]) -> tuple[list[str], int]:
    """Normalize and deduplicate inputs, preserving order (first occurrence wins).
    Returns (deduped_list, removed_count)."""
    seen: set[str] = set()
    deduped: list[str] = []
    for item in inputs:
        key = _normalize_url_for_dedup(item)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped, len(inputs) - len(deduped)


def sample_inputs(inputs: list[str], n: int) -> list[str]:
    """Return a random sample of n items from inputs (or all if n >= len)."""
    import random

    if n <= 0 or n >= len(inputs):
        return inputs
    return random.sample(inputs, n)


async def _fetch_usage_async(api_key: str) -> dict:
    """Fetch usage from API (async)."""
    async with Client(api_key) as client:
        body, _, code = await client.usage()
        if code != 200:
            raise RuntimeError(f"usage API returned HTTP {code}")
        return parse_usage(body)


# Cache usage API responses to avoid hitting the 6 calls/min rate limit.
_usage_cache: dict | None = None
_usage_cache_time: float = 0
_USAGE_CACHE_TTL = 30  # seconds


def get_batch_usage(api_key_flag: str | None) -> dict:
    """Return usage info (max_concurrency, credits) from usage API.

    Caches the result for 30 seconds to avoid hitting the usage API
    rate limit (6 calls/min).
    """
    global _usage_cache, _usage_cache_time  # noqa: PLW0603
    now = time.monotonic()
    if _usage_cache is not None and (now - _usage_cache_time) < _USAGE_CACHE_TTL:
        return _usage_cache
    key = get_api_key(api_key_flag)
    result = asyncio.run(_fetch_usage_async(key))
    _usage_cache = result
    _usage_cache_time = now
    return result


MIN_CREDITS_TO_RUN_BATCH = 100


def validate_batch_run(user_concurrency: int, num_inputs: int, usage: dict) -> None:
    """Raise ValueError if batch should not run (concurrency or credits).
    Credits: block when balance is below MIN_CREDITS_TO_RUN_BATCH (we cannot
    reliably estimate cost for batch/crawl). Concurrency: block when user
    --concurrency exceeds plan limit."""
    max_concurrency = usage.get("max_concurrency", 5)
    if user_concurrency > 0 and user_concurrency > max_concurrency:
        raise ValueError(
            f"concurrency {user_concurrency} exceeds your plan limit of {max_concurrency} "
            "(check with: scrapingbee usage)"
        )
    credits = usage.get("credits", 0)
    if credits < MIN_CREDITS_TO_RUN_BATCH:
        raise ValueError(
            f"insufficient credits: {credits} available (need at least {MIN_CREDITS_TO_RUN_BATCH} to run batch). "
            "Check with: scrapingbee usage"
        )


CONCURRENCY_CAP = 100


def resolve_batch_concurrency(
    user_concurrency: int, usage: dict, num_inputs: int, *, warn: bool = True
) -> int:
    """Return concurrency to use: user value if set (capped at plan limit and CONCURRENCY_CAP),
    else usage limit (at least 1). When from user, caps at min(plan_limit, CONCURRENCY_CAP)."""
    from_usage = usage.get("max_concurrency", 5) or 5
    if user_concurrency > 0:
        cap = min(from_usage, CONCURRENCY_CAP)
        if user_concurrency > cap and warn:
            click.echo(
                f"Warning: concurrency capped at {cap} (plan limit or max {CONCURRENCY_CAP}). "
                "Very high concurrency can overload your network.",
                err=True,
            )
        return min(user_concurrency, cap)
    return max(1, from_usage)


@dataclass
class BatchResult:
    """Result of one batch item."""

    index: int
    input: str
    body: bytes
    headers: dict
    status_code: int
    error: Exception | None
    # When set, use this extension (per-documentation type). When None, infer for scrape only.
    expected_extension: str | None = None
    # True when item was skipped because its output already exists (--resume mode).
    skipped: bool = False
    # ISO-8601 UTC timestamp of when the request was made (empty when skipped).
    fetched_at: str = ""
    # Response latency in milliseconds (None when skipped).
    latency_ms: int | None = None


AsyncBatchFn = Callable[[str], Awaitable[tuple[bytes, dict, int, Exception | None, str | None]]]


def _find_completed_n(output_dir: str) -> frozenset[int]:
    """Return 1-based item indices that already have output (non-.err) files in output_dir.
    Used by --resume to skip already-completed batch items."""
    try:
        base = Path(output_dir).resolve()
        if not base.is_dir():
            return frozenset()
    except Exception:
        return frozenset()
    completed: set[int] = set()
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lstrip(".") == "err":
            continue
        try:
            completed.add(int(p.stem))
        except ValueError:
            continue
    return frozenset(completed)


def _format_eta(seconds: float) -> str:
    """Format seconds as human-readable duration (e.g. '2h 5m', '45s', '3m 10s')."""
    if seconds < 0:
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s" if s else f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if m else f"{h}h"


async def run_batch_async(
    inputs: list[str],
    concurrency: int,
    async_fn: AsyncBatchFn,
    *,
    from_user: bool = False,
    skip_n: frozenset[int] = frozenset(),
    show_progress: bool = True,
    on_result: Callable[[BatchResult], None] | None = None,
) -> list[BatchResult]:
    """Run async_fn for each input with up to concurrency in flight; preserve order."""
    concurrency = min(max(1, concurrency), len(inputs))
    source = "from --concurrency" if from_user else "from usage API"
    total = len(inputs)
    click.echo(f"Batch: {total} items, concurrency {concurrency} ({source})", err=True)
    sem = asyncio.Semaphore(concurrency)
    completed = 0
    failure_count = 0
    start_time = time.monotonic()

    async def run_one(i: int, inp: str) -> tuple[int, BatchResult]:
        nonlocal completed, failure_count
        if i + 1 in skip_n:
            result = BatchResult(
                index=i,
                input=inp,
                body=b"",
                headers={},
                status_code=0,
                error=None,
                skipped=True,
            )
        else:
            async with sem:
                t0 = time.monotonic()
                fetched_at = datetime.now(timezone.utc).isoformat()
                try:
                    body, headers, status_code, err, expected_ext = await async_fn(inp)
                except Exception as e:
                    body, headers, status_code, err, expected_ext = b"", {}, 0, e, None
                latency_ms = int((time.monotonic() - t0) * 1000)
            result = BatchResult(
                index=i,
                input=inp,
                body=body,
                headers=headers,
                status_code=status_code,
                error=err,
                expected_extension=expected_ext,
                fetched_at=fetched_at,
                latency_ms=latency_ms,
            )
        completed += 1
        if result.error and not result.skipped:
            failure_count += 1
        if show_progress:
            elapsed = time.monotonic() - start_time
            parts = [f"[{completed}/{total}]"]
            if elapsed > 0:
                rps = completed / elapsed
                parts.append(f"{rps:.0f} req/s")
                remaining = total - completed
                if rps > 0 and remaining > 0:
                    parts.append(f"ETA {_format_eta(remaining / rps)}")
            if failure_count > 0:
                pct = failure_count / completed * 100
                parts.append(f"Failures: {pct:.0f}%")
            click.echo(f"  {' | '.join(parts)}", err=True)
        if on_result is not None:
            on_result(result)
        return i, result

    tasks = [run_one(i, inp) for i, inp in enumerate(inputs)]
    ordered = await asyncio.gather(*tasks, return_exceptions=True)
    results: list[BatchResult] = []
    for item in ordered:
        if isinstance(item, BaseException):
            continue
        _, result = item
        results.append(result)
    return results


def default_batch_output_dir() -> str:
    """Default folder name for batch output (batch_<timestamp>)."""
    return "batch_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _credits_used_from_headers(headers: dict) -> int | None:
    """Extract the Spb-Cost header value as an int, or None."""
    for k, v in headers.items():
        if k.lower() == "spb-cost" and v:
            try:
                return int(v)
            except (ValueError, TypeError):
                return None
    return None


def write_batch_output_to_dir(
    results: list[BatchResult],
    output_dir: str | None,
    verbose: bool,
    post_process: str | None = None,
) -> tuple[str, int, int]:
    """Write 1.<ext>, 2.<ext>, ... and N.err for failures.  Returns ``(output_dir, succeeded, failed)``.

    Writes failures.txt at the end listing each failed item (index, input, error). Each N.err
    is a JSON object with ``error``, ``status_code``, ``body``, and ``input`` keys.
    Writes manifest.json mapping each input to its file path plus fetched_at, http_status,
    credits_used, latency_ms, and content_md5.
    """
    import json as _json

    output_dir = output_dir or default_batch_output_dir()
    abs_dir = str(Path(output_dir).resolve())
    os.makedirs(abs_dir, exist_ok=True)

    # Load existing manifest from output_dir to carry forward skipped (--resume) entries.
    existing_manifest: dict = {}
    existing_manifest_path = os.path.join(abs_dir, "manifest.json")
    if os.path.exists(existing_manifest_path):
        try:
            with open(existing_manifest_path, encoding="utf-8") as mf:
                existing_manifest = _json.load(mf)
        except Exception:
            existing_manifest = {}

    failures: list[tuple[int, str, str]] = []  # (index+1, input, error_msg)
    manifest: dict[str, dict] = {}
    for result in results:
        n = result.index + 1
        if result.skipped:
            if verbose:
                click.echo(f"Item {n}: skipped (already completed)", err=True)
            if result.input in existing_manifest:
                manifest[result.input] = existing_manifest[result.input]
            continue
        if result.error is not None:
            err_msg = str(result.error)
            failures.append((n, result.input, err_msg))
            click.echo(f"Item {n} ({result.input!r}): {result.error}", err=True)
            err_path = os.path.join(abs_dir, f"{n}.err")
            err_body = ""
            if result.body:
                try:
                    err_body = result.body.decode("utf-8", errors="replace")
                except Exception:
                    err_body = repr(result.body)
            err_obj = {
                "error": err_msg,
                "status_code": result.status_code,
                "input": result.input,
                "body": err_body,
            }
            with open(err_path, "w", encoding="utf-8") as out_file:
                _json.dump(err_obj, out_file, indent=2, ensure_ascii=False)
            continue
        if verbose:
            click.echo(f"Item {n}: HTTP {result.status_code}", err=True)

        credits_used = _credits_used_from_headers(result.headers)
        content_md5 = hashlib.md5(result.body).hexdigest()

        ext = extension_for_crawl(
            result.input,
            result.headers,
            result.body,
            result.expected_extension,
        )
        subdir = _batch_subdir_for_extension(ext)
        if subdir:
            out_dir = os.path.join(abs_dir, subdir)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{n}.{ext}")
            rel = f"{subdir}/{n}.{ext}"
        else:
            out_path = os.path.join(abs_dir, f"{n}.{ext}")
            rel = f"{n}.{ext}"
        write_body = apply_post_process(result.body, post_process) if post_process else result.body
        with open(out_path, "wb") as out_file:
            out_file.write(write_body)
        manifest[result.input] = {
            "file": rel,
            "fetched_at": result.fetched_at,
            "http_status": result.status_code,
            "credits_used": credits_used,
            "latency_ms": result.latency_ms,
            "content_md5": content_md5,
        }
    if failures:
        failures_path = os.path.join(abs_dir, "failures.txt")
        with open(failures_path, "w", encoding="utf-8") as f:
            f.write("Batch failures (index, input, error):\n\n")
            for n, inp, err_msg in failures:
                f.write(f"  {n}. {inp!r}\n    {err_msg}\n\n")
    if manifest:
        manifest_path = os.path.join(abs_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            _json.dump(manifest, f, indent=2, ensure_ascii=False)
    succeeded = len(manifest)
    failed = len(failures)
    return abs_dir, succeeded, failed


def update_csv_with_results(
    csv_path: str,
    input_column: str | None,
    results: list[BatchResult],
    output_path: str | None = None,
) -> tuple[str, int, int]:
    """Read a CSV, merge fresh API response data into each row, write back.
    Returns (output_path, succeeded, failed)."""
    import csv as _csv
    import json as _json

    # Read original CSV
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = _csv.DictReader(f)
        original_fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # Determine the key column
    col = input_column
    if col is None:
        col = original_fieldnames[0] if original_fieldnames else None
    if col is None or col not in original_fieldnames:
        if col and col.isdigit():
            idx = int(col)
            if idx < len(original_fieldnames):
                col = original_fieldnames[idx]
            else:
                raise ValueError(f"Column index {idx} out of range")
        else:
            raise ValueError(f"Column '{col}' not found in CSV headers: {original_fieldnames}")

    # Build a map from input value → result
    result_map: dict[str, BatchResult] = {}
    for r in results:
        if not r.skipped and not r.error and r.body:
            result_map[r.input] = r

    succeeded = 0
    failed = sum(1 for r in results if r.error and not r.skipped)
    new_fieldnames: dict[str, None] = {k: None for k in original_fieldnames}

    # Merge response data into rows
    for row in rows:
        key_val = row.get(col, "").strip()
        if key_val not in result_map:
            continue
        result = result_map[key_val]
        succeeded += 1
        try:
            body_str = result.body.decode("utf-8", errors="replace")
            data = _json.loads(body_str)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        # Flatten the response and merge into the row
        from .commands.export import _flatten_dict

        flat = _flatten_dict(data)
        for k, v in flat.items():
            row[k] = v
            new_fieldnames[k] = None

    # Write updated CSV
    dest = output_path or csv_path
    fieldnames = list(new_fieldnames)
    with open(dest, "w", encoding="utf-8", newline="") as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return dest, succeeded, failed


def apply_post_process(body: bytes, cmd: str) -> bytes:
    """Run shell command with body as stdin, return stdout. On failure, return original body."""
    import subprocess

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            input=body,
            capture_output=True,
            timeout=30,  # noqa: S602
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return body


def write_ndjson_line(result: BatchResult) -> None:
    """Write a single NDJSON line to stdout for a batch result."""
    import json as _json
    import sys as _sys

    if result.skipped:
        return
    body_str = ""
    if result.body:
        try:
            body_str = result.body.decode("utf-8", errors="replace")
        except Exception:
            body_str = repr(result.body)
    # Try to parse body as JSON so it nests properly
    try:
        body_obj = _json.loads(body_str)
    except (ValueError, TypeError):
        body_obj = body_str
    line = _json.dumps(
        {
            "index": result.index + 1,
            "input": result.input,
            "status_code": result.status_code,
            "body": body_obj,
            "error": str(result.error) if result.error else None,
            "fetched_at": result.fetched_at,
            "latency_ms": result.latency_ms,
        },
        ensure_ascii=False,
    )
    _sys.stdout.write(line + "\n")
    _sys.stdout.flush()


def write_batch_output_csv(
    results: list[BatchResult],
    output_file: str | None,
) -> tuple[str, int, int]:
    """Write batch results as CSV. Returns (output_path, succeeded, failed)."""
    import csv
    import io
    import sys as _sys

    succeeded = 0
    failed = 0
    if output_file:
        fh = open(output_file, "w", encoding="utf-8", newline="")
    else:
        fh = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", newline="")
    try:
        writer = csv.writer(fh)
        writer.writerow(["index", "input", "status_code", "body", "error"])
        for result in results:
            if result.skipped:
                continue
            body_str = ""
            if result.body:
                try:
                    body_str = result.body.decode("utf-8", errors="replace")
                except Exception:
                    body_str = repr(result.body)
            err_str = str(result.error) if result.error else ""
            if result.error:
                failed += 1
            else:
                succeeded += 1
            writer.writerow([result.index + 1, result.input, result.status_code, body_str, err_str])
    finally:
        if output_file:
            fh.close()
    return output_file or "<stdout>", succeeded, failed


ApiCallFn = Callable[[Client, str], Awaitable[tuple[bytes, dict, int]]]


async def _run_api_batch_async(
    key: str,
    inputs: list[str],
    concurrency: int,
    from_user: bool,
    skip_n: frozenset[int],
    output_dir: str | None,
    verbose: bool,
    show_progress: bool,
    api_call: ApiCallFn,
    on_complete: str | None = None,
    output_format: str = "files",
    post_process: str | None = None,
    update_csv_path: str | None = None,
    input_column: str | None = None,
) -> None:
    ndjson_pp = post_process if output_format == "ndjson" else None

    def _ndjson_callback(result: BatchResult) -> None:
        if ndjson_pp and result.body and not result.error:
            body = apply_post_process(result.body, ndjson_pp)
            result = BatchResult(
                index=result.index,
                input=result.input,
                body=body,
                headers=result.headers,
                status_code=result.status_code,
                error=result.error,
                expected_extension=result.expected_extension,
                skipped=result.skipped,
                fetched_at=result.fetched_at,
                latency_ms=result.latency_ms,
            )
        write_ndjson_line(result)

    async with Client(key, BASE_URL, connector_limit=concurrency) as client:

        async def do_one(item: str):
            try:
                data, headers, status_code = await api_call(client, item)
                if status_code >= 400:
                    err = RuntimeError(f"HTTP {status_code}")
                    return data, headers, status_code, err, "json"
                return data, headers, status_code, None, "json"
            except Exception as e:
                return b"", {}, 0, e, "json"

        on_result_cb = _ndjson_callback if output_format == "ndjson" else None
        results = await run_batch_async(
            inputs,
            concurrency,
            do_one,
            from_user=from_user,
            skip_n=skip_n,
            show_progress=show_progress,
            on_result=on_result_cb,
        )

    if update_csv_path:
        out_path, succeeded, failed = update_csv_with_results(
            update_csv_path,
            input_column,
            results,
            output_dir,
        )
        click.echo(f"CSV updated: {succeeded} succeeded, {failed} failed. Output: {out_path}")
    elif output_format == "ndjson":
        succeeded = sum(1 for r in results if not r.error and not r.skipped)
        failed = sum(1 for r in results if r.error and not r.skipped)
        click.echo(f"Batch complete: {succeeded} succeeded, {failed} failed.", err=True)
    elif output_format == "csv":
        if post_process:
            for r in results:
                if r.body and not r.error and not r.skipped:
                    r.body = apply_post_process(r.body, post_process)
        out_path, succeeded, failed = write_batch_output_csv(results, output_dir)
        click.echo(f"Batch complete: {succeeded} succeeded, {failed} failed. Output: {out_path}")
    else:
        out_dir, succeeded, failed = write_batch_output_to_dir(
            results,
            output_dir,
            verbose,
            post_process=post_process,
        )
        click.echo(
            f"Batch complete: {succeeded} succeeded, {failed} failed. Output: {out_dir}",
        )
    if on_complete and output_format == "files" and not update_csv_path:
        from .cli_utils import run_on_complete

        run_on_complete(
            on_complete, output_dir=output_dir or "", succeeded=succeeded, failed=failed
        )
    if failed:
        raise SystemExit(1)


def run_api_batch(
    key: str,
    inputs: list[str],
    concurrency: int,
    from_user: bool,
    skip_n: frozenset[int],
    output_dir: str | None,
    verbose: bool,
    show_progress: bool,
    api_call: ApiCallFn,
    on_complete: str | None = None,
    output_format: str = "files",
    post_process: str | None = None,
    update_csv_path: str | None = None,
    input_column: str | None = None,
) -> None:
    """Run a batch of single-item API calls and write results to an output directory."""
    asyncio.run(
        _run_api_batch_async(
            key=key,
            inputs=inputs,
            concurrency=concurrency,
            from_user=from_user,
            skip_n=skip_n,
            output_dir=output_dir,
            verbose=verbose,
            show_progress=show_progress,
            api_call=api_call,
            on_complete=on_complete,
            output_format=output_format,
            post_process=post_process,
            update_csv_path=update_csv_path,
            input_column=input_column,
        )
    )
