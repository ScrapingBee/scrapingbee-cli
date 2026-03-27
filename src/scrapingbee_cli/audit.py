"""Audit logging for exec features (--post-process, --on-complete, schedule).

Logs every shell command execution to a fixed location for forensics
and guard skill monitoring.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

AUDIT_LOG_PATH = Path.home() / ".config" / "scrapingbee-cli" / "audit.log"
MAX_LINES = 10_000


def log_exec(
    feature: str,
    command: str,
    *,
    input_source: str = "",
    output_dir: str = "",
) -> None:
    """Append an entry to the audit log.

    Format: ISO_TIMESTAMP | FEATURE | COMMAND | INPUT | OUTPUT_DIR
    """
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = f"{timestamp} | {feature} | {command} | {input_source} | {output_dir}\n"
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
        _rotate_if_needed()
    except OSError:
        pass


def read_audit_log(n: int = 50) -> str:
    """Read the last N lines of the audit log."""
    if not AUDIT_LOG_PATH.is_file():
        return "No audit log found."
    try:
        with open(AUDIT_LOG_PATH, encoding="utf-8") as f:
            lines = f.readlines()
        recent = lines[-n:] if len(lines) > n else lines
        return "".join(recent)
    except OSError:
        return "Could not read audit log."


def _rotate_if_needed() -> None:
    """Keep only the last MAX_LINES entries."""
    try:
        with open(AUDIT_LOG_PATH, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_LINES:
            with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-MAX_LINES:])
    except OSError:
        pass
