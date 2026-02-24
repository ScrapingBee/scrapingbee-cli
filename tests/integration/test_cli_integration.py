"""Integration tests: CLI subprocess (help, no-api-key, live API matrix)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pytest

from tests.conftest import cli_run, get_cli
from tests.integration.helpers import (
    CLI_COMMANDS,
    CLI_COMMANDS_REQUIRE_API_KEY,
    build_api_matrix_tests,
)

# --- Help & no-API-key (fast, no API key needed) ---


@pytest.mark.parametrize("cmd,args", CLI_COMMANDS)
def test_cli_help(cmd, args):
    """Each command must support --help."""
    code, out, err = cli_run([cmd, "--help"] + args)
    assert code == 0, err or out


def test_root_help():
    code, _, _ = cli_run(["--help"])
    assert code == 0


def test_root_version():
    code, out, _ = cli_run(["--version"])
    assert code == 0
    assert "1.0" in out and "scrapingbee" in out.lower()


@pytest.mark.parametrize("cmd,args", CLI_COMMANDS_REQUIRE_API_KEY)
def test_cli_no_api_key(cmd, args, no_api_key_env):
    """Without API key, CLI must exit non-zero and mention API key (auth/logout excluded)."""
    env, cwd = no_api_key_env
    code, out, err = cli_run([cmd] + args, env=env, cwd=cwd)
    assert code != 0, "expected non-zero exit when API key missing"
    combined = (out + "\n" + err).lower()
    assert "api key" in combined or "api_key" in combined


# --- Live API tests (require SCRAPINGBEE_API_KEY) ---


@pytest.mark.integration
def test_api_matrix(api_key, request):
    """Run one API call per (command, parameter). Skipped if no API key."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")

    base = get_cli()
    api_env = {**os.environ, "SCRAPINGBEE_API_KEY": api_key}
    api_timeout = 90
    chatgpt_timeout = 150
    tests_to_run = build_api_matrix_tests(base, api_timeout, chatgpt_timeout)

    # Get max concurrency from usage API, cap at 200 for tests
    code, out, _ = cli_run(["usage"], timeout=30, env=api_env)
    max_concurrency = 10
    if code == 0:
        try:
            data = json.loads(out)
            n = data.get("max_concurrency") or data.get("max_concurrent_requests")
            if isinstance(n, (int, float)) and 0 < n <= 10000:
                max_concurrency = int(n)
        except (json.JSONDecodeError, TypeError):
            pass
    max_concurrency = min(max_concurrency, 200)

    workers = min(max_concurrency, len(tests_to_run))
    failed: list[tuple[str, list[str], int, str, str]] = []

    def run_one(item):
        name, cmd, timeout = item
        try:
            p = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=api_env,
            )
            return (name, cmd, p.returncode, p.stdout or "", p.stderr or "")
        except subprocess.TimeoutExpired as e:
            return (name, cmd, -1, "", f"timeout after {timeout}s: {e}")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_one, item): item for item in tests_to_run}
        for future in as_completed(futures):
            name, cmd, code, out, err = future.result()
            if code != 0:
                failed.append((name, cmd, code, out, err))

    # Write each failed response to a folder as <timestamp>.err (command + error response)
    if failed:
        root = Path(request.config.rootpath)
        failures_dir = root / "test_failures"
        failures_dir.mkdir(exist_ok=True)
        base_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for i, (name, cmd, code, out, err) in enumerate(failed):
            ts = f"{base_ts}_{i:04d}"
            err_path = failures_dir / f"{ts}.err"
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(f"Test: {name}\n")
                f.write(f"Command: {' '.join(cmd)}\n")
                f.write(f"Exit code: {code}\n")
                f.write("--- stdout ---\n")
                f.write(out or "(empty)\n")
                f.write("--- stderr ---\n")
                f.write(err or "(empty)\n")
        pytest.fail(f"{len(failed)} API test(s) failed. See {failures_dir}")


@pytest.mark.integration
def test_scrape_forwarded_headers_echoed(api_key):
    """Scrape httpbin/headers with a custom header; response must echo that header."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")
    env = {**os.environ, "SCRAPINGBEE_API_KEY": api_key}
    code, out, err = cli_run(
        [
            "scrape",
            "https://httpbin.org/headers",
            "-H",
            "X-Test-Header: echoed-value",
            "--forward-headers",
            "true",
        ],
        timeout=60,
        env=env,
    )
    assert code == 0, err or out
    data = json.loads(out)
    headers = data.get("headers") or {}
    # Header names may be normalized (e.g. lowercased) by the server
    header_key = next((k for k in headers if k.lower() == "x-test-header"), None)
    assert header_key is not None, f"X-Test-Header not in echoed headers: {list(headers)}"
    assert headers[header_key] == "echoed-value"


@pytest.mark.integration
def test_scrape_post_body_echoed(api_key):
    """Scrape httpbin/anything with POST form body; response must echo the form (ScrapingBee expects form-urlencoded)."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")
    # ScrapingBee API accepts POST only as application/x-www-form-urlencoded; use form body
    payload = "KEY_1=VALUE_1"
    env = {**os.environ, "SCRAPINGBEE_API_KEY": api_key}
    cmd = [
        "scrape",
        "https://httpbin.org/anything",
        "--render-js",
        "false",
        "-X",
        "POST",
        "-d",
        payload,
    ]
    code, out, err = cli_run(cmd, timeout=60, env=env)
    if code != 0:
        failures_dir = Path(__file__).resolve().parent.parent / "test_failures"
        failures_dir.mkdir(exist_ok=True)
        err_path = failures_dir / "test_scrape_post_body_echoed.err"
        with open(err_path, "w", encoding="utf-8") as f:
            f.write("Test: test_scrape_post_body_echoed\n")
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write(f"Exit code: {code}\n")
            f.write("--- stdout ---\n")
            f.write(out or "(empty)\n")
            f.write("--- stderr ---\n")
            f.write(err or "(empty)\n")
    assert code == 0, err or out
    data = json.loads(out)
    assert "form" in data, f"no 'form' in response: {list(data)}"
    form = data["form"]
    assert form.get("KEY_1") == "VALUE_1", (
        f"expected form KEY_1=VALUE_1, got form={form!r}"
    )


@pytest.mark.integration
def test_scrape_cookies_echoed(api_key):
    """Scrape httpbin/cookies with --cookies; response must echo that cookie."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")
    env = {**os.environ, "SCRAPINGBEE_API_KEY": api_key}
    # Single cookie: ScrapingBee can reject some multi-cookie strings (Invalid cookie fields)
    code, out, err = cli_run(
        [
            "scrape",
            "https://httpbin.org/cookies",
            "--cookies",
            "session=abc123",
        ],
        timeout=60,
        env=env,
    )
    assert code == 0, err or out
    data = json.loads(out)
    cookies = data.get("cookies") or {}
    assert cookies.get("session") == "abc123", f"session cookie not echoed: {cookies}"


@pytest.mark.integration
def test_batch_uses_usage_concurrency(api_key):
    """Batch scrape without --concurrency must report concurrency from usage API."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(
            "https://httpbin.org/get\nhttps://httpbin.org/headers\nhttps://httpbin.org/get\n"
        )
        tmp = f.name
    out_dir = _test_results_dir() / "batch_usage_concurrency"
    out_dir.mkdir(exist_ok=True)
    try:
        env = {**os.environ, "SCRAPINGBEE_API_KEY": api_key}
        code, out, err = cli_run(
            ["--output-dir", str(out_dir), "--input-file", tmp, "scrape"],
            timeout=120,
            env=env,
        )
        assert code == 0, err or out
        assert "from usage API" in err
        assert "Batch:" in err and "concurrency" in err
        m = re.search(r"concurrency\s+(\d+)\s+\(from usage API\)", err)
        assert m, "could not parse concurrency from stderr"
        assert int(m.group(1)) >= 1
    finally:
        Path(tmp).unlink(missing_ok=True)


@pytest.mark.integration
def test_batch_explicit_concurrency(api_key):
    """Batch scrape with --concurrency N must report 'from --concurrency' in stderr."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("https://httpbin.org/get\nhttps://httpbin.org/headers\n")
        tmp = f.name
    out_dir = _test_results_dir() / "batch_explicit_concurrency"
    out_dir.mkdir(exist_ok=True)
    try:
        env = {**os.environ, "SCRAPINGBEE_API_KEY": api_key}
        code, out, err = cli_run(
            ["--output-dir", str(out_dir), "--concurrency", "2", "--input-file", tmp, "scrape"],
            timeout=120,
            env=env,
        )
        assert code == 0, err or out
        assert "from --concurrency" in err
        m = re.search(r"concurrency\s+2\s+\(from --concurrency\)", err)
        assert m, "expected 'concurrency 2 (from --concurrency)' in stderr"
    finally:
        Path(tmp).unlink(missing_ok=True)


def _test_results_dir() -> Path:
    """Project root / test_results for integration test output (cleaned after session)."""
    root = Path(__file__).resolve().parent.parent.parent
    out = root / "test_results"
    out.mkdir(exist_ok=True)
    return out


@pytest.mark.integration
def test_batch_output_dir_has_files(api_key):
    """Batch scrape with --output-dir must write output files into that dir."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as input_f:
        input_f.write(
            "https://httpbin.org/get\nhttps://httpbin.org/headers\n"
        )
        input_path = input_f.name
    out_dir = _test_results_dir() / "batch_out_test"
    out_dir.mkdir(exist_ok=True)
    try:
        env = {**os.environ, "SCRAPINGBEE_API_KEY": api_key}
        code, out, err = cli_run(
            [
                "--output-dir",
                str(out_dir),
                "--concurrency",
                "2",
                "--input-file",
                input_path,
                "scrape",
            ],
            timeout=120,
            env=env,
        )
        assert code == 0, err or out
        assert "Batch complete" in out
        assert out_dir.exists()
        # Count files (may be in root or in screenshots/ / files/ subdirs)
        all_files = [f for f in out_dir.rglob("*") if f.is_file() and f.suffix not in (".err",)]
        assert len(all_files) >= 2, f"expected at least 2 output files, got {all_files}"
        exts = {f.suffix for f in all_files}
        assert ".html" in exts or ".json" in exts or ".txt" in exts or ".png" in exts
        # At least one success file should have content (exclude failures.txt etc.)
        success_sizes = [f.stat().st_size for f in all_files if f.name != "failures.txt"]
        assert any(s > 0 for s in success_sizes), "expected at least one non-empty output file"
    finally:
        Path(input_path).unlink(missing_ok=True)
        if out_dir.exists():
            shutil.rmtree(out_dir)


@pytest.mark.integration
def test_crawl_output_dir_writes_files(api_key):
    """Crawl with --output-dir and --max-pages 2 must write at least one file to that dir."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")

    out_dir = _test_results_dir() / "crawl_integration"
    out_dir.mkdir(exist_ok=True)
    try:
        env = {**os.environ, "SCRAPINGBEE_API_KEY": api_key}
        code, out, err = cli_run(
            [
                "--output-dir",
                str(out_dir),
                "crawl",
                "https://crawler-test.com/",
                "--max-pages",
                "2",
                "--max-depth",
                "1",
            ],
            timeout=120,
            env=env,
        )
        assert code == 0, err or out
        assert "Saved to" in err
        assert out_dir.exists()
        # Files may be in root (1.html) or in screenshots/ / files/ subdirs
        file_files = [f for f in out_dir.rglob("*") if f.is_file()]
        assert len(file_files) >= 1, (
            f"expected at least 1 file under {out_dir}, got {list(out_dir.rglob('*'))}"
        )
    finally:
        if out_dir.exists():
            shutil.rmtree(out_dir)


@pytest.mark.integration
def test_batch_chatgpt(api_key):
    """Batch chatgpt with --input-file must run and write one JSON per line."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as input_f:
        input_f.write("Say hi\nSay bye\n")
        input_path = input_f.name
    out_dir = _test_results_dir() / "batch_chatgpt_test"
    out_dir.mkdir(exist_ok=True)
    success = False
    try:
        env = {**os.environ, "SCRAPINGBEE_API_KEY": api_key}
        code, out, err = cli_run(
            [
                "--output-dir",
                str(out_dir),
                "--concurrency",
                "2",
                "--input-file",
                input_path,
                "chatgpt",
            ],
            timeout=180,
            env=env,
        )
        assert code == 0, err or out
        assert "Batch complete" in out
        assert out_dir.exists()
        json_files = list(out_dir.glob("*.json"))
        assert len(json_files) >= 2, (
            f"expected at least 2 .json files, got {list(out_dir.iterdir())}"
        )
        success = True
    finally:
        Path(input_path).unlink(missing_ok=True)
        # Only remove output dir on success so .err and failures.txt are kept for inspection on failure
        if out_dir.exists() and success:
            shutil.rmtree(out_dir)
