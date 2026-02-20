"""Integration tests: CLI subprocess (help, no-api-key, live API matrix)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from tests.conftest import cli_run, get_cli
from tests.integration.helpers import CLI_COMMANDS, build_api_matrix_tests

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
    assert "1.0.0" in out or "scrapingbee" in out.lower()


@pytest.mark.parametrize("cmd,args", CLI_COMMANDS)
def test_cli_no_api_key(cmd, args, no_api_key_env):
    """Without API key, CLI must exit non-zero and mention API key."""
    code, out, err = cli_run([cmd] + args, env=no_api_key_env)
    assert code != 0, "expected non-zero exit when API key missing"
    combined = (out + "\n" + err).lower()
    assert "api key" in combined or "api_key" in combined


# --- Live API tests (require SCRAPINGBEE_API_KEY) ---


@pytest.mark.integration
def test_api_matrix(api_key, request):
    """Run one API call per (command, parameter). Skipped if no API key."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")

    base = get_cli() + ["--api-key", api_key]
    api_timeout = 90
    chatgpt_timeout = 150
    tests_to_run = build_api_matrix_tests(base, api_timeout, chatgpt_timeout)

    # Get max concurrency from usage API
    code, out, _ = cli_run(["usage", "--api-key", api_key], timeout=30)
    max_concurrency = 10
    if code == 0:
        try:
            data = json.loads(out)
            n = data.get("max_concurrency") or data.get("max_concurrent_requests")
            if isinstance(n, (int, float)) and 0 < n <= 10000:
                max_concurrency = int(n)
        except (json.JSONDecodeError, TypeError):
            pass

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

    # Write failed_requests.txt on failure
    if failed:
        failed_file = Path(request.config.rootpath) / "failed_requests.txt"
        with open(failed_file, "w") as f:
            for name, cmd, code, out, err in failed:
                f.write("=" * 60 + "\n")
                f.write(f"Test: {name}\n")
                f.write(f"Command: {' '.join(cmd)}\n")
                f.write(f"Exit code: {code}\n")
                f.write(f"--- stdout ---\n{out}\n")
                f.write(f"--- stderr ---\n{err}\n")
        pytest.fail(f"{len(failed)} API test(s) failed. See {failed_file}")


@pytest.mark.integration
def test_scrape_forwarded_headers_echoed(api_key):
    """Scrape httpbin/headers with a custom header; response must echo that header."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")
    code, out, err = cli_run(
        [
            "--api-key",
            api_key,
            "scrape",
            "https://httpbin.scrapingbee.com/headers",
            "-H",
            "X-Test-Header: echoed-value",
            "--forward-headers",
            "true",
        ],
        timeout=60,
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
    """Scrape httpbin/post with POST body; response must echo the JSON body."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")
    payload = '{"foo":"bar","n":42}'
    code, out, err = cli_run(
        [
            "--api-key",
            api_key,
            "scrape",
            "https://httpbin.scrapingbee.com/post",
            "-X",
            "POST",
            "-d",
            payload,
            "--content-type",
            "application/json",
        ],
        timeout=60,
    )
    assert code == 0, err or out
    data = json.loads(out)
    assert "json" in data, f"no 'json' in response: {list(data)}"
    assert data["json"] == {"foo": "bar", "n": 42}


@pytest.mark.integration
def test_scrape_cookies_echoed(api_key):
    """Scrape httpbin/cookies with --cookies; response must echo that cookie."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")
    # Single cookie: ScrapingBee can reject some multi-cookie strings (Invalid cookie fields)
    code, out, err = cli_run(
        [
            "--api-key",
            api_key,
            "scrape",
            "https://httpbin.scrapingbee.com/cookies",
            "--cookies",
            "session=abc123",
        ],
        timeout=60,
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
        f.write("https://httpbin.scrapingbee.com/get\nhttps://httpbin.scrapingbee.com/headers\nhttps://httpbin.scrapingbee.com/get\n")
        tmp = f.name
    try:
        code, out, err = cli_run(
            ["--api-key", api_key, "scrape", "--input-file", tmp],
            timeout=120,
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
        f.write("https://httpbin.scrapingbee.com/get\nhttps://httpbin.scrapingbee.com/headers\n")
        tmp = f.name
    try:
        code, out, err = cli_run(
            ["--api-key", api_key, "--concurrency", "2", "scrape", "--input-file", tmp],
            timeout=120,
        )
        assert code == 0, err or out
        assert "from --concurrency" in err
        m = re.search(r"concurrency\s+2\s+\(from --concurrency\)", err)
        assert m, "expected 'concurrency 2 (from --concurrency)' in stderr"
    finally:
        Path(tmp).unlink(missing_ok=True)


@pytest.mark.integration
def test_batch_output_dir_has_files(api_key):
    """Batch scrape with --batch-output-dir must write output files into that dir."""
    if not api_key:
        pytest.skip("SCRAPINGBEE_API_KEY not set")

    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as input_f:
        input_f.write("https://httpbin.scrapingbee.com/get\nhttps://httpbin.scrapingbee.com/headers\n")
        input_path = input_f.name
    out_dir = Path(input_path).parent / "batch_out_test"
    out_dir.mkdir(exist_ok=True)
    try:
        code, out, err = cli_run(
            [
                "--api-key",
                api_key,
                "--batch-output-dir",
                str(out_dir),
                "--concurrency",
                "2",
                "scrape",
                "--input-file",
                input_path,
            ],
            timeout=120,
        )
        assert code == 0, err or out
        assert "Batch complete" in out
        assert out_dir.exists()
        files = list(out_dir.iterdir())
        assert len(files) >= 2, f"expected at least 2 output files, got {files}"
        exts = {f.suffix for f in files}
        assert ".html" in exts or ".json" in exts or ".txt" in exts
    finally:
        Path(input_path).unlink(missing_ok=True)
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
    out_dir = Path(input_path).parent / "batch_chatgpt_test"
    out_dir.mkdir(exist_ok=True)
    try:
        code, out, err = cli_run(
            [
                "--api-key",
                api_key,
                "--batch-output-dir",
                str(out_dir),
                "--concurrency",
                "2",
                "chatgpt",
                "--input-file",
                input_path,
            ],
            timeout=180,
        )
        assert code == 0, err or out
        assert "Batch complete" in out
        assert out_dir.exists()
        json_files = list(out_dir.glob("*.json"))
        assert len(json_files) >= 2, f"expected at least 2 .json files, got {list(out_dir.iterdir())}"
    finally:
        Path(input_path).unlink(missing_ok=True)
        if out_dir.exists():
            shutil.rmtree(out_dir)
