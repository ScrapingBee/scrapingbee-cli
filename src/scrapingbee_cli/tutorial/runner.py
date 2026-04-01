"""Tutorial runner — Step dataclass, state management, and interactive loop."""

from __future__ import annotations

import itertools
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import click

# ── Constants ──────────────────────────────────────────────────────────────────

MAX_SHOW_CHARS = 800
_W = 64  # display width for separators / line-wrap target
_BOX_W = _W - 5  # max content width inside "  │ " prefix (4 chars + 1 spare)
STATE_FILE = Path.home() / ".config" / "scrapingbee-cli" / "tutorial_state.json"
# UI colors — ANSI named so they adapt to every terminal theme automatically.
# Terminal "yellow" renders as gold/amber in most themes — a natural brand match.

# Input files written at tutorial start for batch/chatgpt steps.
BOOK_URLS = [
    "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
    "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html",
    "https://books.toscrape.com/catalogue/soumission_998/index.html",
    "https://books.toscrape.com/catalogue/sharp-objects_997/index.html",
    "https://books.toscrape.com/catalogue/sapiens-a-brief-history-of-humankind_996/index.html",
]

BOOK_PROMPTS = [
    "Recommend 3 mystery novels similar to Sharp Objects by Gillian Flynn",
    "What makes Sapiens by Yuval Noah Harari a bestseller?",
    "List the main themes in Tipping the Velvet by Sarah Waters",
]


def prepare_tutorial_files(output_dir: Path) -> None:
    """Write urls.txt and prompts.txt used by batch / chatgpt steps."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "urls.txt").write_text("\n".join(BOOK_URLS) + "\n", encoding="utf-8")
    (output_dir / "prompts.txt").write_text("\n".join(BOOK_PROMPTS) + "\n", encoding="utf-8")


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class Step:
    id: str  # e.g. "CH01-S01"
    chapter: int
    chapter_name: str
    title: str
    explanation: str  # Shown before the prompt; \n-separated lines
    args: list[str]  # Args after "scrapingbee"; {OUT} is substituted with output_dir
    what_to_notice: str  # Key things to look for after the command runs
    max_show_chars: int = MAX_SHOW_CHARS
    stream_output: bool = False  # If True, output streams live (crawl / batch)
    preview_file: str | None = None  # {OUT}/path — show inline preview after success
    preview_lines: int = 15  # Max lines shown in the preview box
    prereq_path: str | None = None  # {OUT}/path that must exist before this step runs
    prereq_step_id: str | None = None  # Step ID to auto-run if prereq_path is missing
    prereq_glob: str | None = None  # If set, prereq_path must also contain files matching this glob
    prereq_hint: str | None = None  # Human-readable reason shown when prereq is auto-run


@dataclass
class TutorialState:
    output_dir: str
    completed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def save(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(
                {
                    "output_dir": self.output_dir,
                    "completed": self.completed,
                    "skipped": self.skipped,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls) -> TutorialState | None:
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return cls(
                output_dir=data.get("output_dir", ""),
                completed=data.get("completed", []),
                skipped=data.get("skipped", []),
            )
        except Exception:
            return None

    @classmethod
    def clear(cls) -> None:
        try:
            STATE_FILE.unlink()
        except FileNotFoundError:
            pass


# ── Binary discovery ───────────────────────────────────────────────────────────


def find_binary() -> str:
    """Return path to the scrapingbee binary, preferring the local venv."""
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates = [
        str(project_root / ".venv" / "bin" / "scrapingbee"),
        shutil.which("scrapingbee") or "",
    ]
    for c in candidates:
        if not c:
            continue
        try:
            r = subprocess.run([c, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    click.echo(click.style("ERROR: 'scrapingbee' binary not found.", fg="red"), err=True)
    click.echo("  Install: pip install scrapingbee-cli", err=True)
    raise SystemExit(1)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _preview_hint(path: Path) -> str:
    """Return a shell command to preview the file."""
    ext = path.suffix.lower()
    is_mac = platform.system() == "Darwin"
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"):
        return f"open {path}" if is_mac else f"xdg-open {path}"
    return f"head -30 {path}"


def _osc8_link(path: Path) -> str:
    """Return an OSC 8 terminal hyperlink for a file path (clickable in iTerm2 / modern terminals)."""
    uri = path.resolve().as_uri()
    esc = "\x1b"
    return f"{esc}]8;;{uri}{esc}\\{path}{esc}]8;;{esc}\\"


# ── Runner ─────────────────────────────────────────────────────────────────────


class TutorialRunner:
    def __init__(self, binary: str, state: TutorialState) -> None:
        self.binary = binary
        self.state = state
        self._all_steps: list[Step] = []  # set by run(); used for prereq lookup

    # ── Substitution ────────────────────────────────────────────────────────

    def _sub(self, s: str) -> str:
        return s.replace("{OUT}", self.state.output_dir)

    def _display_sub(self, s: str) -> str:
        """Substitute {OUT} with a path relative to cwd (for display only)."""
        try:
            rel = Path(self.state.output_dir).relative_to(Path.cwd())
            return s.replace("{OUT}", str(rel))
        except ValueError:
            return self._sub(s)  # fallback to absolute if outside cwd

    def _resolved(self, args: list[str]) -> list[str]:
        resolved = [self._sub(a) for a in args]
        # Auto-inject --overwrite so output-file steps never prompt on re-run.
        if "--output-file" in resolved and "--overwrite" not in resolved:
            resolved.append("--overwrite")
        return resolved

    def _display_args(self, args: list[str]) -> list[str]:
        return [self._display_sub(a) for a in args]

    # ── Inline API key collection ────────────────────────────────────────────

    def _masked_input(self, prompt: str) -> str:
        """Read a line from stdin echoing '*' for each character (termios-based)."""
        if not sys.stdin.isatty():
            sys.stderr.write(prompt)
            sys.stderr.flush()
            return sys.stdin.readline().rstrip("\n")
        try:
            import termios
        except ImportError:
            import getpass

            return getpass.getpass(prompt)

        sys.stderr.write(prompt)
        sys.stderr.flush()
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        chars: list[str] = []
        try:
            new = termios.tcgetattr(fd)
            new[3] &= ~(termios.ECHO | termios.ICANON)
            new[6][termios.VMIN] = 1
            new[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, new)
            while True:
                ch = sys.stdin.read(1)
                if ch in ("\n", "\r"):
                    sys.stderr.write("\n")
                    sys.stderr.flush()
                    break
                if ch in ("\x7f", "\x08"):  # DEL / Backspace
                    if chars:
                        chars.pop()
                        sys.stderr.write("\b \b")
                        sys.stderr.flush()
                elif ch == "\x03":  # Ctrl+C
                    sys.stderr.write("\n")
                    sys.stderr.flush()
                    raise KeyboardInterrupt
                elif ch == "\x04" and not chars:  # Ctrl+D on empty input
                    raise EOFError
                elif ch and ord(ch) >= 32:
                    chars.append(ch)
                    sys.stderr.write("*")
                    sys.stderr.flush()
        finally:
            # TCSAFLUSH: wait for output to drain AND discard pending input.
            # This clears any residual characters before returning to the caller.
            termios.tcsetattr(fd, termios.TCSAFLUSH, old)
        return "".join(chars)

    def _validate_api_key(self, key: str) -> tuple[bool, str]:
        """Returns (valid, error_message). Uses stdlib urllib — no extra deps."""
        import urllib.error
        import urllib.request

        url = f"https://app.scrapingbee.com/api/v1/usage?api_key={key}"
        try:
            with urllib.request.urlopen(url, timeout=15):
                return True, ""
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "Invalid API key — check it and try again."
            return False, f"API returned status {e.code}."
        except OSError as e:
            return False, f"Network error: {e}"
        except Exception as e:
            return False, f"Could not validate: {e}"

    def _collect_api_key(self) -> bool:
        """Collect, validate, and save an API key inline. Returns True on success."""
        from ..config import save_api_key_to_dotenv

        if os.environ.get("SCRAPINGBEE_API_KEY"):
            click.echo(click.style("  ✓ API key already saved.", fg="green"))
            return True

        click.echo()
        click.echo(
            click.style("  Enter your ScrapingBee API key.", fg="yellow")
            + click.style("  (https://www.scrapingbee.com/)", fg="bright_black")
        )
        click.echo()

        while True:
            try:
                key = self._masked_input("  API key: ").strip()
            except (KeyboardInterrupt, EOFError):
                click.echo()
                return False

            if not key:
                click.echo(click.style("  No key entered — try again.", fg="red"))
                continue

            sys.stderr.write("  Validating...")
            sys.stderr.flush()
            valid, err = self._validate_api_key(key)
            sys.stderr.write("\r" + " " * 20 + "\r")
            sys.stderr.flush()

            if valid:
                os.environ["SCRAPINGBEE_API_KEY"] = key
                save_api_key_to_dotenv(key)
                click.echo(click.style("  ✓ API key validated and saved.", fg="green"))
                return True

            click.echo(click.style(f"  ✗ {err}", fg="red"))
            click.echo(click.style("  Try again:", fg="yellow"))

    # ── Display helpers ──────────────────────────────────────────────────────

    def _hr(self, char: str = "─") -> None:
        click.echo(click.style(char * _W, fg="bright_black"))

    def _header(self, step: Step, n: int, total: int) -> None:
        click.echo()
        self._hr()
        click.echo(
            click.style(f"  Chapter {step.chapter} · {step.chapter_name}", bold=True)
            + click.style(f"   Step {n}/{total}", fg="bright_black")
        )
        self._hr()
        click.echo()
        click.echo(click.style(f"  {step.title}", bold=True))
        click.echo()

    def _show_explanation(self, step: Step) -> None:
        for line in step.explanation.strip().splitlines():
            click.echo("  " + line)
        click.echo()

    @staticmethod
    def _shell_quote(value: str) -> str:
        """Wrap *value* in single quotes if it contains shell-special characters.
        URLs and values with braces/spaces are always quoted."""
        if not value:
            return value
        needs_quote = (
            any(c in value for c in " {}()$\"';&|<>!*?[]#~")
            or value.startswith("http://")
            or value.startswith("https://")
        )
        if needs_quote:
            return "'" + value.replace("'", "'\\''") + "'"
        return value

    # Command-box syntax — ANSI named colors, adapts to user's terminal theme.
    _C_BIN = {"bold": True}  # scrapingbee
    _C_SUB = {"bold": True}  # subcommand (scrape, crawl, etc.)
    _C_FLAG = {"fg": "cyan"}  # --flags
    _C_STR = {"fg": "green"}  # 'quoted strings'
    _C_NUM = {"fg": "yellow"}  # numbers
    _C_VAL = {}  # plain values (terminal default)

    def _show_cmd(self, resolved: list[str]) -> None:
        """Display the command in a read-only box with syntax highlighting."""
        inner = _W - 4
        max_content = inner - 1

        # Build colored segments: list of (plain_text, color_kwargs) tuples.
        # Each segment is one token; wrapping happens on the plain text later.
        segments: list[tuple[str, dict]] = []
        tokens = ["scrapingbee"] + resolved
        i = 0

        # Binary
        segments.append((tokens[0], self._C_BIN))
        i = 1

        # Subcommand + positional args
        while i < len(tokens) and not tokens[i].startswith("-"):
            val = self._shell_quote(tokens[i])
            color = self._C_SUB if i == 1 else self._C_STR
            segments.append((" " + val, color))
            i += 1

        # Flags and their values
        while i < len(tokens):
            if (
                i + 1 < len(tokens)
                and tokens[i].startswith("-")
                and not tokens[i + 1].startswith("-")
            ):
                val = self._shell_quote(tokens[i + 1])
                try:
                    float(tokens[i + 1])
                    val_color = self._C_NUM
                except ValueError:
                    val_color = self._C_STR if "'" in val or '"' in val else self._C_VAL
                segments.append(("\n  " + tokens[i], self._C_FLAG))
                segments.append((" " + val, val_color))
                i += 2
            else:
                segments.append(("\n  " + tokens[i], self._C_FLAG))
                i += 1

        # Flatten segments into tagged characters: build a list of (char, color)
        # so wrapping preserves color across line breaks.
        tagged: list[tuple[str, dict]] = []
        for text, color in segments:
            for ch in text:
                tagged.append((ch, color))

        # Render into wrapped lines. \n forces a new line.
        lines: list[str] = []  # styled strings
        plain_lens: list[int] = []  # plain-text width per line
        cur_styled = ""
        cur_len = 0
        for ch, color in tagged:
            if ch == "\n":
                lines.append(cur_styled)
                plain_lens.append(cur_len)
                cur_styled = ""
                cur_len = 0
                continue
            # Wrap if we'd exceed max_content
            if cur_len >= max_content:
                # Try to preserve indent for continuation
                lines.append(cur_styled)
                plain_lens.append(cur_len)
                cur_styled = click.style("  ", **self._C_VAL)
                cur_len = 2
            cur_styled += click.style(ch, **color)
            cur_len += 1
        if cur_styled:
            lines.append(cur_styled)
            plain_lens.append(cur_len)

        click.echo(click.style("  Command:", fg="bright_black"))
        click.echo(click.style("  ┌" + "─" * inner + "┐", fg="bright_black"))
        for styled, plen in zip(lines, plain_lens):
            padding = " " * max(0, inner - 1 - plen)
            click.echo(
                click.style("  │ ", fg="bright_black")
                + styled
                + click.style(padding + "│", fg="bright_black")
            )
        click.echo(click.style("  └" + "─" * inner + "┘", fg="bright_black"))
        click.echo()

    def _box_lines(self, text: str) -> list[str]:
        """Split text into lines that fit inside the output box, wrapping long ones."""
        result = []
        for line in text.splitlines():
            if len(line) <= _BOX_W:
                result.append(line)
                continue
            # Wrap long line at word boundary, then slash, then hard-cut.
            while len(line) > _BOX_W:
                bp = line.rfind(" ", 0, _BOX_W)
                if bp <= 0:
                    bp = line.rfind("/", 0, _BOX_W)
                if bp <= 0:
                    bp = _BOX_W
                result.append(line[:bp])
                line = line[bp:].lstrip()
            if line:
                result.append(line)
        return result

    def _show_what_to_notice(self, step: Step) -> None:
        click.echo()
        click.echo(click.style("  What to notice:", fg="yellow"))
        for line in step.what_to_notice.strip().splitlines():
            click.echo("    " + self._sub(line))

    def _show_preview(self, step: Step) -> None:
        """Show up to preview_lines *display* lines of step.preview_file in an inline box.

        preview_lines caps rendered lines after word-wrap, so a single long JSON
        line doesn't blow past the limit by wrapping into many rows.
        """
        if not step.preview_file:
            return
        path = Path(self._sub(step.preview_file))
        if not path.exists():
            return
        ext = path.suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"):
            return  # binary — can't show in terminal
        try:
            raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        inner = _W - 4
        display_lines: list[str] = []
        truncated = False
        for raw_ln in raw_lines:
            for wrapped in self._box_lines(raw_ln) or [""]:
                if len(display_lines) >= step.preview_lines:
                    truncated = True
                    break
                display_lines.append(wrapped)
            if truncated:
                break
        click.echo()
        click.echo(click.style(f"  Preview — {path.name}:", fg="bright_black"))
        click.echo(click.style("  ┌" + "─" * inner + "┐", fg="bright_black"))
        for ln in display_lines:
            padding = " " * max(0, inner - 1 - len(ln))
            click.echo(
                click.style("  │ ", fg="bright_black")
                + ln
                + click.style(padding + "│", fg="bright_black")
            )
        if truncated:
            label = "  … (truncated)"
            padding = " " * max(0, inner - 1 - len(label))
            click.echo(
                click.style("  │ ", fg="bright_black")
                + click.style(label, fg="bright_black")
                + click.style(padding + "│", fg="bright_black")
            )
        click.echo(click.style("  └" + "─" * inner + "┘", fg="bright_black"))

    def _show_file_hints(self, resolved: list[str]) -> None:
        """Print 'Saved to' (as a clickable link) + preview hint."""
        for flag, kind in (("--output-file", "file"), ("--output-dir", "dir")):
            try:
                idx = resolved.index(flag)
                out_path = Path(resolved[idx + 1]).resolve()
            except (ValueError, IndexError):
                continue
            try:
                if kind == "file" and out_path.exists():
                    size_kb = out_path.stat().st_size / 1024
                    link = _osc8_link(out_path)
                    click.echo(
                        click.style("  Saved to: ", fg="green")
                        + click.style(link, fg="cyan", underline=True)
                        + click.style(f" ({size_kb:.1f} KB)", fg="green")
                    )
                elif kind == "dir" and out_path.exists():
                    n_files = sum(1 for f in out_path.rglob("*") if f.is_file())
                    link = _osc8_link(out_path)
                    click.echo(
                        click.style("  Output dir: ", fg="green")
                        + click.style(link, fg="cyan", underline=True)
                        + click.style(f" ({n_files} files)", fg="green")
                    )
            except OSError:
                pass

    def _show_output(
        self,
        stdout: str,
        stderr: str,
        step: Step,
        returncode: int,
        resolved: list[str],
    ) -> None:
        """Display captured output inline or save to file when large."""
        # Show file/dir hints only on success — no point pointing to a
        # partial/missing file when the command failed.
        if returncode == 0:
            self._show_file_hints(resolved)

        combined = "\n".join(filter(None, [stdout.strip(), stderr.strip()]))
        if not combined:
            click.echo(
                click.style("  ✗ Exit code " + str(returncode), fg="red")
                if returncode != 0
                else click.style("  ✓ Done", fg="green")
            )
            return

        inner = _W - 4
        label = "─ output "
        click.echo(click.style("  ┌" + label + "─" * (inner - len(label)) + "┐", fg="bright_black"))

        def _box_row(text: str, dim: bool = False) -> None:
            padding = " " * max(0, inner - 1 - len(text))
            styled = click.style(text, fg="bright_black") if dim else text
            click.echo(
                click.style("  │ ", fg="bright_black")
                + styled
                + click.style(padding + "│", fg="bright_black")
            )

        if len(combined) <= step.max_show_chars:
            for ln in self._box_lines(combined):
                _box_row(ln)
        else:
            preview = combined[: step.max_show_chars]
            for ln in self._box_lines(preview):
                _box_row(ln)
            # Save full output alongside other tutorial files.
            save_path = Path(self.state.output_dir) / f"{step.id}-output.txt"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(combined, encoding="utf-8")
            _box_row(f"… {len(combined):,} chars — full output saved to:", dim=True)
            _box_row(f"  {save_path}", dim=True)

        click.echo(click.style("  └" + "─" * inner + "┘", fg="bright_black"))
        click.echo(
            click.style("  ✗ Exit code " + str(returncode), fg="red")
            if returncode != 0
            else click.style("  ✓ Done", fg="green")
        )

    def _prompt(self, *, after_run: bool) -> str:
        """Prompt for a keypress; return action string.

        Controls (both states):
          ←/→  navigate prev/next
          Q    quit
        Before run:
          Enter  run the command
        After run:
          Enter  rerun the command
        All other keys are silently ignored.
        """
        click.echo()

        _right = "\x1b[C"
        _left = "\x1b[D"

        def _k(label: str) -> str:
            return click.style(label, fg="bright_white", bold=True)

        def _d(text: str) -> str:
            return click.style(text, fg="bright_black")

        if not after_run:
            click.echo(
                _d("  ")
                + _k("←")
                + _d(" prev  ")
                + _k("→")
                + _d(" next  ")
                + _k("Enter")
                + _d(" run  ")
                + _k("^C")
                + _d(" quit"),
                nl=False,
            )
        else:
            click.echo(
                _d("  ")
                + _k("←")
                + _d(" prev  ")
                + _k("→")
                + _d(" next  ")
                + _k("Enter")
                + _d(" rerun  ")
                + _k("^C")
                + _d(" quit"),
                nl=False,
            )

        while True:
            try:
                key = click.getchar()
            except (EOFError, KeyboardInterrupt):
                click.echo()
                return "quit"
            if key == "\x03":  # Ctrl+C
                click.echo()
                return "quit"
            if key == _right:
                click.echo()
                return "next"
            if key == _left:
                click.echo()
                return "prev"
            if key in ("\r", "\n"):
                click.echo()
                return "rerun" if after_run else "run"
            # all other keys silently ignored

    def _run_with_spinner(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        """Run a subprocess with a spinner. Uses capture_output=True (safe for all
        non-stream steps since grandchild-pipe cases are handled by stream_output=True)."""
        frames = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        done = threading.Event()
        elapsed: list[float] = [0.0]
        _tick = 0.1

        def _spin() -> None:
            while not done.is_set():
                secs = int(elapsed[0])
                msg = f"  Waiting for response... ({secs}s)"
                frame = click.style(next(frames), fg="yellow")
                sys.stderr.write(f"\r{frame} {msg}")
                sys.stderr.flush()
                time.sleep(_tick)
                elapsed[0] += _tick
            sys.stderr.write("\r" + " " * 54 + "\r")
            sys.stderr.flush()

        t = threading.Thread(target=_spin, daemon=True)
        t.start()
        try:
            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONWARNINGS": "ignore::DeprecationWarning"},
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            result = subprocess.CompletedProcess(
                cmd, returncode=1, stdout="", stderr="Request timed out after 180s."
            )
        finally:
            done.set()
            t.join()
        return result

    # ── Step execution ───────────────────────────────────────────────────────

    def _flush_stdin(self) -> None:
        """Discard any keystrokes buffered while a subprocess was running.

        Without this, an Enter press during the spinner (e.g. while waiting 30s)
        gets queued and immediately consumed as "rerun" by the next getchar().
        """
        try:
            import termios

            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        except Exception:
            pass

    def _run_prereq(self, step: Step) -> bool:
        """Run a prerequisite step automatically (no user prompt). Returns True on success.

        Recursively resolves the prereq's own prerequisites first.
        """
        # Recursively resolve this step's own prereqs first
        if step.prereq_path and step.prereq_step_id:
            prereq_path = Path(self._sub(step.prereq_path))
            path_missing = not prereq_path.exists()
            glob_missing = (
                step.prereq_glob is not None
                and prereq_path.is_dir()
                and not any(prereq_path.glob(step.prereq_glob))
            )
            if path_missing or glob_missing:
                parent = next((s for s in self._all_steps if s.id == step.prereq_step_id), None)
                if parent:
                    hint = step.prereq_hint or f'"{parent.title}" needs to run first'
                    click.echo(click.style(f"  Note: {hint}", fg="yellow"))
                    click.echo()
                    if not self._run_prereq(parent):
                        return False

        res = self._resolved(step.args)
        self._show_cmd(self._display_args(step.args))
        click.echo()
        self._flush_stdin()
        if step.stream_output:
            returncode = subprocess.run(
                [self.binary] + res,
                env={**os.environ, "PYTHONWARNINGS": "ignore::DeprecationWarning"},
            ).returncode
        else:
            result = self._run_with_spinner([self.binary] + res)
            returncode = result.returncode
            if result.stdout or result.stderr:
                self._show_output(result.stdout, result.stderr, step, returncode, res)
        self._flush_stdin()
        if returncode == 0:
            file_count_msg = ""
            try:
                out_idx = res.index("--output-dir")
                out_dir = Path(res[out_idx + 1])
                if out_dir.is_dir():
                    _skip = {"manifest.json", "failures.txt"}
                    n_files = sum(
                        1
                        for f in out_dir.iterdir()
                        if f.is_file() and f.name not in _skip and not f.name.startswith(".")
                    )
                    if n_files:
                        rel = out_dir.relative_to(Path.cwd()) if out_dir.is_absolute() else out_dir
                        file_count_msg = f" ({n_files} file{'s' if n_files != 1 else ''} in {rel}/)"
            except (ValueError, IndexError, OSError):
                pass
            click.echo(click.style(f"  ✓ Done.{file_count_msg} Continuing...", fg="green"))
        else:
            click.echo(
                click.style(
                    f"  ✗ Prerequisite failed (exit {returncode}). Proceeding anyway.", fg="red"
                )
            )
        click.echo()
        return returncode == 0

    def run_step(self, step: Step, n: int, total: int) -> str:
        """Run one step interactively. Returns 'completed', 'skipped', or 'quit'."""
        while True:
            self._header(step, n, total)
            self._show_explanation(step)
            res = self._resolved(step.args)
            self._show_cmd(self._display_args(step.args))

            action = self._prompt(after_run=False)
            if action == "quit":
                return "quit"
            if action == "next":
                return "skipped"
            if action == "prev":
                return "prev"

            # action == "run"
            click.echo()

            # ── Auth step: handled inline (no subprocess) ────────────────────
            if step.args == ["auth"]:
                success = self._collect_api_key()

            # ── All other steps ───────────────────────────────────────────────
            else:
                # 1. Ensure API key is available first (before prereqs or running)
                if not os.environ.get("SCRAPINGBEE_API_KEY"):
                    click.echo(click.style("  API key not set. Enter it to continue:", fg="yellow"))
                    if not self._collect_api_key():
                        self._flush_stdin()
                        action = self._prompt(after_run=True)
                        if action == "quit":
                            return "quit"
                        if action == "rerun":
                            continue
                        if action == "prev":
                            return "prev"
                        return "skipped"
                    click.echo()

                # 2. Auto-run prerequisites before executing this step
                if step.prereq_path and step.prereq_step_id:
                    prereq_path = Path(self._sub(step.prereq_path))
                    path_missing = not prereq_path.exists()
                    glob_empty = (
                        step.prereq_glob is not None
                        and prereq_path.is_dir()
                        and not any(prereq_path.glob(step.prereq_glob))
                    )
                    if path_missing or glob_empty:
                        prereq = next(
                            (s for s in self._all_steps if s.id == step.prereq_step_id), None
                        )
                        if prereq:
                            hint = step.prereq_hint or f'"{prereq.title}" needs to run first'
                            click.echo(click.style(f"  Note: {hint}", fg="yellow"))
                            click.echo()
                            ok = self._run_prereq(prereq)
                            if ok:
                                self.state.completed.append(prereq.id)
                                self.state.save()
                            click.echo()

                self._flush_stdin()  # discard any residual input before subprocess
                if step.stream_output:
                    returncode = subprocess.run(
                        [self.binary] + res,
                        env={**os.environ, "PYTHONWARNINGS": "ignore::DeprecationWarning"},
                    ).returncode
                    success = returncode == 0
                    if success:
                        self._show_file_hints(res)
                    else:
                        click.echo(click.style(f"  ✗ Exit code {returncode}", fg="red"))
                else:
                    result = self._run_with_spinner([self.binary] + res)
                    success = result.returncode == 0
                    self._show_output(result.stdout, result.stderr, step, result.returncode, res)

            # Flush any keystrokes typed while waiting for the subprocess.
            self._flush_stdin()

            if success:
                self._show_what_to_notice(step)
                self._show_preview(step)

            action = self._prompt(after_run=True)
            if action == "quit":
                return "quit"
            if action == "rerun":
                continue
            if action == "prev":
                return "prev"
            # action == "next"
            return "completed"

    # ── Main loop ────────────────────────────────────────────────────────────

    def run(self, steps: list[Step], start_i: int = 0) -> None:
        self._all_steps = steps
        total = len(steps)
        i = start_i
        while i < len(steps):
            step = steps[i]
            # Auto-skip already-done steps when moving forward.
            if step.id in self.state.completed or step.id in self.state.skipped:
                i += 1
                continue
            result = self.run_step(step, i + 1, total)
            if result == "completed":
                self.state.completed.append(step.id)
                self.state.save()
                i += 1
            elif result == "skipped":
                self.state.skipped.append(step.id)
                self.state.save()
                i += 1
            elif result == "prev":
                if i == 0:
                    click.echo("  Already at the first step.", err=True)
                else:
                    # Go back one step (remove it from completed/skipped so it re-runs).
                    prev_id = steps[i - 1].id
                    self.state.completed = [s for s in self.state.completed if s != prev_id]
                    self.state.skipped = [s for s in self.state.skipped if s != prev_id]
                    self.state.save()
                    i -= 1
            elif result == "quit":
                click.echo()
                click.echo(
                    "  Progress saved. Run "
                    + click.style("scrapingbee tutorial", fg="yellow")
                    + " to resume."
                )
                click.echo()
                return

        click.echo()
        self._hr()
        click.echo()
        click.echo(click.style("  Tutorial complete!", fg="green", bold=True))
        click.echo()
        click.echo("  All output is in: " + click.style(self.state.output_dir, fg="cyan"))
        click.echo()
        TutorialState.clear()
