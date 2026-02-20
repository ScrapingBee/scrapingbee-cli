"""Batch mode: read input file, run concurrent requests, write output."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .client import Client, parse_usage
from .config import get_api_key


def read_input_file(path: str) -> list[str]:
    """Read non-empty trimmed lines from file (one input per line)."""
    with open(path, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if not lines:
        raise ValueError(f'input file "{path}" has no non-empty lines')
    return lines


def get_batch_usage(api_key_flag: str | None) -> dict:
    """Return usage info (max_concurrency, credits) from usage API."""
    key = get_api_key(api_key_flag)
    client = Client(key)
    body, _, code = client.usage()
    if code != 200:
        raise RuntimeError(f"usage API returned HTTP {code}")
    return parse_usage(body)


def validate_batch_run(
    user_concurrency: int, num_inputs: int, usage: dict
) -> None:
    """Raise ValueError if batch should not run (concurrency or credits)."""
    max_concurrency = usage.get("max_concurrency", 5)
    if user_concurrency > 0 and user_concurrency > max_concurrency:
        raise ValueError(
            f"concurrency {user_concurrency} exceeds your plan limit of {max_concurrency} "
            "(check with: scrapingbee usage)"
        )
    credits = usage.get("credits", 0)
    if credits > 0 and num_inputs > credits:
        raise ValueError(
            f"not enough credits: {num_inputs} requested, {credits} available "
            "(check with: scrapingbee usage)"
        )


def resolve_batch_concurrency(
    user_concurrency: int, usage: dict, _num_inputs: int
) -> int:
    """Return concurrency to use: user value if set, else usage limit."""
    if user_concurrency > 0:
        return user_concurrency
    return usage.get("max_concurrency", 5)


@dataclass
class BatchResult:
    """Result of one batch item."""

    index: int
    input: str
    body: bytes
    status_code: int
    error: Exception | None


def run_batch(
    inputs: list[str],
    concurrency: int,
    fn: Callable[[str], tuple[bytes, int, Exception | None]],
) -> list[BatchResult]:
    """Run fn for each input with up to concurrency workers; preserve order."""
    concurrency = min(concurrency or 1, len(inputs))
    results: list[BatchResult | None] = [None] * len(inputs)

    def do_one(i: int, inp: str) -> tuple[int, BatchResult]:
        body, status_code, err = fn(inp)
        return i, BatchResult(
            index=i, input=inp, body=body, status_code=status_code, error=err
        )

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(do_one, i, inp): i for i, inp in enumerate(inputs)}
        for future in as_completed(futures):
            _i, result = future.result()
            results[result.index] = result

    return [r for r in results if r is not None]


def default_batch_output_dir() -> str:
    """Default folder name for batch output (batch_<timestamp>)."""
    return "batch_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def write_batch_output_to_dir(
    results: list[BatchResult],
    output_dir: str | None,
    verbose: bool,
) -> str:
    """Write 1.txt, 2.txt, ... and N.err for failures; return absolute path."""
    output_dir = output_dir or default_batch_output_dir()
    abs_dir = str(Path(output_dir).resolve())
    os.makedirs(abs_dir, exist_ok=True)
    for r in results:
        n = r.index + 1
        if r.error is not None:
            import sys
            print(f'Item {n} ({r.input!r}): {r.error}', file=sys.stderr)
            if r.body:
                err_path = os.path.join(abs_dir, f"{n}.err")
                with open(err_path, "wb") as f:
                    f.write(r.body)
            continue
        if verbose:
            import sys
            print(f"Item {n}: HTTP {r.status_code}", file=sys.stderr)
        out_path = os.path.join(abs_dir, f"{n}.txt")
        with open(out_path, "wb") as f:
            f.write(r.body)
    return abs_dir
