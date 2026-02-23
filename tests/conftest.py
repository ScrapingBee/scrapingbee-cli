"""Pytest fixtures and shared helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import pytest


def get_cli() -> list[str]:
    """Return CLI invocation: scrapingbee binary or python -m scrapingbee_cli.cli."""
    exe = shutil.which("scrapingbee")
    if exe:
        return [exe]
    return [sys.executable, "-m", "scrapingbee_cli.cli"]


def cli_run(
    args: list[str],
    *,
    timeout: int = 60,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
) -> tuple[int, str, str]:
    """Run CLI with args; return (returncode, stdout, stderr)."""
    cmd = get_cli() + args
    use_env = env if env is not None else os.environ.copy()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=use_env,
        cwd=cwd,
    )
    return result.returncode, result.stdout or "", result.stderr or ""


@pytest.fixture(scope="session")
def cli():
    """Session fixture: (get_cli, run)."""
    return get_cli(), cli_run


@pytest.fixture(scope="session")
def api_key() -> str | None:
    """Session fixture: SCRAPINGBEE_API_KEY from env or from config file (e.g. after scrapingbee auth)."""
    from scrapingbee_cli.config import load_dotenv

    load_dotenv()
    return os.environ.get("SCRAPINGBEE_API_KEY") or None


@pytest.fixture
def no_api_key_env(tmp_path):
    """(env, cwd) for no-API-key tests: no SCRAPINGBEE_API_KEY, HOME and cwd set to tmp_path so CLI cannot load key from .env or ~/.config."""
    env = {k: v for k, v in os.environ.items() if k != "SCRAPINGBEE_API_KEY"}
    env["HOME"] = str(tmp_path)
    return env, str(tmp_path)


def _cleanup_test_results(root_path: Path) -> None:
    """Remove test_results/ in project root (integration test batch/crawl output only)."""
    test_results = root_path / "test_results"
    if test_results.is_dir():
        try:
            shutil.rmtree(test_results)
        except OSError:
            pass


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_results_after_tests(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """After the test session, remove test_results/ so genuine batch_* / crawl_* in root are untouched."""
    yield
    root = Path(request.config.rootpath)
    _cleanup_test_results(root)
