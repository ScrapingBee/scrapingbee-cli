#!/usr/bin/env python3
"""End-to-end test runner for ScrapingBee CLI.

Usage:
    SCRAPINGBEE_API_KEY=your_key uv run python tests/run_e2e_tests.py
    SCRAPINGBEE_API_KEY=your_key uv run python tests/run_e2e_tests.py --filter GG
    SCRAPINGBEE_API_KEY=your_key uv run python tests/run_e2e_tests.py --workers 3

Runs ~182 tests with up to 5 concurrent workers.
Aborts after 10 consecutive failures.
Writes results to TEST_RESULTS.md.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
RESULTS_FILE = PROJECT_ROOT / "TEST_RESULTS.md"
MAX_CONSECUTIVE_FAILURES = 10
DEFAULT_WORKERS = 5
DEFAULT_TIMEOUT = 140  # seconds per test

# ─── Binary detection ─────────────────────────────────────────────────────────


def find_binary() -> str:
    candidates = [
        str(PROJECT_ROOT / ".venv" / "bin" / "scrapingbee"),
        "scrapingbee",
    ]
    for c in candidates:
        try:
            result = subprocess.run([c, "--version"], capture_output=True, timeout=5)
            if result.returncode == 0:
                return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    print("ERROR: 'scrapingbee' binary not found.", file=sys.stderr)
    print("  Install with: pip install -e .", file=sys.stderr)
    sys.exit(1)


# ─── Check helpers ────────────────────────────────────────────────────────────

CheckFn = Callable[[str, str, int], tuple[bool, str]]


def json_key(*keys: str) -> CheckFn:
    """Stdout is valid JSON and all `keys` are present at top level."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        if rc != 0:
            return False, f"exit {rc}"
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            return False, f"invalid JSON: {e}  stdout[:300]={stdout[:300]!r}"
        missing = [k for k in keys if k not in data]
        if missing:
            return False, f"missing keys {missing}; got {list(data.keys())[:15]}"
        return True, f"keys present: {list(keys)}"

    return check


def json_key_either(*alternatives: str) -> CheckFn:
    """At least one of the given top-level keys exists in JSON output."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        if rc != 0:
            return False, f"exit {rc}"
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            return False, f"invalid JSON: {e}  stdout[:300]={stdout[:300]!r}"
        found = [k for k in alternatives if k in data]
        if not found:
            return False, (f"none of {list(alternatives)} in {list(data.keys())[:15]}")
        return True, f"found key(s): {found}"

    return check


def json_key_nested(key: str, subkey: str) -> CheckFn:
    """Stdout JSON has key[subkey] present."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        if rc != 0:
            return False, f"exit {rc}"
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            return False, f"invalid JSON: {e}"
        if key not in data:
            return False, f"key '{key}' missing"
        if not isinstance(data[key], dict) or subkey not in data[key]:
            return False, f"subkey '{subkey}' missing in {key!r}"
        return True, f"nested key {key}.{subkey} found"

    return check


def stdout_contains(pattern: str, case_sensitive: bool = False) -> CheckFn:
    """stdout contains pattern."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        hay = stdout if case_sensitive else stdout.lower()
        needle = pattern if case_sensitive else pattern.lower()
        if needle in hay:
            return True, f"stdout contains {pattern!r}"
        return False, f"pattern {pattern!r} not in stdout[:300]={stdout[:300]!r}"

    return check


def stderr_contains(pattern: str, case_sensitive: bool = False) -> CheckFn:
    """stderr contains pattern."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        hay = stderr if case_sensitive else stderr.lower()
        needle = pattern if case_sensitive else pattern.lower()
        if needle in hay:
            return True, f"stderr contains {pattern!r}"
        return False, f"pattern {pattern!r} not in stderr[:300]={stderr[:300]!r}"

    return check


def exit_ok() -> CheckFn:
    """Exit code is 0."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        if rc == 0:
            return True, "exit 0"
        return False, f"exit {rc}"

    return check


def combined_checks(*checks: CheckFn) -> CheckFn:
    """All checks must pass."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        for fn in checks:
            ok, msg = fn(stdout, stderr, rc)
            if not ok:
                return False, msg
        return True, "all checks passed"

    return check


def file_exists_with(path: str, *patterns: str) -> CheckFn:
    """File at path exists and contains each pattern."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        p = Path(path)
        if not p.exists():
            return False, f"file does not exist: {path}"
        try:
            content = p.read_text(errors="replace")
            for pat in patterns:
                if pat.lower() not in content.lower():
                    return False, f"pattern {pat!r} not in {path}"
        except OSError as e:
            return False, str(e)
        return True, f"file {path} exists with patterns {patterns}"

    return check


def manifest_in(dirpath: str, min_entries: int = 1) -> CheckFn:
    """manifest.json in dirpath has at least min_entries entries."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        manifest = Path(dirpath) / "manifest.json"
        if not manifest.exists():
            return False, f"manifest.json missing in {dirpath}"
        try:
            data = json.loads(manifest.read_text())
            n = len(data)
            if n < min_entries:
                return False, f"manifest has {n} entries, need >= {min_entries}"
            return True, f"manifest has {n} entries"
        except json.JSONDecodeError as e:
            return False, f"manifest JSON error: {e}"

    return check


def ndjson_with_key(key: str, min_lines: int = 1) -> CheckFn:
    """stdout is NDJSON with at least min_lines, each containing key."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        if rc != 0:
            return False, f"exit {rc}"
        lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
        if len(lines) < min_lines:
            return False, f"only {len(lines)} NDJSON lines, need >= {min_lines}"
        for i, line in enumerate(lines):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                return False, f"line {i + 1} is not JSON: {line[:100]!r}"
            if key not in obj:
                return False, f"key {key!r} missing in line {i + 1}"
        return True, f"{len(lines)} NDJSON lines, key {key!r} present"

    return check


def one_url_per_line() -> CheckFn:
    """stdout contains lines that look like URLs (start with http)."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        if rc != 0:
            return False, f"exit {rc}"
        lines = [ln.strip() for ln in stdout.strip().splitlines() if ln.strip()]
        if not lines:
            return False, "empty output"
        non_url = [ln for ln in lines if not ln.startswith("http")]
        if non_url:
            return False, f"non-URL lines: {non_url[:3]}"
        return True, f"{len(lines)} URL lines"

    return check


def lines_contain(pattern: str) -> CheckFn:
    """stdout has lines and each non-empty line contains pattern."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        if rc != 0:
            return False, f"exit {rc}"
        lines = [ln.strip() for ln in stdout.strip().splitlines() if ln.strip()]
        if not lines:
            return False, "empty output"
        missing = [ln for ln in lines if pattern.lower() not in ln.lower()]
        if missing:
            return False, f"line doesn't contain {pattern!r}: {missing[0][:100]!r}"
        return True, f"{len(lines)} lines all contain {pattern!r}"

    return check


def png_magic() -> CheckFn:
    """stdout binary starts with PNG magic bytes."""

    def check(stdout: str, stderr: str, rc: int) -> tuple[bool, str]:
        if rc != 0:
            return False, f"exit {rc}"
        # stdout is text; PNG magic is \x89PNG in raw bytes
        if stdout.startswith("\x89PNG") or "\x89PNG" in stdout[:10]:
            return True, "PNG magic found"
        # also accept if it's non-empty (binary gets mangled in text mode)
        if len(stdout) > 1000:
            return True, f"large binary output ({len(stdout)} chars, likely PNG)"
        return False, f"expected PNG, got {stdout[:30]!r}"

    return check


# ─── Test dataclass ───────────────────────────────────────────────────────────


@dataclass
class Test:
    id: str
    description: str
    args: list[str]  # passed directly to scrapingbee (no shell)
    check: CheckFn
    timeout: int = DEFAULT_TIMEOUT
    env_extra: dict = field(default_factory=dict)
    skip: bool = False
    skip_reason: str = ""


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def create_fixtures() -> dict[str, str]:
    """Create temp files needed by batch tests. Returns a dict of paths."""
    f: dict[str, str] = {}

    # Two-URL scrape fixture
    urls_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    urls_file.write("https://httpbin.org/json\nhttps://httpbin.org/html\n")
    urls_file.close()
    f["urls_file"] = urls_file.name

    # Google batch queries
    gs_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    gs_file.write("python\njavascript\nrust\n")
    gs_file.close()
    f["gs_file"] = gs_file.name

    # Amazon batch queries
    az_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    az_file.write("laptop\ntablet\nkeyboard\n")
    az_file.close()
    f["az_file"] = az_file.name

    # YouTube IDs
    yt_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    yt_file.write("dQw4w9WgXcQ\njNQXAC9IVRw\n")
    yt_file.close()
    f["yt_file"] = yt_file.name

    # ChatGPT prompts
    cg_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    cg_file.write("What is Python?\nWhat is JavaScript?\n")
    cg_file.close()
    f["cg_file"] = cg_file.name

    # Output directories (will be created by the CLI)
    for name, path in [
        ("batch_dir", "/tmp/sb_scrape_batch"),
        ("md_batch_dir", "/tmp/sb_md_batch"),
        ("chunk_batch_dir", "/tmp/sb_chunk_batch"),
        ("google_batch_dir", "/tmp/sb_google_batch"),
        ("az_batch_dir", "/tmp/sb_az_batch"),
        ("yt_batch_dir", "/tmp/sb_yt_batch"),
        ("cg_batch_dir", "/tmp/sb_cg_batch"),
        ("crawl_dir", "/tmp/sb_crawl"),
        ("crawl_md_dir", "/tmp/sb_crawl_md"),
        ("crawl_txt_dir", "/tmp/sb_crawl_txt"),
        ("crawl_nojs_dir", "/tmp/sb_crawl_nojs"),
        ("crawl_cc_dir", "/tmp/sb_crawl_cc"),
        ("diff_base_dir", "/tmp/sb_diff_base"),
        ("diff_dir", "/tmp/sb_diff"),
        ("noprog_dir", "/tmp/sb_noprog"),
    ]:
        f[name] = path
        Path(path).mkdir(parents=True, exist_ok=True)

    f["out_file"] = "/tmp/sb_out.json"
    f["screen_file"] = "/tmp/screen.png"
    f["screen_sel_file"] = "/tmp/screen_sel.png"
    f["screen_full_file"] = "/tmp/screen_full.png"
    f["page_html"] = "/tmp/page.html"
    f["export_ndjson_file"] = "/tmp/sb_export.ndjson"
    f["export_csv_file"] = "/tmp/sb_export.csv"
    f["export_txt_file"] = "/tmp/sb_export.txt"
    # Clean up any stale export files from previous runs
    for ef in ("export_ndjson_file", "export_csv_file", "export_txt_file"):
        p = Path(f[ef])
        if p.is_dir():
            import shutil

            shutil.rmtree(p)
        elif p.exists():
            p.unlink()

    return f


# ─── Test definitions ─────────────────────────────────────────────────────────


def build_tests(fx: dict[str, str]) -> list[Test]:
    tests: list[Test] = []

    # ── G: Global / Meta ──────────────────────────────────────────────────────
    tests += [
        Test("G-01", "scrapingbee --help", ["--help"], stdout_contains("usage")),
        Test("G-02", "scrapingbee --version", ["--version"], exit_ok()),
        Test("G-03", "usage command", ["usage"], json_key("max_api_credit")),
    ]

    # ── GL: Global options ─────────────────────────────────────────────────────
    tests += [
        Test(
            "GL-01",
            "--verbose scrape https://httpbin.org/json",
            ["--verbose", "scrape", "https://httpbin.org/json"],
            stderr_contains("http status: 200"),
        ),
        Test(
            "GL-02",
            "--output-file /tmp/sb_out.json scrape",
            ["--output-file", fx["out_file"], "scrape", "https://httpbin.org/json"],
            file_exists_with(fx["out_file"], "slideshow"),
        ),
        Test(
            "GL-03",
            "--extract-field slideshow scrape (top-level key)",
            ["--extract-field", "slideshow", "scrape", "https://httpbin.org/json"],
            combined_checks(exit_ok(), stdout_contains("author")),
        ),
        Test(
            "GL-04",
            "--fields organic_results google python",
            ["--fields", "organic_results", "google", "python"],
            json_key("organic_results"),
        ),
        Test(
            "GL-05",
            "--retries 1 --backoff 1.0 scrape",
            ["--retries", "1", "--backoff", "1.0", "scrape", "https://httpbin.org/json"],
            json_key("slideshow"),
        ),
        Test(
            "GL-06",
            "--input-file batch scrape (setup for diff-dir)",
            [
                "--output-dir",
                fx["diff_base_dir"],
                "--input-file",
                fx["urls_file"],
                "scrape",
                "--render-js",
                "false",
            ],
            manifest_in(fx["diff_base_dir"], 2),
        ),
        Test(
            "GL-07",
            "--no-progress batch scrape",
            [
                "--no-progress",
                "--output-dir",
                fx["noprog_dir"],
                "--input-file",
                fx["urls_file"],
                "scrape",
                "--render-js",
                "false",
            ],
            manifest_in(fx["noprog_dir"], 2),
        ),
        Test(
            "GL-08",
            "--diff-dir scrape (unchanged detection)",
            [
                "--diff-dir",
                fx["diff_base_dir"],
                "--output-dir",
                fx["diff_dir"],
                "--input-file",
                fx["urls_file"],
                "scrape",
                "--render-js",
                "false",
            ],
            manifest_in(fx["diff_dir"], 2),
            timeout=60,
        ),
    ]

    # ── SC: scrape core ────────────────────────────────────────────────────────
    tests += [
        Test("SC-01", "scrape JSON", ["scrape", "https://httpbin.org/json"], json_key("slideshow")),
        Test(
            "SC-02", "scrape HTML", ["scrape", "https://httpbin.org/html"], stdout_contains("<html")
        ),
        Test(
            "SC-03",
            "scrape --render-js false",
            ["scrape", "https://httpbin.org/json", "--render-js", "false"],
            json_key("slideshow"),
        ),
        Test(
            "SC-04",
            "scrape --render-js true",
            ["scrape", "https://quotes.toscrape.com", "--render-js", "true"],
            stdout_contains("<html"),
        ),
        Test(
            "SC-05",
            "scrape --return-page-markdown true",
            ["scrape", "https://example.com", "--return-page-markdown", "true"],
            combined_checks(exit_ok(), stdout_contains("example")),
        ),
        Test(
            "SC-06",
            "scrape --return-page-text true",
            ["scrape", "https://httpbin.org/json", "--return-page-text", "true"],
            combined_checks(
                exit_ok(),
                lambda o, e, r: (
                    ("<html" not in o.lower(), "unexpected HTML in text mode")
                    if r == 0
                    else (False, f"exit {r}")
                ),
            ),
        ),
        Test(
            "SC-07",
            "scrape --return-page-source true",
            ["scrape", "https://httpbin.org/json", "--return-page-source", "true"],
            combined_checks(exit_ok()),
        ),
    ]

    # ── PR: presets ───────────────────────────────────────────────────────────
    tests += [
        Test(
            "PR-01",
            "--preset screenshot",
            [
                "--output-file",
                fx["screen_file"],
                "scrape",
                "https://example.com",
                "--preset",
                "screenshot",
            ],
            file_exists_with(fx["screen_file"]),
            timeout=60,
        ),
        Test(
            "PR-02",
            "--preset screenshot-and-html",
            ["scrape", "https://example.com", "--preset", "screenshot-and-html"],
            json_key("body", "screenshot"),
            timeout=60,
        ),
        Test(
            "PR-03",
            "--preset fetch",
            ["scrape", "https://httpbin.org/json", "--preset", "fetch"],
            json_key("slideshow"),
        ),
        Test(
            "PR-04",
            "--preset extract-links",
            ["scrape", "https://example.com", "--preset", "extract-links"],
            combined_checks(exit_ok(), stdout_contains("http")),
        ),
        Test(
            "PR-05",
            "--preset extract-emails",
            ["scrape", "https://example.com", "--preset", "extract-emails"],
            exit_ok(),
        ),
        Test(
            "PR-06",
            "--preset extract-phones",
            ["scrape", "https://example.com", "--preset", "extract-phones"],
            exit_ok(),
        ),
        Test(
            "PR-07",
            "--preset scroll-page",
            ["scrape", "https://quotes.toscrape.com", "--preset", "scroll-page"],
            stdout_contains("<html"),
            timeout=60,
        ),
    ]

    # ── JW: JS & wait ─────────────────────────────────────────────────────────
    tests += [
        Test(
            "JW-01",
            "--js-scenario wait 500ms",
            [
                "scrape",
                "https://quotes.toscrape.com",
                "--js-scenario",
                '{"instructions":[{"wait":500}]}',
            ],
            stdout_contains("<html"),
            timeout=60,
        ),
        Test(
            "JW-02",
            "--wait 1000",
            ["scrape", "https://quotes.toscrape.com", "--wait", "1000"],
            stdout_contains("<html"),
            timeout=60,
        ),
        Test(
            "JW-03",
            '--wait-for ".quote"',
            ["scrape", "https://quotes.toscrape.com", "--wait-for", ".quote"],
            stdout_contains("<html"),
            timeout=60,
        ),
        Test(
            "JW-04",
            "--wait-browser load",
            ["scrape", "https://quotes.toscrape.com", "--wait-browser", "load"],
            stdout_contains("<html"),
            timeout=60,
        ),
        Test(
            "JW-05",
            "--block-ads true",
            ["scrape", "https://quotes.toscrape.com", "--block-ads", "true"],
            stdout_contains("<html"),
        ),
        Test(
            "JW-06",
            "--block-resources true",
            ["scrape", "https://quotes.toscrape.com", "--block-resources", "true"],
            stdout_contains("<html"),
        ),
        Test(
            "JW-07",
            "--window-width 1280 --window-height 800",
            ["scrape", "https://example.com", "--window-width", "1280", "--window-height", "800"],
            stdout_contains("<html"),
        ),
    ]

    # ── PX: proxy & country ───────────────────────────────────────────────────
    tests += [
        Test(
            "PX-01",
            "--premium-proxy true",
            ["scrape", "https://httpbin.org/json", "--premium-proxy", "true"],
            json_key("slideshow"),
        ),
        Test(
            "PX-02",
            "--stealth-proxy true",
            ["scrape", "https://httpbin.org/json", "--stealth-proxy", "true"],
            json_key("slideshow"),
        ),
        Test(
            "PX-03",
            "--country-code us",
            ["scrape", "https://httpbin.org/ip", "--country-code", "us"],
            json_key("origin"),
        ),
        Test(
            "PX-04",
            "--country-code gb",
            ["scrape", "https://httpbin.org/ip", "--country-code", "gb"],
            json_key("origin"),
        ),
        Test(
            "PX-05",
            "--country-code fr",
            ["scrape", "https://httpbin.org/ip", "--country-code", "fr"],
            json_key("origin"),
        ),
        Test(
            "PX-06",
            "--country-code de",
            ["scrape", "https://httpbin.org/ip", "--country-code", "de"],
            json_key("origin"),
        ),
        Test(
            "PX-07",
            "--country-code jp",
            ["scrape", "https://httpbin.org/ip", "--country-code", "jp"],
            json_key("origin"),
        ),
    ]

    # ── HR: headers & request ─────────────────────────────────────────────────
    tests += [
        Test(
            "HR-01",
            "-H X-Test: hello --forward-headers true",
            [
                "scrape",
                "https://httpbin.org/headers",
                "-H",
                "X-Test: hello",
                "--forward-headers",
                "true",
            ],
            stdout_contains("X-Test"),
        ),
        Test(
            "HR-02",
            "--forward-headers true",
            ["scrape", "https://httpbin.org/headers", "--forward-headers", "true"],
            exit_ok(),
        ),
        Test(
            "HR-03",
            "--forward-headers-pure true",
            ["scrape", "https://httpbin.org/headers", "--forward-headers-pure", "true"],
            exit_ok(),
        ),
        Test(
            "HR-04",
            "-X POST -d key=val",
            ["scrape", "https://httpbin.org/anything", "-X", "POST", "-d", "key=val"],
            combined_checks(exit_ok(), stdout_contains('"POST"')),
        ),
        Test(
            "HR-05",
            "-X PUT -d x=1",
            ["scrape", "https://httpbin.org/anything", "-X", "PUT", "-d", "x=1"],
            combined_checks(exit_ok(), stdout_contains('"PUT"')),
        ),
        Test(
            "HR-06",
            "--cookies session=abc123",
            ["scrape", "https://httpbin.org/cookies", "--cookies", "session=abc123"],
            stdout_contains("abc123"),
        ),
        Test(
            "HR-07",
            "--json-response true",
            ["scrape", "https://httpbin.org/anything", "--json-response", "true"],
            json_key("body", "xhr"),
        ),
        Test(
            "HR-08",
            "--device mobile",
            ["scrape", "https://httpbin.org/anything", "--device", "mobile"],
            exit_ok(),
        ),
        Test(
            "HR-09",
            "--device desktop",
            ["scrape", "https://httpbin.org/anything", "--device", "desktop"],
            exit_ok(),
        ),
        Test(
            "HR-10",
            "--session-id 42",
            ["scrape", "https://httpbin.org/json", "--session-id", "42"],
            exit_ok(),
        ),
        Test(
            "HR-11",
            "--timeout 30000",
            ["scrape", "https://httpbin.org/json", "--timeout", "30000"],
            json_key("slideshow"),
        ),
    ]

    # ── SS: screenshot ────────────────────────────────────────────────────────
    tests += [
        Test(
            "SS-01",
            "--screenshot true (to file)",
            [
                "--output-file",
                fx["screen_file"],
                "scrape",
                "https://example.com",
                "--screenshot",
                "true",
            ],
            file_exists_with(fx["screen_file"]),
            timeout=60,
        ),
        Test(
            "SS-02",
            "--screenshot-selector .quote",
            [
                "--output-file",
                fx["screen_sel_file"],
                "scrape",
                "https://quotes.toscrape.com",
                "--screenshot-selector",
                ".quote",
            ],
            file_exists_with(fx["screen_sel_file"]),
            timeout=60,
        ),
        Test(
            "SS-03",
            "--screenshot-full-page true",
            [
                "--output-file",
                fx["screen_full_file"],
                "scrape",
                "https://example.com",
                "--screenshot-full-page",
                "true",
            ],
            file_exists_with(fx["screen_full_file"]),
            timeout=60,
        ),
    ]

    # ── EX: extraction ────────────────────────────────────────────────────────
    tests += [
        Test(
            "EX-01",
            "--extract-rules",
            [
                "scrape",
                "https://quotes.toscrape.com",
                "--extract-rules",
                '{"quotes":{"selector":".text","type":"list"}}',
            ],
            json_key("quotes"),
        ),
        Test(
            "EX-02",
            "--ai-query basic",
            ["scrape", "https://quotes.toscrape.com", "--ai-query", "What is the first quote?"],
            combined_checks(exit_ok()),
            timeout=60,
        ),
        Test(
            "EX-03",
            "--ai-query --ai-selector",
            [
                "scrape",
                "https://quotes.toscrape.com",
                "--ai-query",
                "List all quote texts",
                "--ai-selector",
                ".quote",
            ],
            combined_checks(exit_ok()),
            timeout=60,
        ),
        Test(
            "EX-04",
            "--ai-extract-rules",
            [
                "scrape",
                "https://quotes.toscrape.com",
                "--ai-extract-rules",
                '{"first_quote":"Extract the first quote text"}',
            ],
            json_key("first_quote"),
            timeout=60,
        ),
        Test(
            "EX-05",
            "--transparent-status-code true",
            ["scrape", "https://httpbin.org/json", "--transparent-status-code", "true"],
            json_key("slideshow"),
        ),
    ]

    # ── CH: chunked / RAG output ──────────────────────────────────────────────
    tests += [
        Test(
            "CH-01",
            "--chunk-size 500",
            ["scrape", "https://example.com", "--return-page-text", "true", "--chunk-size", "500"],
            ndjson_with_key("chunk_index"),
        ),
        Test(
            "CH-02",
            "--chunk-size 200 --chunk-overlap 50",
            [
                "scrape",
                "https://example.com",
                "--return-page-text",
                "true",
                "--chunk-size",
                "200",
                "--chunk-overlap",
                "50",
            ],
            ndjson_with_key("content"),
        ),
    ]

    # ── OE: output/extension ─────────────────────────────────────────────────
    tests += [
        Test(
            "OE-01",
            "--output-file /tmp/page.html scrape",
            ["--output-file", fx["page_html"], "scrape", "https://example.com"],
            file_exists_with(fx["page_html"], "<html"),
        ),
    ]

    # ── BT: batch mode ────────────────────────────────────────────────────────
    tests += [
        Test(
            "BT-01",
            "batch scrape --render-js false",
            [
                "--output-dir",
                fx["batch_dir"],
                "--input-file",
                fx["urls_file"],
                "scrape",
                "--render-js",
                "false",
            ],
            manifest_in(fx["batch_dir"], 2),
            timeout=90,
        ),
        Test(
            "BT-02",
            "batch --return-page-markdown",
            [
                "--output-dir",
                fx["md_batch_dir"],
                "--input-file",
                fx["urls_file"],
                "scrape",
                "--return-page-markdown",
                "true",
            ],
            manifest_in(fx["md_batch_dir"], 2),
            timeout=90,
        ),
        Test(
            "BT-03",
            "batch --chunk-size 300",
            [
                "--output-dir",
                fx["chunk_batch_dir"],
                "--input-file",
                fx["urls_file"],
                "scrape",
                "--return-page-text",
                "true",
                "--chunk-size",
                "300",
            ],
            manifest_in(fx["chunk_batch_dir"], 2),
            timeout=90,
        ),
    ]

    # ── GG: google ────────────────────────────────────────────────────────────
    tests += [
        Test(
            "GG-01",
            "google 'python programming'",
            ["google", "python programming"],
            json_key("organic_results"),
        ),
        Test(
            "GG-02",
            "google --search-type news",
            ["google", "python", "--search-type", "news"],
            json_key_either("news_results", "organic_results"),
        ),
        Test(
            "GG-03",
            "google --search-type images",
            ["google", "python", "--search-type", "images"],
            json_key_either("images_results", "organic_results"),
        ),
        Test(
            "GG-04",
            "google --search-type shopping",
            ["google", "python", "--search-type", "shopping"],
            json_key_either("shopping_results", "organic_results"),
            timeout=90,
        ),
        Test(
            "GG-05",
            "google --search-type maps",
            ["google", "coffee near london", "--search-type", "maps"],
            json_key_either("local_results", "organic_results"),
        ),
        Test(
            "GG-06",
            "google --search-type ai-mode",
            [
                "--retries",
                "5",
                "--backoff",
                "1.0",
                "google",
                "what is python programming",
                "--search-type",
                "ai-mode",
            ],
            json_key_either("ai_mode_answer", "ai_result", "organic_results"),
            timeout=120,
        ),
        Test(
            "GG-07",
            "google --country-code us",
            ["google", "coffee", "--country-code", "us"],
            json_key_either("organic_results", "meta_data"),
        ),
        Test(
            "GG-08",
            "google --country-code gb",
            ["google", "coffee", "--country-code", "gb"],
            json_key("organic_results"),
        ),
        Test(
            "GG-09",
            "google --country-code fr",
            ["google", "café", "--country-code", "fr"],
            json_key("organic_results"),
        ),
        Test(
            "GG-10",
            "google --country-code de",
            ["google", "kaffee", "--country-code", "de"],
            json_key("organic_results"),
            timeout=90,
        ),
        Test(
            "GG-11",
            "google --country-code jp",
            ["google", "コーヒー", "--country-code", "jp"],
            json_key("organic_results"),
        ),
        Test(
            "GG-12",
            "google --device mobile",
            ["google", "python", "--device", "mobile"],
            json_key("organic_results"),
        ),
        Test(
            "GG-13",
            "google --page 2",
            ["google", "python", "--page", "2"],
            json_key_either("organic_results", "meta_data"),
        ),
        Test(
            "GG-14",
            "google --language fr",
            ["google", "python", "--language", "fr"],
            json_key("organic_results"),
        ),
        Test(
            "GG-15",
            "google --language de",
            ["google", "python", "--language", "de"],
            json_key("organic_results"),
        ),
        Test(
            "GG-16",
            "google --language es",
            ["google", "python", "--language", "es"],
            json_key("organic_results"),
        ),
        Test(
            "GG-17",
            "google --language ja",
            ["google", "python", "--language", "ja"],
            json_key("organic_results"),
        ),
        Test(
            "GG-18",
            "google --nfpr true",
            ["google", "python", "--nfpr", "true"],
            json_key("organic_results"),
        ),
        Test(
            "GG-19",
            "google --add-html true",
            ["google", "python", "--add-html", "true"],
            json_key("organic_results", "html"),
        ),
        Test(
            "GG-20",
            "google --light-request true",
            ["google", "python", "--light-request", "true"],
            json_key("organic_results"),
        ),
        Test(
            "GG-21",
            "--extract-field organic_results.url google",
            ["--extract-field", "organic_results.url", "google", "python"],
            one_url_per_line(),
        ),
        Test(
            "GG-22",
            "google batch",
            ["--output-dir", fx["google_batch_dir"], "--input-file", fx["gs_file"], "google"],
            manifest_in(fx["google_batch_dir"], 3),
            timeout=120,
        ),
    ]

    # ── FS: fast-search ───────────────────────────────────────────────────────
    tests += [
        Test(
            "FS-01",
            "fast-search 'python programming'",
            ["fast-search", "python programming"],
            json_key_either("organic", "organic_results", "results"),
        ),
        Test(
            "FS-02",
            "fast-search --country-code us",
            ["fast-search", "coffee", "--country-code", "us"],
            combined_checks(exit_ok()),
        ),
        Test(
            "FS-03",
            "fast-search --country-code gb",
            ["fast-search", "coffee", "--country-code", "gb"],
            combined_checks(exit_ok()),
        ),
        Test(
            "FS-04",
            "fast-search --country-code fr",
            ["fast-search", "coffee", "--country-code", "fr"],
            combined_checks(exit_ok()),
        ),
        Test(
            "FS-05",
            "fast-search --page 2",
            ["fast-search", "python", "--page", "2"],
            combined_checks(exit_ok()),
        ),
        Test(
            "FS-06",
            "fast-search --language en",
            ["fast-search", "python", "--language", "en"],
            combined_checks(exit_ok()),
        ),
        Test(
            "FS-07",
            "fast-search --language fr",
            ["fast-search", "python", "--language", "fr"],
            combined_checks(exit_ok()),
        ),
    ]

    # ── AP: amazon-product ────────────────────────────────────────────────────
    # B07FZ8S74R = Echo Dot 3rd Gen. API returns "product_name" key.
    tests += [
        Test(
            "AP-01",
            "amazon-product B07FZ8S74R (Echo Dot)",
            ["amazon-product", "B07FZ8S74R"],
            json_key("product_name"),
        ),
        Test(
            "AP-02",
            "amazon-product --domain com",
            ["amazon-product", "B07FZ8S74R", "--domain", "com"],
            json_key("product_name"),
        ),
        Test(
            "AP-03",
            "amazon-product --domain co.uk --country gb",
            ["amazon-product", "B09B8YWXDF", "--domain", "co.uk", "--country", "gb"],
            json_key("product_name"),
        ),
        Test(
            "AP-04",
            "amazon-product --domain de --country de",
            ["amazon-product", "B0BMB9RHTG", "--domain", "de", "--country", "de"],
            json_key("product_name"),
        ),
        Test(
            "AP-05",
            "amazon-product --domain fr --country fr",
            ["amazon-product", "B09B8RF4PY", "--domain", "fr", "--country", "fr"],
            json_key("product_name"),
        ),
        Test(
            "AP-06",
            "amazon-product --zip-code 10001",
            ["amazon-product", "B07FZ8S74R", "--zip-code", "10001"],
            json_key("product_name"),
        ),
        Test(
            "AP-07",
            "amazon-product --language en_US",
            ["amazon-product", "B07FZ8S74R", "--language", "en_US"],
            json_key("product_name"),
        ),
        Test(
            "AP-08",
            "amazon-product --currency USD",
            ["amazon-product", "B07FZ8S74R", "--currency", "USD"],
            json_key("product_name"),
        ),
        Test(
            "AP-09",
            "amazon-product --add-html true",
            ["amazon-product", "B07FZ8S74R", "--add-html", "true"],
            json_key("product_name"),
        ),
        Test(
            "AP-10",
            "amazon-product --light-request true",
            ["amazon-product", "B07FZ8S74R", "--light-request", "true"],
            json_key("product_name"),
        ),
        Test(
            "AP-11",
            "amazon-product --device desktop",
            ["amazon-product", "B07FZ8S74R", "--device", "desktop"],
            json_key("product_name"),
        ),
    ]

    # ── AS: amazon-search ─────────────────────────────────────────────────────
    # API returns "products" key (not "results"). --device only accepts "desktop".
    tests += [
        Test(
            "AS-01",
            "amazon-search 'wireless headphones'",
            ["amazon-search", "wireless headphones"],
            json_key("products"),
        ),
        Test(
            "AS-02",
            "amazon-search --sort-by most-recent",
            ["amazon-search", "headphones", "--sort-by", "most-recent"],
            json_key("products"),
        ),
        Test(
            "AS-03",
            "amazon-search --sort-by price-low-to-high",
            ["amazon-search", "headphones", "--sort-by", "price-low-to-high"],
            json_key("products"),
        ),
        Test(
            "AS-04",
            "amazon-search --sort-by price-high-to-low",
            ["amazon-search", "headphones", "--sort-by", "price-high-to-low"],
            json_key("products"),
        ),
        Test(
            "AS-05",
            "amazon-search --sort-by average-review",
            ["amazon-search", "headphones", "--sort-by", "average-review"],
            json_key("products"),
        ),
        Test(
            "AS-06",
            "amazon-search --sort-by bestsellers",
            ["amazon-search", "headphones", "--sort-by", "bestsellers"],
            json_key("products"),
        ),
        Test(
            "AS-07",
            "amazon-search --sort-by featured",
            ["amazon-search", "headphones", "--sort-by", "featured"],
            json_key("products"),
        ),
        Test(
            "AS-08",
            "amazon-search --start-page 2",
            ["amazon-search", "headphones", "--start-page", "2"],
            json_key("products"),
        ),
        Test(
            "AS-09",
            "amazon-search --pages 2",
            ["amazon-search", "headphones", "--pages", "2"],
            json_key("products"),
            timeout=60,
        ),
        Test(
            "AS-10",
            "amazon-search --device desktop",
            ["amazon-search", "headphones", "--device", "desktop"],
            json_key("products"),
        ),
        Test(
            "AS-11",
            "amazon-search German domain",
            ["amazon-search", "kopfhörer", "--domain", "de", "--country", "de"],
            json_key("products"),
        ),
        Test(
            "AS-12",
            "amazon-search UK domain",
            ["amazon-search", "headphones", "--domain", "co.uk", "--country", "gb"],
            json_key("products"),
        ),
        Test(
            "AS-13",
            "amazon-search --zip-code 90210",
            ["amazon-search", "headphones", "--zip-code", "90210"],
            json_key("products"),
        ),
        Test(
            "AS-14",
            "amazon-search --language en_US",
            ["amazon-search", "headphones", "--language", "en_US"],
            json_key("products"),
        ),
        Test(
            "AS-15",
            "amazon-search --add-html true",
            ["amazon-search", "headphones", "--add-html", "true"],
            json_key("products"),
        ),
        Test(
            "AS-16",
            "amazon-search --light-request true",
            ["amazon-search", "headphones", "--light-request", "true"],
            json_key("products"),
        ),
        Test(
            "AS-17",
            "amazon-search batch",
            ["--output-dir", fx["az_batch_dir"], "--input-file", fx["az_file"], "amazon-search"],
            manifest_in(fx["az_batch_dir"], 3),
            timeout=120,
        ),
    ]

    # ── WS: walmart-search ────────────────────────────────────────────────────
    tests += [
        Test(
            "WS-01",
            "walmart-search laptop",
            ["walmart-search", "laptop"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "WS-02",
            "walmart-search --sort-by best-match",
            ["walmart-search", "laptop", "--sort-by", "best-match"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "WS-03",
            "walmart-search --sort-by price-low",
            ["walmart-search", "laptop", "--sort-by", "price-low"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "WS-04",
            "walmart-search --sort-by price-high",
            ["walmart-search", "laptop", "--sort-by", "price-high"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "WS-05",
            "walmart-search --sort-by best-seller",
            ["walmart-search", "laptop", "--sort-by", "best-seller"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "WS-06",
            "walmart-search --min-price 200 --max-price 800",
            ["walmart-search", "laptop", "--min-price", "200", "--max-price", "800"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "WS-07",
            "walmart-search --device mobile",
            ["walmart-search", "laptop", "--device", "mobile"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "WS-08",
            "walmart-search --fulfillment-speed today",
            ["walmart-search", "laptop", "--fulfillment-speed", "today"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "WS-09",
            "walmart-search --fulfillment-speed 2-days",
            ["walmart-search", "laptop", "--fulfillment-speed", "2-days"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "WS-11",
            "walmart-search --delivery-zip 10001",
            ["walmart-search", "laptop", "--delivery-zip", "10001"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "WS-12",
            "walmart-search --add-html true",
            ["walmart-search", "laptop", "--add-html", "true"],
            combined_checks(exit_ok()),
        ),
        Test(
            "WS-13",
            "walmart-search --light-request true",
            ["walmart-search", "laptop", "--light-request", "true"],
            json_key_either("products", "results", "organic_results"),
        ),
    ]

    # ── WP: walmart-product ───────────────────────────────────────────────────
    # 874432175 = QFX Bluetooth Speaker. API returns "title" key.
    tests += [
        Test(
            "WP-01",
            "walmart-product 874432175",
            ["walmart-product", "874432175"],
            json_key("title"),
        ),
        Test(
            "WP-02",
            "walmart-product --delivery-zip 10001",
            ["walmart-product", "874432175", "--delivery-zip", "10001"],
            json_key("title"),
        ),
        Test(
            "WP-03",
            "walmart-product --store-id 2648",
            ["walmart-product", "874432175", "--store-id", "2648"],
            json_key("title"),
        ),
        Test(
            "WP-05",
            "walmart-product --add-html true",
            ["walmart-product", "874432175", "--add-html", "true"],
            combined_checks(exit_ok()),
        ),
        Test(
            "WP-06",
            "walmart-product --light-request true",
            ["walmart-product", "874432175", "--light-request", "true"],
            json_key("title"),
        ),
    ]

    # ── YS: youtube-search ────────────────────────────────────────────────────
    tests += [
        Test(
            "YS-01",
            "youtube-search 'python tutorial'",
            ["youtube-search", "python tutorial"],
            json_key("results"),
        ),
        Test(
            "YS-02",
            "youtube-search --upload-date last-hour",
            ["youtube-search", "python", "--upload-date", "last-hour"],
            json_key("results"),
        ),
        Test(
            "YS-03",
            "youtube-search --upload-date this-week",
            ["youtube-search", "python", "--upload-date", "this-week"],
            json_key("results"),
        ),
        Test(
            "YS-04",
            "youtube-search --upload-date this-month",
            ["youtube-search", "python", "--upload-date", "this-month"],
            json_key("results"),
        ),
        Test(
            "YS-05",
            "youtube-search --upload-date this-year",
            ["youtube-search", "python", "--upload-date", "this-year"],
            json_key("results"),
        ),
        Test(
            "YS-06",
            "youtube-search --type video",
            ["youtube-search", "python", "--type", "video"],
            json_key("results"),
        ),
        Test(
            "YS-07",
            "youtube-search --type channel",
            ["youtube-search", "python", "--type", "channel"],
            json_key("results"),
        ),
        Test(
            "YS-08",
            "youtube-search --type playlist",
            ["youtube-search", "python", "--type", "playlist"],
            json_key("results"),
        ),
        Test(
            "YS-09",
            "youtube-search --sort-by view-count",
            ["youtube-search", "python", "--sort-by", "view-count"],
            json_key("results"),
        ),
        Test(
            "YS-10",
            "youtube-search --sort-by upload-date",
            ["youtube-search", "python", "--sort-by", "upload-date"],
            json_key("results"),
        ),
        Test(
            "YS-11",
            "youtube-search --sort-by relevance",
            ["youtube-search", "python", "--sort-by", "relevance"],
            json_key("results"),
        ),
        Test(
            "YS-12",
            "youtube-search --sort-by rating",
            ["youtube-search", "python", "--sort-by", "rating"],
            json_key("results"),
        ),
        Test(
            "YS-13",
            "youtube-search --4k true",
            ["youtube-search", "4k nature", "--4k", "true"],
            json_key("results"),
        ),
        Test(
            "YS-14",
            "youtube-search --subtitles true",
            ["youtube-search", "lecture", "--subtitles", "true"],
            json_key("results"),
        ),
        Test(
            "YS-15",
            "youtube-search --hd true",
            ["youtube-search", "tutorial", "--hd", "true"],
            json_key("results"),
        ),
        Test(
            "YS-16",
            "youtube-search --creative-commons true",
            ["youtube-search", "music", "--creative-commons", "true"],
            json_key("results"),
        ),
        Test(
            "YS-17",
            "youtube-search --live true",
            ["youtube-search", "live", "--live", "true"],
            json_key("results"),
        ),
        Test(
            "YS-18",
            "--extract-field results.link youtube-search",
            ["--extract-field", "results.link", "youtube-search", "rick astley"],
            lines_contain("youtube.com"),
        ),
    ]

    # ── YM: youtube-metadata ──────────────────────────────────────────────────
    tests += [
        Test(
            "YM-01",
            "youtube-metadata dQw4w9WgXcQ",
            ["youtube-metadata", "dQw4w9WgXcQ"],
            combined_checks(json_key("title"), stdout_contains("rick astley")),
        ),
        Test(
            "YM-02",
            "youtube-metadata (URL form)",
            ["youtube-metadata", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
            json_key("title"),
        ),
        Test(
            "YM-03",
            "youtube-metadata jNQXAC9IVRw",
            ["youtube-metadata", "jNQXAC9IVRw"],
            json_key("title"),
        ),
        Test(
            "YM-04",
            "youtube-metadata batch",
            ["--output-dir", fx["yt_batch_dir"], "--input-file", fx["yt_file"], "youtube-metadata"],
            manifest_in(fx["yt_batch_dir"], 2),
            timeout=60,
        ),
    ]

    # ── CG: chatgpt ───────────────────────────────────────────────────────────
    tests += [
        Test(
            "CG-01",
            "chatgpt 'What is 2+2?'",
            ["chatgpt", "What is 2+2?"],
            combined_checks(exit_ok(), stdout_contains("4")),
            timeout=60,
        ),
        Test(
            "CG-02",
            "chatgpt 'List three programming languages'",
            ["chatgpt", "List three programming languages"],
            combined_checks(exit_ok()),
            timeout=60,
        ),
        Test(
            "CG-03",
            "chatgpt batch",
            ["--output-dir", fx["cg_batch_dir"], "--input-file", fx["cg_file"], "chatgpt"],
            manifest_in(fx["cg_batch_dir"], 2),
            timeout=140,
        ),
    ]

    # ── CR: crawl ─────────────────────────────────────────────────────────────
    tests += [
        Test(
            "CR-01",
            "crawl --max-pages 2 --max-depth 1",
            [
                "--output-dir",
                fx["crawl_dir"],
                "crawl",
                "https://example.com",
                "--max-pages",
                "2",
                "--max-depth",
                "1",
            ],
            manifest_in(fx["crawl_dir"], 1),
            timeout=120,
        ),
        Test(
            "CR-02",
            "crawl --return-page-markdown",
            [
                "--output-dir",
                fx["crawl_md_dir"],
                "crawl",
                "https://example.com",
                "--max-pages",
                "2",
                "--return-page-markdown",
                "true",
            ],
            manifest_in(fx["crawl_md_dir"], 1),
            timeout=120,
        ),
        Test(
            "CR-03",
            "crawl --return-page-text",
            [
                "--output-dir",
                fx["crawl_txt_dir"],
                "crawl",
                "https://example.com",
                "--max-pages",
                "2",
                "--return-page-text",
                "true",
            ],
            manifest_in(fx["crawl_txt_dir"], 1),
            timeout=120,
        ),
        Test(
            "CR-04",
            "crawl --render-js false",
            [
                "--output-dir",
                fx["crawl_nojs_dir"],
                "crawl",
                "https://example.com",
                "--max-pages",
                "2",
                "--render-js",
                "false",
            ],
            manifest_in(fx["crawl_nojs_dir"], 1),
            timeout=120,
        ),
        Test(
            "CR-05",
            "crawl --country-code us",
            [
                "--output-dir",
                fx["crawl_cc_dir"],
                "crawl",
                "https://example.com",
                "--max-pages",
                "2",
                "--country-code",
                "us",
            ],
            manifest_in(fx["crawl_cc_dir"], 1),
            timeout=120,
        ),
    ]

    # ── SC-H: schedule help ───────────────────────────────────────────────────
    tests += [
        Test(
            "SC-H",
            "schedule --help",
            ["schedule", "--help"],
            combined_checks(stdout_contains("--every"), stdout_contains("--auto-diff")),
        ),
    ]

    # ── NV: norm_val regression ───────────────────────────────────────────────
    tests += [
        Test(
            "NV-01",
            "amazon-search --sort-by most-recent (norm_val)",
            ["amazon-search", "laptop", "--sort-by", "most-recent"],
            json_key("products"),
        ),
        Test(
            "NV-02",
            "walmart-search --sort-by best-seller (norm_val)",
            ["walmart-search", "tv", "--sort-by", "best-seller"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "NV-03",
            "walmart-search --fulfillment-speed 2-days (norm_val)",
            ["walmart-search", "tv", "--fulfillment-speed", "2-days"],
            json_key_either("products", "results", "organic_results"),
        ),
        Test(
            "NV-04",
            "youtube-search --sort-by view-count (norm_val)",
            ["youtube-search", "music", "--sort-by", "view-count"],
            json_key("results"),
        ),
        Test(
            "NV-05",
            "youtube-search --upload-date this-week (norm_val)",
            ["youtube-search", "news", "--upload-date", "this-week"],
            json_key("results"),
        ),
        Test(
            "NV-06",
            "google --search-type ai-mode (norm_val)",
            ["google", "what is python", "--search-type", "ai-mode"],
            json_key_either("ai_mode_answer", "ai_result", "organic_results"),
            timeout=90,
        ),
    ]

    # ── VB: verbose headers ───────────────────────────────────────────────────
    tests += [
        Test(
            "VB-01",
            "--verbose google python (Credit Cost in stderr)",
            ["--verbose", "google", "python"],
            stderr_contains("credit cost"),
        ),
        Test(
            "VB-02",
            "--verbose scrape (HTTP Status in stderr)",
            ["--verbose", "scrape", "https://httpbin.org/json"],
            stderr_contains("http status: 200"),
        ),
    ]

    # ── XP: export ─────────────────────────────────────────────────────────────
    # These tests depend on batch_dir from BT-01 (which writes 2 JSON files).
    tests += [
        Test(
            "XP-01",
            "export --format ndjson from batch dir",
            [
                "--output-file",
                fx["export_ndjson_file"],
                "export",
                "--input-dir",
                fx["batch_dir"],
                "--format",
                "ndjson",
            ],
            exit_ok(),
        ),
        Test(
            "XP-02",
            "export --format csv from google batch",
            [
                "--output-file",
                fx["export_csv_file"],
                "export",
                "--input-dir",
                fx["google_batch_dir"],
                "--format",
                "csv",
            ],
            exit_ok(),
        ),
        Test(
            "XP-03",
            "export --format txt from batch dir",
            [
                "--output-file",
                fx["export_txt_file"],
                "export",
                "--input-dir",
                fx["batch_dir"],
                "--format",
                "txt",
            ],
            exit_ok(),
        ),
        Test(
            "XP-04",
            "export --diff-dir (unchanged detection)",
            [
                "export",
                "--input-dir",
                fx["diff_dir"],
                "--diff-dir",
                fx["diff_base_dir"],
                "--format",
                "ndjson",
            ],
            stderr_contains("skipped"),
        ),
    ]

    # ── SD: schedule ──────────────────────────────────────────────────────────
    tests += [
        Test(
            "SD-01",
            "schedule --help",
            ["schedule", "--help"],
            combined_checks(exit_ok(), stdout_contains("--every")),
        ),
    ]

    return tests


# ─── Runner ───────────────────────────────────────────────────────────────────


@dataclass
class Result:
    test: Test
    passed: bool
    message: str
    stdout: str
    stderr: str
    returncode: int
    duration: float
    skipped: bool = False


def run_test(test: Test, binary: str, api_key: str) -> Result:
    if test.skip:
        return Result(test, True, test.skip_reason, "", "", 0, 0.0, skipped=True)

    cmd = [binary] + test.args
    env = {**os.environ, "SCRAPINGBEE_API_KEY": api_key, **test.env_extra}

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=test.timeout,
            env=env,
        )
        duration = time.monotonic() - t0
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - t0
        return Result(test, False, f"TIMEOUT after {test.timeout}s", "", "", -1, duration)
    except Exception as e:
        duration = time.monotonic() - t0
        return Result(test, False, f"exception: {e}", "", "", -1, duration)

    try:
        passed, message = test.check(stdout, stderr, rc)
    except Exception as e:
        passed, message = False, f"check raised: {e}"

    return Result(test, passed, message, stdout, stderr, rc, duration)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="ScrapingBee CLI end-to-end tests")
    parser.add_argument(
        "--filter",
        "-f",
        default="",
        help="Only run tests whose ID starts with this prefix (e.g. GG, SC, AP)",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Concurrent workers (default {DEFAULT_WORKERS})",
    )
    args = parser.parse_args()

    # ── API key check ────────────────────────────────────────────────────────
    api_key = os.environ.get("SCRAPINGBEE_API_KEY", "").strip()
    if not api_key:
        print("ERROR: SCRAPINGBEE_API_KEY is not set.", file=sys.stderr)
        print("  Export it before running:", file=sys.stderr)
        print("    export SCRAPINGBEE_API_KEY=your_key", file=sys.stderr)
        print("  Then: uv run python tests/run_e2e_tests.py", file=sys.stderr)
        sys.exit(1)

    # ── Binary ───────────────────────────────────────────────────────────────
    binary = find_binary()
    print(f"Using binary: {binary}")

    # ── Fixtures ─────────────────────────────────────────────────────────────
    print("Creating fixtures...")
    fx = create_fixtures()

    # ── Build tests ──────────────────────────────────────────────────────────
    all_tests = build_tests(fx)
    if args.filter:
        prefix = args.filter.upper()
        all_tests = [t for t in all_tests if t.id.upper().startswith(prefix)]
        print(f"Filtered to {len(all_tests)} tests matching '{args.filter}'")

    total = len(all_tests)
    print(
        f"Running {total} tests with {args.workers} workers "
        f"(abort after {MAX_CONSECUTIVE_FAILURES} consecutive failures)\n"
    )

    # ── Shared state ─────────────────────────────────────────────────────────
    results: list[Result] = []
    lock = threading.Lock()
    consecutive = [0]  # mutable int in list so lambda can mutate
    abort_event = threading.Event()
    completed = [0]

    def run_one(test: Test) -> Result:
        if abort_event.is_set():
            return Result(test, False, "ABORTED (too many consecutive failures)", "", "", -1, 0.0)
        r = run_test(test, binary, api_key)
        with lock:
            completed[0] += 1
            results.append(r)
            if r.skipped:
                status = "SKIP"
                consecutive[0] = 0
            elif r.passed:
                status = "PASS"
                consecutive[0] = 0
            else:
                status = "FAIL"
                consecutive[0] += 1

            icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "−"}[status]
            dur = f"{r.duration:.1f}s"
            print(
                f"  {icon} [{completed[0]:3d}/{total}] {r.test.id:<8} {status}  "
                f"({dur})  {r.message[:80]}"
            )

            if consecutive[0] >= MAX_CONSECUTIVE_FAILURES:
                print(
                    f"\n  !! {MAX_CONSECUTIVE_FAILURES} consecutive failures — aborting remaining tests !!\n"
                )
                abort_event.set()
        return r

    start_time = time.monotonic()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(run_one, t): t for t in all_tests}
        # Drain futures in completion order (just to avoid uncollected exceptions)
        for _ in as_completed(futures):
            pass

    elapsed = time.monotonic() - start_time

    # ── Summary ──────────────────────────────────────────────────────────────
    passed = [r for r in results if r.passed and not r.skipped]
    failed = [r for r in results if not r.passed and not r.skipped]
    skipped = [r for r in results if r.skipped]
    aborted = [r for r in results if r.message.startswith("ABORTED")]

    print(f"\n{'=' * 60}")
    print(
        f"Results: {len(passed)} passed  |  {len(failed)} failed  |  "
        f"{len(skipped)} skipped  |  {len(aborted)} aborted"
    )
    print(f"Total time: {elapsed:.1f}s")

    if failed:
        print("\nFailed tests:")
        for r in failed:
            print(f"  ✗ {r.test.id}  —  {r.message}")

    # ── Write TEST_RESULTS.md ─────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [
        "# ScrapingBee CLI — E2E Test Results",
        "",
        f"**Run at:** {ts}  ",
        f"**Binary:** `{binary}`  ",
        f"**Total:** {total}  |  **Passed:** {len(passed)}  |  "
        f"**Failed:** {len(failed)}  |  **Skipped:** {len(skipped)}  |  "
        f"**Aborted:** {len(aborted)}  ",
        f"**Duration:** {elapsed:.1f}s  ",
        "",
        "---",
        "",
    ]

    if passed:
        lines += [
            "## Passed",
            "",
            "| ID | Description | Duration |",
            "|----|-------------|----------|",
        ]
        for r in sorted(passed, key=lambda x: x.test.id):
            lines.append(f"| {r.test.id} | {r.test.description[:60]} | {r.duration:.1f}s |")
        lines.append("")

    if failed:
        lines += [
            "## Failed",
            "",
        ]
        for r in sorted(failed, key=lambda x: x.test.id):
            lines += [
                f"### {r.test.id} — {r.test.description}",
                "",
                f"**Reason:** {r.message}  ",
                f"**Exit code:** {r.returncode}  ",
                f"**Duration:** {r.duration:.1f}s  ",
                "",
                f"**Command:** `scrapingbee {' '.join(r.test.args)}`  ",
                "",
            ]
            if r.stdout:
                preview = r.stdout[:500].replace("```", "'''")
                lines += [
                    "**stdout (first 500 chars):**",
                    "```",
                    preview,
                    "```",
                    "",
                ]
            if r.stderr:
                preview = r.stderr[:300].replace("```", "'''")
                lines += [
                    "**stderr (first 300 chars):**",
                    "```",
                    preview,
                    "```",
                    "",
                ]
            lines.append("---")
            lines.append("")

    if skipped:
        lines += [
            "## Skipped",
            "",
            "| ID | Reason |",
            "|----|--------|",
        ]
        for r in skipped:
            lines.append(f"| {r.test.id} | {r.test.skip_reason} |")
        lines.append("")

    RESULTS_FILE.write_text("\n".join(lines))
    print(f"\nResults written to: {RESULTS_FILE}")

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
