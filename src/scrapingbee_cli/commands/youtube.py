"""YouTube search and metadata commands."""

from __future__ import annotations

import asyncio
import re

import click
from click_option_group import optgroup

from ..batch import (
    _find_completed_n,
    get_batch_usage,
    read_input_file,
    resolve_batch_concurrency,
    run_api_batch,
    validate_batch_run,
)
from ..cli_utils import check_api_response, norm_val, parse_bool, write_output
from ..client import Client
from ..config import BASE_URL, get_api_key

YOUTUBE_UPLOAD_DATE = ["today", "last-hour", "this-week", "this-month", "this-year"]

_YT_URL_PATTERN = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})"
)


def _extract_video_id(value: str) -> str:
    """Return the bare video ID from a YouTube URL or pass through an already-bare ID."""
    m = _YT_URL_PATTERN.search(value)
    return m.group(1) if m else value


def _normalize_youtube_search(data: bytes) -> bytes:
    """Normalize youtube-search response into a clean, pipeable format.

    The API returns ``results`` as a JSON-encoded string whose items use internal
    YouTube API field names (``videoId``, nested title/channel objects, etc.).
    This function rebuilds ``results`` as a proper JSON array with flat fields:
    ``link``, ``video_id``, ``title``, ``channel``, ``views``, ``published``, ``duration``.
    ``link`` is a full ``https://www.youtube.com/watch?v=…`` URL, making
    ``--extract-field results.link`` work directly for piping into youtube-metadata.
    """
    import json as _json

    try:
        d = _json.loads(data)
    except (ValueError, TypeError):
        return data
    raw = d.get("results")
    if not isinstance(raw, str):
        return data
    try:
        items = _json.loads(raw)
    except (ValueError, TypeError):
        return data
    if not isinstance(items, list):
        return data

    clean = []
    for item in items:
        if not isinstance(item, dict):
            continue
        video_id = item.get("videoId")
        if not video_id:
            continue
        # title
        t_obj = item.get("title") or {}
        runs = t_obj.get("runs", []) if isinstance(t_obj, dict) else []
        title = runs[0].get("text", "") if runs else ""
        # channel
        c_obj = item.get("longBylineText") or item.get("ownerText") or {}
        runs = c_obj.get("runs", []) if isinstance(c_obj, dict) else []
        channel = runs[0].get("text", "") if runs else ""
        # views / published / duration
        vc = item.get("viewCountText") or {}
        views = vc.get("simpleText", "") if isinstance(vc, dict) else ""
        pb = item.get("publishedTimeText") or {}
        published = pb.get("simpleText", "") if isinstance(pb, dict) else ""
        dur = item.get("lengthText") or {}
        duration = dur.get("simpleText", "") if isinstance(dur, dict) else ""

        clean.append(
            {
                "link": f"https://www.youtube.com/watch?v={video_id}",
                "video_id": video_id,
                "title": title,
                "channel": channel,
                "views": views,
                "published": published,
                "duration": duration,
            }
        )

    d["results"] = clean
    return _json.dumps(d, ensure_ascii=False).encode()


YOUTUBE_TYPE = ["video", "channel", "playlist", "movie"]
YOUTUBE_DURATION = ["short", "medium", "long", "<4", "4-20", ">20"]
_DURATION_ALIAS = {"short": "<4", "medium": "4-20", "long": ">20"}
YOUTUBE_SORT_BY = ["relevance", "rating", "view-count", "upload-date"]


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
    type=click.Choice(YOUTUBE_DURATION, case_sensitive=False),
    default=None,
    help="Duration: short (<4 min), medium (4-20 min), long (>20 min).",
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
    duration = _DURATION_ALIAS.get(duration.lower(), duration) if duration else duration
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
        try:
            inputs = read_input_file(input_file)
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        usage_info = get_batch_usage(None)
        try:
            validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        skip_n = (
            _find_completed_n(obj.get("output_dir") or "") if obj.get("resume") else frozenset()
        )

        async def api_call(client, q):
            data, headers, status_code = await client.youtube_search(
                q,
                upload_date=norm_val(upload_date),
                type=type_,
                duration=duration,
                sort_by=norm_val(sort_by),
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
            return _normalize_youtube_search(data), headers, status_code

        run_api_batch(
            key=key,
            inputs=inputs,
            concurrency=concurrency,
            from_user=obj["concurrency"] > 0,
            skip_n=skip_n,
            output_dir=obj.get("output_dir") or None,
            verbose=obj["verbose"],
            show_progress=obj.get("progress", True),
            api_call=api_call,
            diff_dir=obj.get("diff_dir"),
        )
        return

    if not query:
        click.echo("expected one search query, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.youtube_search(
                query,
                upload_date=norm_val(upload_date),
                type=type_,
                duration=duration,
                sort_by=norm_val(sort_by),
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
        data = _normalize_youtube_search(data)
        write_output(
            data,
            headers,
            status_code,
            obj["output_file"],
            obj["verbose"],
            extract_field=obj.get("extract_field"),
            fields=obj.get("fields"),
            command="youtube-search",
        )

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
        try:
            inputs = read_input_file(input_file)
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        usage_info = get_batch_usage(None)
        try:
            validate_batch_run(obj["concurrency"], len(inputs), usage_info)
        except ValueError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        concurrency = resolve_batch_concurrency(obj["concurrency"], usage_info, len(inputs))

        skip_n = (
            _find_completed_n(obj.get("output_dir") or "") if obj.get("resume") else frozenset()
        )

        async def api_call(client, vid):
            return await client.youtube_metadata(
                _extract_video_id(vid),
                retries=obj.get("retries", 3) or 3,
                backoff=obj.get("backoff", 2.0) or 2.0,
            )

        run_api_batch(
            key=key,
            inputs=inputs,
            concurrency=concurrency,
            from_user=obj["concurrency"] > 0,
            skip_n=skip_n,
            output_dir=obj.get("output_dir") or None,
            verbose=obj["verbose"],
            show_progress=obj.get("progress", True),
            api_call=api_call,
            diff_dir=obj.get("diff_dir"),
        )
        return

    if not video_id:
        click.echo("expected one video ID, or use global --input-file for batch", err=True)
        raise SystemExit(1)

    async def _single() -> None:
        async with Client(key, BASE_URL) as client:
            data, headers, status_code = await client.youtube_metadata(
                _extract_video_id(video_id),
                retries=obj.get("retries", 3) or 3,
                backoff=obj.get("backoff", 2.0) or 2.0,
            )
        check_api_response(data, status_code)
        write_output(
            data,
            headers,
            status_code,
            obj["output_file"],
            obj["verbose"],
            extract_field=obj.get("extract_field"),
            fields=obj.get("fields"),
            command="youtube-metadata",
        )

    asyncio.run(_single())


def register(cli: click.Group) -> None:
    cli.add_command(youtube_search_cmd, "youtube-search")
    cli.add_command(youtube_metadata_cmd, "youtube-metadata")
