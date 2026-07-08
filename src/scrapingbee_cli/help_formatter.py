"""Custom Rich-powered help formatter for ScrapingBee CLI."""

from __future__ import annotations

import sys
from typing import Any

import click

from .theme import BEE_AMBER, BEE_YELLOW, err_console


def _should_style() -> bool:
    """True when stderr is a real TTY (styled help goes to stderr)."""
    return sys.stderr.isatty()


class BeeHelpFormatter(click.HelpFormatter):
    """Click help formatter that outputs styled text via Rich."""

    def write(self, string: str) -> None:
        """Collect raw text — we'll style it in getvalue()."""
        super().write(string)


class BeeCommand(click.Command):
    """Command subclass that renders help through Rich."""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Override to render help with Rich styling."""
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_epilog(ctx, formatter)

    def get_help(self, ctx: click.Context) -> str:
        """Return plain help AND print styled version to stderr if TTY."""
        formatter = ctx.make_formatter()
        self.format_help(ctx, formatter)
        plain = formatter.getvalue()
        if _should_style():
            _print_styled_help(plain, self.name or "")
        return plain


class BeeGroup(click.Group):
    """Group subclass that renders help through Rich."""

    def get_help(self, ctx: click.Context) -> str:
        formatter = ctx.make_formatter()
        self.format_help(ctx, formatter)
        plain = formatter.getvalue()
        if _should_style():
            _print_styled_help(plain, self.name or "scrapingbee")
        return plain

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_commands(ctx, formatter)
        self.format_epilog(ctx, formatter)

    def command(self, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("cls", BeeCommand)
        return super().command(*args, **kwargs)

    def group(self, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("cls", BeeGroup)
        return super().group(*args, **kwargs)


def _print_styled_help(plain_help: str, command_name: str) -> None:
    """Parse plain Click help text and render it with Rich styling."""
    from rich.text import Text

    lines = plain_help.split("\n")

    # Header
    err_console.print()
    header = Text()
    header.append(f"  {command_name}", style=f"bold {BEE_YELLOW}")
    err_console.print(header)
    err_console.print()

    in_commands = False

    for line in lines:
        stripped = line.strip()

        # Skip the "Usage:" line (we already printed header)
        if stripped.startswith("Usage:"):
            # Print usage in dim
            err_console.print(f"  [dim]{stripped}[/dim]")
            continue

        # Section headers
        if stripped.endswith(":") and not stripped.startswith("-") and not stripped.startswith("["):
            in_commands = stripped == "Commands:"
            err_console.print(
                f"  [bold {BEE_YELLOW}]~~ {stripped[:-1]} ~~{'~' * (36 - len(stripped))}[/]"
            )
            continue

        # Option group headers (from click-option-group)
        if stripped.endswith(":") and len(stripped) < 40 and not stripped.startswith("-"):
            err_console.print(
                f"  [bold {BEE_YELLOW}]~~ {stripped[:-1]} ~~{'~' * (36 - len(stripped))}[/]"
            )
            continue

        # Empty lines
        if not stripped:
            err_console.print()
            continue

        # Description text (not indented or lightly indented, not starting with -)
        if not line.startswith("  ") or (
            line.startswith("  ") and not line.startswith("    ") and not stripped.startswith("-")
        ):
            if stripped and not stripped.startswith("-"):
                err_console.print(f"  [dim]{stripped}[/dim]")
                continue

        # Options: --flag  Description
        if stripped.startswith("-") or stripped.startswith("["):
            # Split on double space to separate flag from description
            parts = stripped.split("  ", 1)
            if len(parts) == 2:
                flag, desc = parts[0].strip(), parts[1].strip()
                text = Text()
                text.append(f"    {flag:<30}", style=f"bold {BEE_AMBER}")
                text.append(f" {desc}", style="dim")
                err_console.print(text)
            else:
                err_console.print(f"    [{BEE_AMBER}]{stripped}[/]")
            continue

        # Commands list
        if in_commands and stripped:
            parts = stripped.split("  ", 1)
            if len(parts) == 2:
                cmd, desc = parts[0].strip(), parts[1].strip()
                text = Text()
                text.append(f"    {cmd:<20}", style=f"bold {BEE_YELLOW}")
                text.append(f" {desc}", style="dim")
                err_console.print(text)
            else:
                err_console.print(f"    [{BEE_YELLOW}]{stripped}[/]")
            continue

        # Indented description continuation
        if stripped:
            err_console.print(f"    [dim]{stripped}[/dim]")

    err_console.print()
