"""Pytest fixtures and shared helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
    )
    return result.returncode, result.stdout or "", result.stderr or ""


@pytest.fixture(scope="session")
def cli():
    """Session fixture: (get_cli, run)."""
    return get_cli(), cli_run


@pytest.fixture(scope="session")
def api_key() -> str | None:
    """Session fixture: SCRAPINGBEE_API_KEY if set."""
    return os.environ.get("SCRAPINGBEE_API_KEY")


@pytest.fixture
def no_api_key_env():
    """Environment without SCRAPINGBEE_API_KEY (for no-key tests)."""
    return {k: v for k, v in os.environ.items() if k != "SCRAPINGBEE_API_KEY"}


def _cleanup_batch_folders(root_path: Path) -> None:
    """Remove batch_* directories under root_path (integration test cleanup)."""
    if not root_path.is_dir():
        return
    for path in root_path.iterdir():
        if path.is_dir() and path.name.startswith("batch_"):
            try:
                shutil.rmtree(path)
            except OSError:
                pass


@pytest.fixture(scope="session", autouse=True)
def cleanup_batch_folders_after_tests(request: pytest.FixtureRequest) -> None:
    """After the test session, remove batch_* directories in the project root."""
    yield
    root = Path(request.config.rootpath)
    _cleanup_batch_folders(root)
