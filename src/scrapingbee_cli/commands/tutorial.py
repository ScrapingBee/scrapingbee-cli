"""Tutorial command — interactive step-by-step CLI walkthrough."""

from __future__ import annotations

from pathlib import Path

import click

from ..config import load_dotenv
from ..tutorial.runner import TutorialRunner, TutorialState, find_binary, prepare_tutorial_files
from ..tutorial.steps import STEPS, get_chapter_list


@click.command()
@click.option(
    "--chapter",
    type=int,
    default=None,
    help="Jump to a specific chapter number (skips earlier chapters).",
)
@click.option(
    "--reset",
    is_flag=True,
    default=False,
    help="Clear saved progress and start the tutorial from the beginning.",
)
@click.option(
    "--list",
    "list_chapters",
    is_flag=True,
    default=False,
    help="List all chapters and steps without running anything.",
)
@click.option(
    "--output-dir",
    "output_dir",
    default="./tutorial-out",
    show_default=True,
    help="Directory where tutorial output files are saved.",
)
def tutorial_cmd(
    chapter: int | None,
    reset: bool,
    list_chapters: bool,
    output_dir: str,
) -> None:
    """Interactive step-by-step tutorial using books.toscrape.com.

    Walks through every command and key option with live examples.
    Progress is saved automatically so you can quit and resume later.

    \b
    Examples:
      scrapingbee tutorial                  # start or resume
      scrapingbee tutorial --chapter 6      # jump to Crawling
      scrapingbee tutorial --list           # show all chapters
      scrapingbee tutorial --reset          # start fresh
    """
    if list_chapters:
        _show_chapter_list()
        return

    # Load any saved .env so the key is in os.environ for all subprocesses.
    load_dotenv()

    binary = find_binary()

    if reset:
        TutorialState.clear()
        click.echo("  Progress cleared.")

    # Resolve state: resume saved session or start fresh.
    saved = None if reset else TutorialState.load()

    if saved and saved.output_dir and chapter is None and not reset:
        last = saved.completed[-1] if saved.completed else "none"
        click.echo()
        try:
            resume = click.confirm(f"  Resume tutorial? (last completed: {last})", default=True)
        except click.Abort:
            return
        if not resume:
            TutorialState.clear()
            saved = None

    if saved is None:
        out_path = Path(output_dir).resolve()  # absolute — resume works from any cwd
        state = TutorialState(output_dir=str(out_path))
    else:
        state = saved
        out_path = Path(state.output_dir)

    out_path.mkdir(parents=True, exist_ok=True)
    prepare_tutorial_files(out_path)

    start_i = 0
    if chapter is not None:
        # Find where the target chapter starts in the full list.
        start_i = next((idx for idx, s in enumerate(STEPS) if s.chapter >= chapter), len(STEPS))
        if start_i >= len(STEPS):
            click.echo(f"  No steps found starting at chapter {chapter}.")
            return
        # Clear completed/skipped for target-chapter steps so they re-run.
        target_ids = {s.id for s in STEPS if s.chapter >= chapter}
        state.completed = [sid for sid in state.completed if sid not in target_ids]
        state.skipped = [sid for sid in state.skipped if sid not in target_ids]
        # Mark pre-chapter steps as skipped so they auto-skip forward but are
        # reachable via Back navigation.
        pre_ids = {s.id for s in STEPS if s.chapter < chapter}
        for sid in pre_ids:
            if sid not in state.completed and sid not in state.skipped:
                state.skipped.append(sid)

    runner = TutorialRunner(binary=binary, state=state)
    runner.run(STEPS, start_i=start_i)


def _show_chapter_list() -> None:
    click.echo()
    for chap_num, chap_name, chap_steps in get_chapter_list():
        click.echo(
            click.style(f"  Chapter {chap_num}", bold=True)
            + click.style(f": {chap_name}", fg="bright_white")
            + click.style(
                f"  ({len(chap_steps)} step{'s' if len(chap_steps) != 1 else ''})",
                fg="bright_black",
            )
        )
        for step in chap_steps:
            click.echo(click.style(f"    {step.id}", fg="cyan") + f"  {step.title}")
    click.echo()


def register(cli: click.Group) -> None:
    cli.add_command(tutorial_cmd, "tutorial")
