"""YouTube search and metadata commands."""

from __future__ import annotations

import asyncio

import click
from click_option_group import optgroup

from ..batch import (
    get_batch_usage,
    read_input_file,
    resolve_batch_concurrency,
    run_batch_async,
    validate_batch_run,
    write_batch_output_to_dir,
)
from ..client import Client
from ..config import BASE_URL, get_api_key
from ..cli_utils import check_api_response, parse_bool, write_output

YOUTUBE_UPLOAD_DATE = ["today", "last_hour", "this_week", "this_month", "this_year"]
YOUTUBE_TYPE = ["video", "channel", "playlist", "movie"]
YOUTUBE_SORT_BY = ["relevance", "rating", "view_count", "upload_date"]


@click.command("youtube-search")
@click.argument("query", required=False)
@optgroup.group("Filters", help="Upload date, type, duration, sort")
@optgroup.option(
    "--upload-date",
    type=click.Choice(YOUTUBE_UPLOAD_DATE, case_sensitive=False),
    default=None,
    help="Filter by upload date.",
)
@optgroup.option(
    "--type",
    "type_",
    type=click.Choice(YOUTUBE_TYPE, case_sensitive=False),
    default=None,
    help="Result type.",
)
@optgroup.option(
    "--duration",
    type=str,
    default=None,
    help="Duration: under 4 min, 4-20 min, over 20 min.",
)
@optgroup.option(
    "--sort-by",
    type=click.Choice(YOUTUBE_SORT_BY, case_sensitive=False),
    default=None,
    help="Sort order.",
)
@optgroup.group("Quality & features", help="HD, 4K, subtitles, live, etc.")
@optgroup.option("--hd", type=str, default=None, help="HD only (true/false).")
@optgroup.option("--4k", "is_4k", type=str, default=None, help="4K only (true/false).")
@optgroup.option("--subtitles", type=str, default=None, help="With subtitles (true/false).")
@optgroup.option(
    "--creative-commons", type=str, default=None, help="Creative Commons only (true/false)."
)
@optgroup.option("--live", type=str, default=None, help="Live streams only (true/false).")
@optgroup.option("--360", "is_360", type=str, default=None, help="360° videos only (true/false).")
@optgroup.option("--3d", "is_3d", type=str, default=None, help="3D videos only (true/false).")
@optgroup.option("--hdr", type=str, default=None, help="HDR videos only (true/false).")
@optgroup.option("--location", type=str, default=None, help="With location (true/false).")
@optgroup.option("--vr180", type=str, default=None, help="VR180 only (true/false).")
@click.pass_obj
def youtube_search_cmd(
    obj: dict,
    query: str | None,
    upload_date: str | None,
    type_: str | None,
    duration: str | None,
    sort_by: str | None,
    hd: str | None,
    is_4k: str | None,
    subtitles: str | None,
    creative_commons: str | None,
    live: str | None,
    is_360: str | None,
    is_3d: str | None,
    hdr: str | None,
    location: str | None,
    vr180: str | None,
) -> None:
    """Search YouTube videos."""
    input_file = obj.get("input_file")
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if query:
            click.echo("cannot use both global --input-file and positional query", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(None)
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(q: str):
                    try:
                        data, headers, status_code = await client.youtube_search(
                            q,
                            upload_date=upload_date,
                            type=type_,
                            duration=duration,
                            sort_by=sort_by,
                            hd=parse_bool(hd),
                            is_4k=parse_bool(is_4k),
                            subtitles=parse_bool(subtitles),
                            creative_commons=parse_bool(creative_commons),
                            live=parse_bool(live),
                            is_360=parse_bool(is_360),
                            is_3d=parse_bool(is_3d),
                            hdr=parse_bool(hdr),
                            location=parse_bool(location),
                            vr180=parse_bool(vr180),
                            retries=obj.get("retries", 3) or 3,
                            backoff=obj.get("backoff", 2.0) or 2.0,
                        )
                        if status_code >= 400:
                            err = RuntimeError(f"HTTP {status_code}")
                            return data, headers, status_code, err, "json"
                        return data, headers, status_code, None, "json"
                    except Exception as e:
                        return b"", {}, 0, e, "json"

                results = await run_batch_async(
                    inputs, concurrency, do_one, from_user=obj["concurrency"] > 0
                )
            out_dir = write_batch_output_to_dir(
                results, obj.get("output_dir") or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not query:
        click.echo("expected one search query, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.youtube_search(
                query,
                upload_date=upload_date,
                type=type_,
                duration=duration,
                sort_by=sort_by,
                hd=parse_bool(hd),
                is_4k=parse_bool(is_4k),
                subtitles=parse_bool(subtitles),
                creative_commons=parse_bool(creative_commons),
                live=parse_bool(live),
                is_360=parse_bool(is_360),
                is_3d=parse_bool(is_3d),
                hdr=parse_bool(hdr),
                location=parse_bool(location),
                vr180=parse_bool(vr180),
                retries=obj.get("retries", 3) or 3,
                backoff=obj.get("backoff", 2.0) or 2.0,
            )
        check_api_response(data, status_code)
        write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


@click.command("youtube-metadata")
@click.argument("video_id", required=False)
@click.pass_obj
def youtube_metadata_cmd(
    obj: dict,
    video_id: str | None,
) -> None:
    """Fetch YouTube video metadata."""
    input_file = obj.get("input_file")
    try:
        key = get_api_key(None)
    except ValueError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1)

    if input_file:
        if video_id:
            click.echo("cannot use both global --input-file and positional video-id", err=True)
            raise SystemExit(1)
        inputs = read_input_file(input_file)
        usage_info = get_batch_usage(None)
        validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        async def _batch() -> None:
            async with Client(key, BASE_URL, connector_limit=concurrency) as client:

                async def do_one(vid: str):
                    try:
                        data, headers, status_code = await client.youtube_metadata(
                            vid,
                            retries=obj.get("retries", 3) or 3,
                            backoff=obj.get("backoff", 2.0) or 2.0,
                        )
                        if status_code >= 400:
                            err = RuntimeError(f"HTTP {status_code}")
                            return data, headers, status_code, err, "json"
                        return data, headers, status_code, None, "json"
                    except Exception as e:
                        return b"", {}, 0, e, "json"

                results = await run_batch_async(
                    inputs, concurrency, do_one, from_user=obj["concurrency"] > 0
                )
            out_dir = write_batch_output_to_dir(
                results, obj.get("output_dir") or None, obj["verbose"]
            )
            click.echo(f"Batch complete. Output written to {out_dir}")

        asyncio.run(_batch())
        return

    if not video_id:
        click.echo("expected one video ID, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.youtube_metadata(
                video_id,
                retries=obj.get("retries", 3) or 3,
                backoff=obj.get("backoff", 2.0) or 2.0,
            )
        check_api_response(data, status_code)
        write_output(data, headers, status_code, obj["output_file"], obj["verbose"])

    asyncio.run(_single())


def register(cli):  # noqa: ANN001
    cli.add_command(youtube_search_cmd, "youtube-search")
    cli.add_command(youtube_metadata_cmd, "youtube-metadata")
