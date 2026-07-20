"""PTY regression tests for the interactive REPL (pexpect + pyte).

Drives the real ``scrapingbee`` REPL under a pseudo-terminal and asserts behavior
from the rendered screen grid. These tests are Unix-only (termios/pexpect) and
timing-sensitive, so each:
  * is marked ``@pytest.mark.pty`` (deselect with ``-m "not pty"``) and skipped on Windows,
  * pumps **until a condition** (not a fixed sleep) for robustness on slow CI,
  * asserts the on-screen ``reverse`` highlight (deterministic in pyte) rather than the
    OS clipboard — which would need a platform tool and would touch the real clipboard.
    The drag-copy path test hijacks ``pbcopy`` / ``wl-copy`` / ``xclip`` / ``xsel`` on
    ``PATH`` so the copied bytes are captured without touching the real clipboard.

The clipboard *write* itself is covered by a separate unit test (test_scrollback_selection.py).
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pexpect = pytest.importorskip("pexpect")
pyte = pytest.importorskip("pyte")

pytestmark = [
    pytest.mark.pty,
    pytest.mark.skipif(sys.platform == "win32", reason="PTY tests need termios (Unix-only)"),
]

# Prefer the scrapingbee next to the test-runner's python (the editable install
# under test) over any stale copy earlier on PATH.
SB = os.path.join(os.path.dirname(sys.executable), "scrapingbee")
if not os.path.exists(SB):
    SB = shutil.which("scrapingbee")
needs_cli = pytest.mark.skipif(not SB, reason="scrapingbee console script not found")
COLS, ROWS = 110, 32
_MINIMAL_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

# Unique markers for the scroll regression — must not appear in the banner/help.
_SCROLL_TOP = "PTY_SCROLL_TOP_MARKER"
_SCROLL_BOTTOM = "PTY_SCROLL_BOTTOM_MARKER"


class _MockApiHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Spb-Cost", "5")
        self.end_headers()
        self.wfile.write(_MINIMAL_PNG)


def _start_mock_api_server():
    server = HTTPServer(("127.0.0.1", 0), _MockApiHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _write_sitecustomize(tmp_path) -> None:
    (tmp_path / "sitecustomize.py").write_text(
        """\
import os
_port = os.environ.get("SCRAPINGBEE_MOCK_API_PORT")
if _port:
    import scrapingbee_cli.config as _config
    _config.BASE_URL = f"http://127.0.0.1:{_port}"
""",
        encoding="utf-8",
    )


def _setup_exec_home(home, key: str = "dummy-pty-key") -> None:
    """Lay down config so ``!shell`` works under a temp HOME."""
    cfg = home / ".config" / "scrapingbee-cli"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / ".env").write_text(
        f'SCRAPINGBEE_API_KEY="{key}"\nSCRAPINGBEE_UNSAFE_VERIFIED="1"\n',
        encoding="utf-8",
    )


def _setup_fake_clipboard(tmp_path):
    clip_file = tmp_path / "clipboard.txt"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture = f'cat > "{clip_file}"'
    for name in ("pbcopy", "wl-copy", "xsel"):
        tool = bin_dir / name
        tool.write_text(f"#!/bin/sh\n{capture}\n", encoding="utf-8")
        tool.chmod(0o755)
    xclip = bin_dir / "xclip"
    xclip.write_text(f'#!/bin/sh\nwhile [ "$1" ]; do shift; done\n{capture}\n', encoding="utf-8")
    xclip.chmod(0o755)
    return clip_file, bin_dir


def _spawn(
    home,
    args=(),
    key="dummy-pty-key",
    *,
    extra_env=None,
    rows=ROWS,
    cols=COLS,
    exec_enabled=False,
):
    if exec_enabled:
        _setup_exec_home(home, key)
    env = dict(os.environ)
    env.update(HOME=str(home), SCRAPINGBEE_API_KEY=key, TERM="xterm-256color", PWD=str(home))
    if exec_enabled:
        env["SCRAPINGBEE_ALLOW_EXEC"] = "1"
    if extra_env:
        env.update(extra_env)
    child = pexpect.spawn(
        SB,
        list(args),
        dimensions=(rows, cols),
        env=env,
        encoding="utf-8",
        codec_errors="replace",
        timeout=20,
        cwd=str(home),
    )
    screen = pyte.Screen(cols, rows)
    return child, screen, pyte.Stream(screen)


def _text(screen):
    return "\n".join(line.rstrip() for line in screen.display)


def _reverse_cells(screen):
    return sum(
        1 for y in range(screen.lines) for x in range(screen.columns) if screen.buffer[y][x].reverse
    )


def _pump(child, screen, stream, secs):
    end = time.monotonic() + secs
    while time.monotonic() < end:
        try:
            stream.feed(child.read_nonblocking(1 << 16, 0.2))
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            return


def _pump_until(child, screen, stream, predicate, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            stream.feed(child.read_nonblocking(1 << 16, 0.2))
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            break
        if predicate(screen):
            return True
    return predicate(screen)


def _content_row(screen, default=13):
    disp = list(screen.display)
    for y in range(11, ROWS - 4):
        t = disp[y]
        if (
            len(t.strip()) > 15
            and "─" not in t
            and "❯" not in t
            and "ScrapingBee" not in t
            and "Web scraping" not in t
        ):
            return y, t
    return default, disp[default]


def _scrollback_lines(screen, *, top=11, bottom_margin=4):
    """Rows between the banner and the input/toolbar chrome."""
    end = max(top, screen.lines - bottom_margin)
    return [screen.display[y].rstrip() for y in range(top, end)]


def _scrollback_text(screen, **kwargs) -> str:
    return "\n".join(_scrollback_lines(screen, **kwargs))


def _marker_in_scrollback(screen, marker: str) -> bool:
    """True when ``marker`` appears as its own scrollback row (not the input echo)."""
    return any(line.strip() == marker for line in _scrollback_lines(screen))


def _drag(child, target, c1, c2):
    child.send(f"\x1b[<0;{c1 + 1};{target + 1}M")  # left press
    child.send(f"\x1b[<32;{c2 + 1};{target + 1}M")  # left-drag (motion)
    child.send(f"\x1b[<0;{c2 + 1};{target + 1}m")  # left release


def _path_span_in_line(line: str, path: str) -> tuple[int, int]:
    """Return inclusive ``(start, end)`` column indices for ``path`` in ``line``."""
    start = line.find(path)
    if start >= 0:
        return start, start + len(path) - 1
    basename = os.path.basename(path)
    idx = line.find(basename)
    assert idx >= 0, f"path not in line: {path!r} in {line!r}"
    start = idx
    while start > 0 and line[start - 1] not in " \t":
        start -= 1
    return start, idx + len(basename) - 1


def _saved_path_drag_coords(screen, saved_path: str) -> tuple[int, int, int, int]:
    """Return inclusive drag endpoints ``(r1, c1, r2, c2)`` for a Saved-to path."""
    disp = list(screen.display)
    basename = os.path.basename(saved_path)

    saved_row = None
    end_row = None
    for y in range(11, ROWS - 4):
        t = disp[y]
        if "❯" in t or "─" in t:
            continue
        if t.strip().startswith("✓"):
            break
        if "Saved to" in t:
            saved_row = y
        if saved_row is not None and ("Saved to" in t or "/" in t or basename in t):
            end_row = y

    assert saved_row is not None and end_row is not None, (
        f"path rows not found in:\n{_text(screen)}"
    )

    r1 = saved_row
    while r1 <= end_row and "/" not in disp[r1]:
        r1 += 1
    assert r1 <= end_row, f"path start row not found in:\n{_text(screen)}"
    c1 = disp[r1].find("/")

    end_line = disp[end_row]
    _, c2 = _path_span_in_line(end_line, saved_path)
    return r1, c1, end_row, c2


@needs_cli
def test_drag_copy_saved_screenshot_path(tmp_path):
    """Drag across a ``Saved to …/screenshot.png`` line copies the full path."""
    server, port = _start_mock_api_server()
    _write_sitecustomize(tmp_path)
    clip_file, bin_dir = _setup_fake_clipboard(tmp_path)
    (tmp_path / "abc").mkdir()
    saved_path = str((tmp_path / "abc" / "screenshot.png").resolve())

    extra_env = {
        "PYTHONPATH": str(tmp_path),
        "SCRAPINGBEE_MOCK_API_PORT": str(port),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    child, screen, stream = _spawn(tmp_path, extra_env=extra_env)
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no command prompt"
        child.send(
            "scrape https://example.com --output-file abc/screenshot.png --render-js false\r"
        )
        assert _pump_until(
            child,
            screen,
            stream,
            lambda s: "screenshot.png" in _text(s) and "Saved to" in _text(s),
            timeout=25.0,
        ), f"Saved path not on screen:\n{_text(screen)}"
        _pump(child, screen, stream, 0.3)

        r1, c1, r2, c2 = _saved_path_drag_coords(screen, saved_path)

        if clip_file.exists():
            clip_file.unlink()
        _drag_multi(child, r1, c1, r2, c2)
        assert _pump_until(
            child,
            screen,
            stream,
            lambda s: clip_file.is_file() and clip_file.stat().st_size > 0,
            timeout=5.0,
        ), "clipboard capture file was not written"
        copied = clip_file.read_text(encoding="utf-8").strip()
        flat = copied.replace("\n", "")
        assert flat.endswith(".png"), f"selection dropped final chars: {copied!r}"
        assert not flat.endswith(".pn"), f"selection missing final char: {copied!r}"
        assert os.path.realpath(flat) == os.path.realpath(saved_path), (
            f"expected {saved_path!r}, got {copied!r}"
        )
    finally:
        child.close(force=True)
        server.shutdown()


@needs_cli
def test_drag_selects_and_highlights(tmp_path):
    """Default mode: a left-drag over scrollback content paints a reverse highlight."""
    child, screen, stream = _spawn(tmp_path)
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no command prompt"
        child.send(":help\r")
        assert _pump_until(child, screen, stream, lambda s: "Complete" in _text(s)), "no help text"
        target, line = _content_row(screen)
        c1 = len(line) - len(line.lstrip())
        c2 = min(c1 + 20, len(line.rstrip()))
        _drag(child, target, c1, c2)
        assert _pump_until(child, screen, stream, lambda s: _reverse_cells(s) > 0), "no highlight"
    finally:
        child.close(force=True)


@needs_cli
def test_classic_mouse_no_drag_highlight(tmp_path):
    """--no-drag-copy: shows the mode chip and a drag produces NO selection highlight."""
    child, screen, stream = _spawn(tmp_path, args=["--no-drag-copy"])
    try:
        assert _pump_until(child, screen, stream, lambda s: "Scroll mode" in _text(s)), "no chip"
        child.send(":help\r")
        assert _pump_until(child, screen, stream, lambda s: "Complete" in _text(s))
        target, line = _content_row(screen)
        baseline = _reverse_cells(screen)
        _drag(child, target, 4, 24)
        _pump(child, screen, stream, 1.0)  # let any (incorrect) highlight render
        assert _reverse_cells(screen) == baseline, "classic mode must not drag-highlight"
    finally:
        child.close(force=True)


@needs_cli
def test_onboarding_q_quits(tmp_path):
    """First-run 'API key:' prompt (no key): the advertised :q must quit (bug #1 fix)."""
    child, screen, stream = _spawn(tmp_path, key="")
    try:
        assert _pump_until(child, screen, stream, lambda s: "API key:" in _text(s)), "no onboarding"
        child.send(":q\r")
        end = time.monotonic() + 8
        while time.monotonic() < end and child.isalive():
            try:
                child.read_nonblocking(1 << 16, 0.2)
            except pexpect.TIMEOUT:
                pass
            except pexpect.EOF:
                break
        assert not child.isalive(), "':q' did not quit the onboarding prompt"
    finally:
        child.close(force=True)


def _rows_with_reverse(screen):
    """Count screen rows that contain at least one reverse-video (selected) cell."""
    return sum(
        1
        for y in range(screen.lines)
        if any(screen.buffer[y][x].reverse for x in range(screen.columns))
    )


def _drag_multi(child, r1, c1, r2, c2):
    """Left press at (r1,c1), drag to (r2,c2), release — spans rows for a multi-line select."""
    child.send(f"\x1b[<0;{c1 + 1};{r1 + 1}M")  # left press
    child.send(f"\x1b[<32;{c2 + 1};{r2 + 1}M")  # left-drag (motion)
    child.send(f"\x1b[<0;{c2 + 1};{r2 + 1}m")  # left release


def _scroll_keys_top(child, *, pageup_presses: int = 0) -> None:
    """Send real terminal key sequences for scroll-to-top.

    Ctrl+Home is the fast path; optional repeated PgUp exercises the
    incremental scroll_up(10) binding too.
    """
    child.send("\x1b[1;5H")  # Ctrl+Home (xterm modifyOtherKeys)
    for _ in range(pageup_presses):
        child.send("\x1b[5~")  # PgUp


def _scroll_keys_bottom(child, *, pagedown_presses: int = 12) -> None:
    """PgDn toward the bottom of the scrollback."""
    for _ in range(pagedown_presses):
        child.send("\x1b[6~")  # PgDn


def _wait_dead(child, secs=8):
    """Drain output until the child exits or the timeout elapses; return True if it exited."""
    end = time.monotonic() + secs
    while time.monotonic() < end and child.isalive():
        try:
            child.read_nonblocking(1 << 16, 0.2)
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            break
    return not child.isalive()


@needs_cli
def test_command_mode_q_quits(tmp_path):
    """With a key set (command mode, not onboarding), :q quits the REPL."""
    child, screen, stream = _spawn(tmp_path)
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no prompt"
        child.send(":q\r")
        assert _wait_dead(child), "':q' did not quit command mode"
    finally:
        child.close(force=True)


@needs_cli
def test_ctrl_d_quits_on_empty_line(tmp_path):
    """Ctrl+D (EOF) on an empty prompt exits the REPL."""
    child, screen, stream = _spawn(tmp_path)
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no prompt"
        child.send("\x04")  # Ctrl+D
        assert _wait_dead(child), "Ctrl+D did not exit the REPL"
    finally:
        child.close(force=True)


@needs_cli
def test_multiline_drag_highlights_multiple_rows(tmp_path):
    """Default mode: a drag spanning two rows highlights more than one row."""
    child, screen, stream = _spawn(tmp_path)
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no prompt"
        child.send(":help\r")
        assert _pump_until(child, screen, stream, lambda s: "Complete" in _text(s)), "no help"
        target, line = _content_row(screen)
        c1 = len(line) - len(line.lstrip())
        _drag_multi(child, target, c1, target + 1, 20)
        assert _pump_until(child, screen, stream, lambda s: _rows_with_reverse(s) >= 2), (
            "multi-row drag did not highlight 2+ rows"
        )
    finally:
        child.close(force=True)


@needs_cli
def test_ctrl_l_repaints_without_clearing(tmp_path):
    """Ctrl+L forces a full repaint: scrollback content and prompt survive."""
    child, screen, stream = _spawn(tmp_path)
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no prompt"
        child.send(":help\r")
        assert _pump_until(child, screen, stream, lambda s: "Complete" in _text(s)), "no help"
        child.send("\x0c")  # Ctrl+L
        _pump(child, screen, stream, 1.0)
        assert child.isalive(), "Ctrl+L killed the REPL"
        t = _text(screen)
        assert "Complete" in t, "repaint lost scrollback content"
        assert "❯" in t, "repaint lost the prompt"
    finally:
        child.close(force=True)


@needs_cli
def test_focus_reports_do_not_leak_into_input(tmp_path):
    """The REPL enables mode 1004; ESC[I / ESC[O focus reports must be consumed
    (focus-in triggers a repaint), never inserted as literal text."""
    import io

    child, screen, stream = _spawn(tmp_path)
    child.logfile_read = io.StringIO()  # raw output capture
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no prompt"
        assert "\x1b[?1004h" in child.logfile_read.getvalue(), "focus reporting not enabled"
        child.send("\x1b[O")  # focus lost
        child.send("\x1b[I")  # focus gained → full repaint
        child.send("hello")
        assert _pump_until(child, screen, stream, lambda s: "hello" in _text(s)), "typed text lost"
        t = _text(screen)
        assert "[I" not in t and "[O" not in t, "focus report leaked into the UI"
        assert child.isalive()
    finally:
        child.close(force=True)


@needs_cli
def test_scroll_up_reaches_content_above_wrapped_line(tmp_path):
    """End-to-end scroll: real key events reach lines above a long wrapped row.

      Mirrors the google-preview bug shape — a few short logical lines, one
      ~4000-character line that wraps to dozens of visual rows, then a footer.
      At the default bottom position the top marker is off-screen; Ctrl+Home
    and PgUp must scroll back to it. Would fail when scroll_up capped in
      logical lines instead of visual rows.
    """
    # Match the user's repro window (92×30); narrow width maximises wrap depth.
    child, screen, stream = _spawn(tmp_path, cols=92, rows=30, exec_enabled=True)
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no prompt"

        shell_cmd = (
            f"!python3 -c \"print('{_SCROLL_TOP}'); print('W'*4000); print('{_SCROLL_BOTTOM}')\""
        )
        child.send(shell_cmd + "\r")
        assert _pump_until(
            child,
            screen,
            stream,
            lambda s: _marker_in_scrollback(s, _SCROLL_BOTTOM) and "pollinating" not in _text(s),
            timeout=20,
        ), "shell output did not finish"
        assert not _marker_in_scrollback(screen, _SCROLL_TOP), (
            "top marker visible in scrollback before scrolling"
        )

        # Ctrl+Home → scroll_to_top binding.
        _scroll_keys_top(child)
        assert _pump_until(
            child,
            screen,
            stream,
            lambda s: _marker_in_scrollback(s, _SCROLL_TOP),
            timeout=5,
        ), "Ctrl+Home did not reach content above the wrapped line"

        # PgDn back toward the footer.
        _scroll_keys_bottom(child)
        assert _pump_until(
            child,
            screen,
            stream,
            lambda s: _marker_in_scrollback(s, _SCROLL_BOTTOM),
            timeout=5,
        ), "PgDn did not scroll back toward the bottom"

        # Incremental PgUp from the bottom (no Ctrl+Home) must also reach the top.
        for _ in range(30):
            child.send("\x1b[5~")
        assert _pump_until(
            child,
            screen,
            stream,
            lambda s: _marker_in_scrollback(s, _SCROLL_TOP),
            timeout=5,
        ), "repeated PgUp did not reach content above the wrapped line"
    finally:
        child.close(force=True)


@needs_cli
def test_classic_mouse_shift_tab_toggles_mode(tmp_path):
    """--no-drag-copy: Shift+Tab (no popup open) toggles the toolbar Scroll <-> Select label."""
    child, screen, stream = _spawn(tmp_path, args=["--no-drag-copy"])
    try:
        assert _pump_until(child, screen, stream, lambda s: "Scroll mode" in _text(s)), "no chip"
        child.send("\x1b[Z")  # Shift+Tab (CSI Z / back-tab)
        assert _pump_until(child, screen, stream, lambda s: "Select mode" in _text(s)), (
            "Shift+Tab did not switch to Select mode"
        )
        child.send("\x1b[Z")  # toggle back
        assert _pump_until(child, screen, stream, lambda s: "Scroll mode" in _text(s)), (
            "Shift+Tab did not switch back to Scroll mode"
        )
    finally:
        child.close(force=True)


def _has_session_default_skip_warning(screen, command: str, setting: str) -> bool:
    t = _text(screen)
    return (
        "not applied to" in t
        and command in t
        and setting in t
        and "unsupported by this command" in t
    )


def _pump_until_transient(child, screen, stream, predicate, timeout=15.0, step=256):
    """Like ``_pump_until`` but also catches short-lived screen states.

    ``_pump_until`` feeds each PTY read (up to 64 KiB) to pyte in one go and
    only then checks the predicate, so text that appears and scrolls off (or
    is repainted over) within a single read is never observed. Feeding the
    data in small slices and checking after each slice makes transient
    states — like a warning printed just before command output streams in —
    reliably detectable.
    """
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            data = child.read_nonblocking(1 << 16, 0.2)
        except pexpect.TIMEOUT:
            continue
        except pexpect.EOF:
            break
        for i in range(0, len(data), step):
            stream.feed(data[i : i + step])
            if predicate(screen):
                return True
    return predicate(screen)


@needs_cli
def test_session_default_skip_warning_on_screen(tmp_path):
    """Scrape-only session defaults warn on screen when a command ignores them."""
    # Tall grid: the warning is appended to scrollback before the command
    # output, so on a short screen later lines (help text, footer, background
    # usage-refresh output on CI) can push it out of the visible window.
    child, screen, stream = _spawn(tmp_path, rows=64)
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no prompt"
        child.send(":set premium-proxy=true\r")
        assert _pump_until(
            child,
            screen,
            stream,
            lambda s: "premium-proxy" in _text(s) and "true" in _text(s),
        ), ":set did not apply premium-proxy=true"
        # ``usage --help`` keeps the output short; the transient pump checks
        # every intermediate screen state, not just the post-read one.
        child.send("usage --help\r")
        assert _pump_until_transient(
            child,
            screen,
            stream,
            lambda s: _has_session_default_skip_warning(s, "usage", "premium-proxy"),
            timeout=20.0,
        ), f"skip warning for premium-proxy on usage not shown; screen:\n{_text(screen)}"
    finally:
        child.close(force=True)


@needs_cli
def test_session_default_no_skip_warning_for_supported_command(tmp_path):
    """Session defaults supported by the target command must not emit a skip warning."""
    child, screen, stream = _spawn(tmp_path)
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no prompt"
        child.send(":set premium-proxy=true\r")
        assert _pump_until(
            child,
            screen,
            stream,
            lambda s: "premium-proxy" in _text(s) and "true" in _text(s),
        ), ":set did not apply premium-proxy=true"
        child.send("scrape --help\r")
        assert _pump_until(
            child,
            screen,
            stream,
            lambda s: "✓" in _text(s) and "--output-file" in _text(s),
            timeout=20.0,
        ), "scrape --help did not complete"
        assert not _has_session_default_skip_warning(screen, "scrape", "premium-proxy"), (
            "skip warning shown for premium-proxy on scrape"
        )
    finally:
        child.close(force=True)


@needs_cli
def test_repl_tilde_output_file_validated_before_scrape(tmp_path):
    """REPL expands ~/ output paths and rejects overwrites before any scrape work."""
    home = tmp_path / "home"
    home.mkdir()
    out_dir = home / "Desktop" / "sb-cli-test" / "ss"
    out_dir.mkdir(parents=True)
    (out_dir / "screenshot.png").write_bytes(b"old")

    child, screen, stream = _spawn(home)
    try:
        assert _pump_until(child, screen, stream, lambda s: "❯" in _text(s)), "no prompt"
        child.send(
            "scrape https://example.com --render-js false "
            "--output-file ~/Desktop/sb-cli-test/ss/screenshot.png\r"
        )
        assert _pump_until(
            child,
            screen,
            stream,
            lambda s: "already exists" in _text(s) and "--overwrite" in _text(s),
            timeout=10.0,
        ), "overwrite error not shown before scrape"
        t = _text(screen)
        assert "Cannot write to '~/" not in t
    finally:
        child.close(force=True)
