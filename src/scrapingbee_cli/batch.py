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


def read_input_file(path: str) -> list[str]:
    """Read non-empty trimmed lines from file or stdin (use '-' for stdin)."""
    import sys as _sys

    if path == "-":
        lines = [line.strip() for line in _sys.stdin if line.strip()]
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


async def _fetch_usage_async(api_key: str) -> dict:
    """Fetch usage from API (async)."""
    async with Client(api_key) as client:
        body, _, code = await client.usage()
        if code != 200:
            raise RuntimeError(f"usage API returned HTTP {code}")
        return parse_usage(body)


def get_batch_usage(api_key_flag: str | None) -> dict:
    """Return usage info (max_concurrency, credits) from usage API."""
    key = get_api_key(api_key_flag)
    return asyncio.run(_fetch_usage_async(key))


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


async def run_batch_async(
    inputs: list[str],
    concurrency: int,
    async_fn: AsyncBatchFn,
    *,
    from_user: bool = False,
    skip_n: frozenset[int] = frozenset(),
    show_progress: bool = True,
) -> list[BatchResult]:
    """Run async_fn for each input with up to concurrency in flight; preserve order."""
    concurrency = min(max(1, concurrency), len(inputs))
    source = "from --concurrency" if from_user else "from usage API"
    total = len(inputs)
    click.echo(f"Batch: {total} items, concurrency {concurrency} ({source})", err=True)
    sem = asyncio.Semaphore(concurrency)
    completed = 0

    async def run_one(i: int, inp: str) -> tuple[int, BatchResult]:
        nonlocal completed
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
        if show_progress:
            if result.skipped:
                suffix = " (skipped)"
            elif result.error:
                suffix = " (error)"
            else:
                suffix = ""
            click.echo(f"  [{completed}/{total}]{suffix}", err=True)
        return i, result

    tasks = [run_one(i, inp) for i, inp in enumerate(inputs)]
    ordered = await asyncio.gather(*tasks, return_exceptions=True)
    return [result for _, result in ordered if not isinstance(result, BaseException)]


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
    diff_dir: str | None = None,
) -> str:
    """Write 1.<ext>, 2.<ext>, ... (ext per docs or inferred for scrape) and N.err for failures.
    Writes failures.txt at the end listing each failed item (index, input, error). Each N.err
    starts with the error message line so failures are reported in files as well as stderr.
    Writes manifest.json mapping each input to its file path plus fetched_at, http_status,
    credits_used, latency_ms, and content_md5.

    diff_dir: compare against a previous run; skip writing files whose content is unchanged.
    """
    import json as _json

    output_dir = output_dir or default_batch_output_dir()
    abs_dir = str(Path(output_dir).resolve())

    # Guard: diff_dir must not point at the same directory we're writing to.
    if diff_dir:
        abs_diff = str(Path(diff_dir).resolve())
        if abs_diff == abs_dir:
            raise ValueError(
                f"--diff-dir cannot be the same as the output directory ({abs_dir}). "
                "Use a previous run's directory."
            )

    os.makedirs(abs_dir, exist_ok=True)

    # Load previous manifest for diff detection.
    old_manifest: dict = {}
    if diff_dir:
        old_manifest_path = os.path.join(diff_dir, "manifest.json")
        if os.path.exists(old_manifest_path):
            try:
                with open(old_manifest_path, encoding="utf-8") as mf:
                    old_manifest = _json.load(mf)
            except Exception:
                old_manifest = {}

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
            # Carry forward the existing manifest entry so resume runs keep full history.
            if result.input in existing_manifest:
                manifest[result.input] = existing_manifest[result.input]
            continue
        if result.error is not None:
            err_msg = str(result.error)
            failures.append((n, result.input, err_msg))
            click.echo(f"Item {n} ({result.input!r}): {result.error}", err=True)
            err_path = os.path.join(abs_dir, f"{n}.err")
            with open(err_path, "wb") as out_file:
                out_file.write(f"Error: {err_msg}\n\n".encode())
                if result.body:
                    out_file.write(result.body)
            continue
        if verbose:
            click.echo(f"Item {n}: HTTP {result.status_code}", err=True)

        credits_used = _credits_used_from_headers(result.headers)
        content_md5 = hashlib.md5(result.body).hexdigest()

        # Diff-dir: check whether content changed vs previous run.
        if diff_dir and result.input in old_manifest:
            old_entry = old_manifest[result.input]
            old_md5 = old_entry.get("content_md5")
            if old_md5 and old_md5 == content_md5:
                manifest[result.input] = {
                    "file": None,
                    "fetched_at": result.fetched_at,
                    "http_status": result.status_code,
                    "credits_used": credits_used,
                    "latency_ms": result.latency_ms,
                    "content_md5": content_md5,
                    "unchanged": True,
                }
                continue
            elif old_file := old_entry.get("file"):
                if not old_entry.get("unchanged"):
                    old_file_path = os.path.join(diff_dir, old_file)
                    if os.path.exists(old_file_path):
                        try:
                            old_bytes = Path(old_file_path).read_bytes()
                            if content_md5 == hashlib.md5(old_bytes).hexdigest():
                                manifest[result.input] = {
                                    "file": None,
                                    "fetched_at": result.fetched_at,
                                    "http_status": result.status_code,
                                    "credits_used": credits_used,
                                    "latency_ms": result.latency_ms,
                                    "content_md5": content_md5,
                                    "unchanged": True,
                                }
                                continue
                        except OSError:
                            pass

        # Same order as crawl: preferred (expected) → URL path → body/Content-Type
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
        with open(out_path, "wb") as out_file:
            out_file.write(result.body)
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
    return abs_dir


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
    diff_dir: str | None = None,
) -> None:
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

        results = await run_batch_async(
            inputs,
            concurrency,
            do_one,
            from_user=from_user,
            skip_n=skip_n,
            show_progress=show_progress,
        )
    out_dir = write_batch_output_to_dir(results, output_dir, verbose, diff_dir=diff_dir)
    click.echo(f"Batch complete. Output written to {out_dir}", err=True)


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
    diff_dir: str | None = None,
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
            diff_dir=diff_dir,
        )
    )
