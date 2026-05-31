#!/usr/bin/env python3
"""Fetch YouTube videos for current NIJISANJI/hololive talents.

The script resolves channel IDs from the current roster, fetches each channel's
uploads playlist, then downloads video metadata. It supports both latest-N and
date-range fetches. It also emits a rough collaboration candidate table by
matching known YouTube channel IDs and @handles in video descriptions.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "current"
BUILD_DIR = BASE_DIR / "build" / "youtube-current-cache"
TODAY = date.today().isoformat()
USER_AGENT = "analysis-niji-holo/0.1 (+https://github.com/jackojacko05/analysis_niji_holo)"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


VIDEO_FIELDS = [
    "dataset_date",
    "fetched_at",
    "video_id",
    "video_url",
    "channel_id",
    "channel_title",
    "owner_talent_ids",
    "owner_names",
    "owner_orgs",
    "published_at",
    "title",
    "description",
    "live_broadcast_content",
    "duration",
    "view_count",
    "like_count",
    "comment_count",
    "description_urls",
    "matched_known_handles",
    "matched_known_channel_ids",
]

CHANNEL_FIELDS = [
    "dataset_date",
    "fetched_at",
    "org",
    "agency",
    "affiliation",
    "talent_id",
    "name",
    "en_name",
    "slug",
    "active_status",
    "profile_url",
    "source_youtube_url",
    "channel_id",
    "channel_title",
    "channel_custom_url",
    "uploads_playlist_id",
    "subscriber_count",
    "video_count",
    "view_count",
    "resolved_method",
    "resolved_source",
    "resolution_notes",
]

COLLAB_FIELDS = [
    "dataset_date",
    "video_id",
    "video_url",
    "published_at",
    "title",
    "owner_channel_id",
    "owner_talent_ids",
    "owner_names",
    "collaborator_channel_id",
    "collaborator_talent_id",
    "collaborator_name",
    "collaborator_org",
    "evidence_type",
    "evidence",
]


@dataclass
class ApiStats:
    requests: int = 0
    cache_hits: int = 0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def compact_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def safe_cache_name(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "__") or "index"
    return f"{parsed.netloc}__{path}.html"


def fetch_text(url: str, cache_path: Path, *, force: bool = False, sleep_s: float = 0.0) -> str:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists() and not force:
        return cache_path.read_text(encoding="utf-8", errors="replace")
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as res:
        body = res.read().decode("utf-8", errors="replace")
    cache_path.write_text(body, encoding="utf-8")
    if sleep_s:
        time.sleep(sleep_s)
    return body


def parse_next_data(page_html: str) -> dict:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        page_html,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Could not find __NEXT_DATA__ script")
    return json.loads(html.unescape(match.group(1)))


def parse_nijisanji_channel_detail(page_html: str) -> tuple[str, str, str]:
    data = parse_next_data(page_html)
    detail = data.get("props", {}).get("pageProps", {}).get("liverDetail", {})
    socials = detail.get("socialLinks") or {}
    return (
        detail.get("channelId") or "",
        detail.get("channelName") or "",
        socials.get("youtube") or "",
    )


def extract_channel_id_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] == "channel" and path_parts[1].startswith("UC"):
        return path_parts[1]
    if parsed.netloc in {"youtu.be", "www.youtu.be"}:
        return ""
    return ""


def extract_handle_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    for part in path_parts:
        if part.startswith("@") and len(part) > 1:
            return normalize_handle(part)
    return ""


def normalize_handle(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("@"):
        value = value[1:]
    return value.rstrip("/").casefold()


def cache_key(endpoint: str, params: dict[str, str]) -> str:
    clean = "&".join(f"{key}={params[key]}" for key in sorted(params))
    digest = hashlib.sha256(f"{endpoint}?{clean}".encode("utf-8")).hexdigest()[:24]
    return f"{endpoint}-{digest}.json"


def youtube_request(
    endpoint: str,
    params: dict[str, str],
    *,
    api_key: str,
    cache_dir: Path,
    stats: ApiStats,
    force: bool = False,
    sleep_s: float = 0.0,
) -> dict:
    cache_path = cache_dir / cache_key(endpoint, params)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists() and not force:
        stats.cache_hits += 1
        return json.loads(cache_path.read_text(encoding="utf-8"))

    request_params = dict(params)
    request_params["key"] = api_key
    url = f"{YOUTUBE_API_BASE}/{endpoint}?{urlencode(request_params)}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=45) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"YouTube API error for {endpoint}: HTTP {exc.code}: {body[:1000]}") from exc
    except URLError as exc:
        raise RuntimeError(f"YouTube API network error for {endpoint}: {exc}") from exc

    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    stats.requests += 1
    if sleep_s:
        time.sleep(sleep_s)
    return payload


def chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def channel_url(channel_id: str) -> str:
    return f"https://www.youtube.com/channel/{channel_id}" if channel_id else ""


def video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def parse_rfc3339(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError:
        return None


def resolve_date_bounds(
    start_date: str,
    end_date: str,
    timezone_name: str,
) -> tuple[datetime | None, datetime | None, str]:
    tz = ZoneInfo(timezone_name)
    start_dt_utc: datetime | None = None
    end_dt_utc: datetime | None = None

    if start_date:
        start_local = datetime.combine(date.fromisoformat(start_date), datetime_time.min, tzinfo=tz)
        start_dt_utc = start_local.astimezone(timezone.utc)
    if end_date:
        # Inclusive date from the user's local perspective.
        end_local = datetime.combine(date.fromisoformat(end_date) + timedelta(days=1), datetime_time.min, tzinfo=tz)
        end_dt_utc = end_local.astimezone(timezone.utc)

    if start_dt_utc and end_dt_utc and start_dt_utc >= end_dt_utc:
        raise ValueError("--start-date must be earlier than or equal to --end-date")

    if start_date and end_date:
        label = f"{start_date}_to_{end_date}"
    elif start_date:
        label = f"{start_date}_to_latest"
    elif end_date:
        label = f"until_{end_date}"
    else:
        label = ""
    return start_dt_utc, end_dt_utc, label


def in_published_range(
    published_at: datetime | None,
    *,
    start_dt_utc: datetime | None,
    end_dt_utc: datetime | None,
) -> bool:
    if not published_at:
        return True
    if start_dt_utc and published_at < start_dt_utc:
        return False
    if end_dt_utc and published_at >= end_dt_utc:
        return False
    return True


def resolve_known_channels(
    talents: list[dict[str, str]],
    *,
    api_key: str,
    cache_dir: Path,
    stats: ApiStats,
    force_api: bool,
    fetch_niji_details: bool,
    force_web: bool,
    sleep_s: float,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for talent in talents:
        row = {
            "dataset_date": TODAY,
            "fetched_at": "",
            "org": talent["org"],
            "agency": talent["agency"],
            "affiliation": talent["affiliation"],
            "talent_id": talent["talent_id"],
            "name": talent["name"],
            "en_name": talent["en_name"],
            "slug": talent["slug"],
            "active_status": talent["active_status"],
            "profile_url": talent["profile_url"],
            "source_youtube_url": talent.get("youtube_url", ""),
            "channel_id": extract_channel_id_from_url(talent.get("youtube_url", "")),
            "channel_title": "",
            "channel_custom_url": "",
            "uploads_playlist_id": "",
            "subscriber_count": "",
            "video_count": "",
            "view_count": "",
            "resolved_method": "youtube_url_channel_id" if extract_channel_id_from_url(talent.get("youtube_url", "")) else "",
            "resolved_source": talent.get("youtube_url", ""),
            "resolution_notes": "",
        }

        if talent["org"] == "nijisanji" and fetch_niji_details:
            try:
                page_html = fetch_text(
                    talent["profile_url"],
                    BUILD_DIR / "nijisanji-detail" / safe_cache_name(talent["profile_url"]),
                    force=force_web,
                    sleep_s=sleep_s,
                )
                detail_channel_id, detail_channel_name, detail_youtube_url = parse_nijisanji_channel_detail(page_html)
                if detail_youtube_url and not row["source_youtube_url"]:
                    row["source_youtube_url"] = detail_youtube_url
                if detail_channel_id:
                    row["channel_id"] = detail_channel_id
                    row["channel_title"] = detail_channel_name
                    row["resolved_method"] = "nijisanji_official_detail_channel_id"
                    row["resolved_source"] = talent["profile_url"]
            except Exception as exc:  # keep the run going; emit missing row later
                row["resolution_notes"] = f"niji_detail_error: {exc}"

        handle = extract_handle_from_url(row["source_youtube_url"])
        if not row["channel_id"] and handle:
            payload = youtube_request(
                "channels",
                {
                    "part": "id,snippet,contentDetails,statistics",
                    "forHandle": f"@{handle}",
                    "maxResults": "1",
                },
                api_key=api_key,
                cache_dir=cache_dir,
                stats=stats,
                force=force_api,
                sleep_s=sleep_s,
            )
            items = payload.get("items", [])
            if items:
                item = items[0]
                row["channel_id"] = item.get("id", "")
                row["channel_title"] = item.get("snippet", {}).get("title", "")
                row["channel_custom_url"] = item.get("snippet", {}).get("customUrl", "")
                row["uploads_playlist_id"] = (
                    item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "")
                )
                stats_block = item.get("statistics", {})
                row["subscriber_count"] = stats_block.get("subscriberCount", "")
                row["video_count"] = stats_block.get("videoCount", "")
                row["view_count"] = stats_block.get("viewCount", "")
                row["resolved_method"] = "youtube_api_forHandle"
                row["resolved_source"] = f"@{handle}"
            else:
                row["resolution_notes"] = compact_space(f"{row['resolution_notes']} handle_not_found @{handle}")

        rows.append(row)

    enrich_channel_metadata(rows, api_key=api_key, cache_dir=cache_dir, stats=stats, force_api=force_api, sleep_s=sleep_s)
    return rows


def enrich_channel_metadata(
    rows: list[dict[str, str]],
    *,
    api_key: str,
    cache_dir: Path,
    stats: ApiStats,
    force_api: bool,
    sleep_s: float,
) -> None:
    channel_ids = sorted({row["channel_id"] for row in rows if row["channel_id"]})
    by_id: dict[str, dict] = {}
    for chunk in chunks(channel_ids, 50):
        payload = youtube_request(
            "channels",
            {
                "part": "snippet,contentDetails,statistics",
                "id": ",".join(chunk),
                "maxResults": "50",
            },
            api_key=api_key,
            cache_dir=cache_dir,
            stats=stats,
            force=force_api,
            sleep_s=sleep_s,
        )
        for item in payload.get("items", []):
            by_id[item.get("id", "")] = item

    fetched_at = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row["fetched_at"] = fetched_at
        item = by_id.get(row["channel_id"])
        if not item:
            if row["channel_id"]:
                row["resolution_notes"] = compact_space(f"{row['resolution_notes']} channel_metadata_not_found")
            continue
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        stats_block = item.get("statistics", {})
        row["channel_title"] = row["channel_title"] or snippet.get("title", "")
        row["channel_custom_url"] = row["channel_custom_url"] or snippet.get("customUrl", "")
        row["uploads_playlist_id"] = row["uploads_playlist_id"] or content.get("relatedPlaylists", {}).get("uploads", "")
        row["subscriber_count"] = row["subscriber_count"] or stats_block.get("subscriberCount", "")
        row["video_count"] = row["video_count"] or stats_block.get("videoCount", "")
        row["view_count"] = row["view_count"] or stats_block.get("viewCount", "")


def fetch_upload_video_ids(
    upload_playlist_id: str,
    *,
    max_videos: int,
    start_dt_utc: datetime | None,
    end_dt_utc: datetime | None,
    api_key: str,
    cache_dir: Path,
    stats: ApiStats,
    force_api: bool,
    sleep_s: float,
) -> list[str]:
    video_ids: list[str] = []
    seen_video_ids: set[str] = set()
    page_token = ""
    while max_videos <= 0 or len(video_ids) < max_videos:
        date_filtering = start_dt_utc is not None or end_dt_utc is not None
        page_size = 50 if date_filtering else min(50, max_videos - len(video_ids))
        params = {
            "part": "snippet,contentDetails",
            "playlistId": upload_playlist_id,
            "maxResults": str(page_size),
        }
        if page_token:
            params["pageToken"] = page_token
        payload = youtube_request(
            "playlistItems",
            params,
            api_key=api_key,
            cache_dir=cache_dir,
            stats=stats,
            force=force_api,
            sleep_s=sleep_s,
        )
        reached_before_start = False
        for item in payload.get("items", []):
            content = item.get("contentDetails", {})
            snippet = item.get("snippet", {})
            video_id = content.get("videoId") or snippet.get("resourceId", {}).get("videoId", "")
            published_at = parse_rfc3339(content.get("videoPublishedAt", "") or snippet.get("publishedAt", ""))
            if start_dt_utc and published_at and published_at < start_dt_utc:
                reached_before_start = True
                continue
            if not in_published_range(published_at, start_dt_utc=start_dt_utc, end_dt_utc=end_dt_utc):
                continue
            if video_id and video_id not in seen_video_ids:
                video_ids.append(video_id)
                seen_video_ids.add(video_id)
                if max_videos > 0 and len(video_ids) >= max_videos:
                    break
        if reached_before_start:
            break
        page_token = payload.get("nextPageToken", "")
        if not page_token or not payload.get("items"):
            break
    return video_ids[:max_videos] if max_videos > 0 else video_ids


def fetch_video_details(
    video_ids: list[str],
    *,
    api_key: str,
    cache_dir: Path,
    stats: ApiStats,
    force_api: bool,
    sleep_s: float,
) -> list[dict]:
    videos: list[dict] = []
    for chunk in chunks(video_ids, 50):
        payload = youtube_request(
            "videos",
            {
                "part": "snippet,contentDetails,statistics,liveStreamingDetails",
                "id": ",".join(chunk),
                "maxResults": "50",
            },
            api_key=api_key,
            cache_dir=cache_dir,
            stats=stats,
            force=force_api,
            sleep_s=sleep_s,
        )
        videos.extend(payload.get("items", []))
    return videos


def extract_description_urls(description: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"https?://[^\s<>()\[\]{}\"']+", description or ""):
        url = match.group(0).rstrip(".,;:。)、）]")
        if url not in urls:
            urls.append(url)
    return urls


def extract_known_channel_ids(description: str, known_channel_ids: set[str]) -> set[str]:
    found: set[str] = set()
    for channel_id in re.findall(r"UC[0-9A-Za-z_-]{20,}", description or ""):
        if channel_id in known_channel_ids:
            found.add(channel_id)
    return found


def extract_known_handles(description: str, known_handles: set[str]) -> set[str]:
    found: set[str] = set()
    for handle in re.findall(r"(?<![\w.])@([0-9A-Za-z][0-9A-Za-z._-]{2,})", description or ""):
        normalized = normalize_handle(handle)
        if normalized in known_handles:
            found.add(normalized)
    return found


def build_known_indexes(channel_rows: list[dict[str, str]]) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]]]:
    by_channel: dict[str, list[dict[str, str]]] = {}
    by_handle: dict[str, list[dict[str, str]]] = {}
    for row in channel_rows:
        if row["channel_id"]:
            by_channel.setdefault(row["channel_id"], []).append(row)
        for handle in [extract_handle_from_url(row["source_youtube_url"]), normalize_handle(row["channel_custom_url"])]:
            if handle:
                by_handle.setdefault(handle, []).append(row)
    return by_channel, by_handle


def make_owner_fields(owner_rows: list[dict[str, str]]) -> tuple[str, str, str]:
    talent_ids = []
    names = []
    orgs = []
    for row in owner_rows:
        if row["talent_id"] not in talent_ids:
            talent_ids.append(row["talent_id"])
        if row["name"] not in names:
            names.append(row["name"])
        if row["org"] not in orgs:
            orgs.append(row["org"])
    return "|".join(talent_ids), "|".join(names), "|".join(orgs)


def build_video_and_collab_rows(
    videos: list[dict],
    owner_rows_by_channel: dict[str, list[dict[str, str]]],
    channel_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    by_channel, by_handle = build_known_indexes(channel_rows)
    known_channel_ids = set(by_channel)
    known_handles = set(by_handle)
    fetched_at = datetime.now(timezone.utc).isoformat()
    video_rows: list[dict[str, str]] = []
    collab_rows: list[dict[str, str]] = []

    for item in videos:
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        stats_block = item.get("statistics", {})
        video_id = item.get("id", "")
        channel_id = snippet.get("channelId", "")
        description = snippet.get("description", "") or ""
        owner_rows = owner_rows_by_channel.get(channel_id, [])
        owner_talent_ids, owner_names, owner_orgs = make_owner_fields(owner_rows)
        urls = extract_description_urls(description)
        matched_channel_ids = extract_known_channel_ids(description, known_channel_ids)
        matched_handles = extract_known_handles(description, known_handles)
        owner_talent_set = {row["talent_id"] for row in owner_rows}

        video_rows.append(
            {
                "dataset_date": TODAY,
                "fetched_at": fetched_at,
                "video_id": video_id,
                "video_url": video_url(video_id),
                "channel_id": channel_id,
                "channel_title": snippet.get("channelTitle", ""),
                "owner_talent_ids": owner_talent_ids,
                "owner_names": owner_names,
                "owner_orgs": owner_orgs,
                "published_at": snippet.get("publishedAt", ""),
                "title": snippet.get("title", ""),
                "description": description,
                "live_broadcast_content": snippet.get("liveBroadcastContent", ""),
                "duration": content.get("duration", ""),
                "view_count": stats_block.get("viewCount", ""),
                "like_count": stats_block.get("likeCount", ""),
                "comment_count": stats_block.get("commentCount", ""),
                "description_urls": "|".join(urls),
                "matched_known_handles": "|".join(sorted(matched_handles)),
                "matched_known_channel_ids": "|".join(sorted(matched_channel_ids)),
            }
        )

        seen_collabs: set[tuple[str, str, str]] = set()
        for matched_channel_id in sorted(matched_channel_ids):
            for collaborator in by_channel.get(matched_channel_id, []):
                if collaborator["talent_id"] in owner_talent_set:
                    continue
                key = (video_id, collaborator["talent_id"], "channel_id")
                if key in seen_collabs:
                    continue
                seen_collabs.add(key)
                collab_rows.append(make_collab_row(item, owner_talent_ids, owner_names, collaborator, "description_channel_id", matched_channel_id))

        for matched_handle in sorted(matched_handles):
            for collaborator in by_handle.get(matched_handle, []):
                if collaborator["talent_id"] in owner_talent_set:
                    continue
                key = (video_id, collaborator["talent_id"], "handle")
                if key in seen_collabs:
                    continue
                seen_collabs.add(key)
                collab_rows.append(make_collab_row(item, owner_talent_ids, owner_names, collaborator, "description_handle", f"@{matched_handle}"))

    return video_rows, collab_rows


def make_collab_row(
    item: dict,
    owner_talent_ids: str,
    owner_names: str,
    collaborator: dict[str, str],
    evidence_type: str,
    evidence: str,
) -> dict[str, str]:
    snippet = item.get("snippet", {})
    video_id = item.get("id", "")
    return {
        "dataset_date": TODAY,
        "video_id": video_id,
        "video_url": video_url(video_id),
        "published_at": snippet.get("publishedAt", ""),
        "title": snippet.get("title", ""),
        "owner_channel_id": snippet.get("channelId", ""),
        "owner_talent_ids": owner_talent_ids,
        "owner_names": owner_names,
        "collaborator_channel_id": collaborator["channel_id"],
        "collaborator_talent_id": collaborator["talent_id"],
        "collaborator_name": collaborator["name"],
        "collaborator_org": collaborator["org"],
        "evidence_type": evidence_type,
        "evidence": evidence,
    }


def latest_talents_path() -> Path:
    paths = sorted(DATA_DIR.glob("talents_current_*.csv"))
    if not paths:
        raise FileNotFoundError("No data/current/talents_current_*.csv found. Run build_current_fanart_dataset.py first.")
    return paths[-1]


def write_summary(
    path: Path,
    *,
    talents: list[dict[str, str]],
    channel_rows: list[dict[str, str]],
    video_rows: list[dict[str, str]],
    collab_rows: list[dict[str, str]],
    stats: ApiStats,
    max_videos: int,
    start_date: str,
    end_date: str,
    timezone_name: str,
) -> None:
    resolved = [row for row in channel_rows if row["channel_id"]]
    missing = [row for row in channel_rows if not row["channel_id"]]
    unique_channels = sorted({row["channel_id"] for row in resolved})
    lines = [
        f"# YouTube Videos Fetch ({TODAY})",
        "",
        "## Scope",
        "",
        f"- talents considered: {len(talents)}",
        f"- resolved talent-channel rows: {len(resolved)}",
        f"- unresolved talent-channel rows: {len(missing)}",
        f"- unique channels fetched: {len(unique_channels)}",
        f"- date range: {start_date or 'unbounded'} to {end_date or 'unbounded'} ({timezone_name})",
        f"- target latest videos per channel: {max_videos if max_videos > 0 else 'unbounded by count'}",
        f"- video rows: {len(video_rows)}",
        f"- inferred description collaboration rows: {len(collab_rows)}",
        "",
        "## YouTube API Usage",
        "",
        f"- network requests made by this run: {stats.requests}",
        f"- cache hits: {stats.cache_hits}",
        "- each `channels.list`, `playlistItems.list`, and `videos.list` request costs 1 quota unit.",
        "",
        "## Collaboration Heuristic",
        "",
        "- Matches only known current NIJISANJI/hololive YouTube channel IDs and @handles in video descriptions.",
        "- Edges are evidence candidates, not final collaboration truth; descriptions often include guests, music credits, or management channels.",
        "- Shared channels, such as grouped official channels, are kept as pipe-separated owners.",
    ]
    if missing:
        lines.extend(["", "## Unresolved Channels", ""])
        for row in missing[:100]:
            note = f" ({row['resolution_notes']})" if row["resolution_notes"] else ""
            lines.append(f"- {row['org']} {row['name']} / {row['en_name']}{note}")
        if len(missing) > 100:
            lines.append(f"- ... {len(missing) - 100} more")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--talents", type=Path, default=latest_talents_path(), help="Current talent CSV.")
    parser.add_argument("--api-key-env", default="YOUTUBE_API_KEY", help="Environment variable holding a YouTube Data API key.")
    parser.add_argument(
        "--max-videos",
        type=int,
        default=None,
        help="Latest videos to fetch per unique channel. Defaults to 200 without --start-date, and unlimited with --start-date.",
    )
    parser.add_argument("--start-date", default="", help="Inclusive local date lower bound, e.g. 2025-06-01.")
    parser.add_argument("--end-date", default="", help="Inclusive local date upper bound. Defaults to today when --start-date is set.")
    parser.add_argument("--date-timezone", default="Asia/Tokyo", help="Timezone used for date bounds.")
    parser.add_argument("--limit-channels", type=int, default=0, help="Debug limit for unique channels after resolution.")
    parser.add_argument("--fetch-niji-details", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force-web", action="store_true", help="Refresh official profile HTML cache.")
    parser.add_argument("--force-api", action="store_true", help="Refresh YouTube API cache.")
    parser.add_argument("--sleep", type=float, default=0.03, help="Delay between remote requests.")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        print(f"Missing {args.api_key_env}.", file=sys.stderr)
        raise SystemExit(2)

    if args.start_date and not args.end_date:
        args.end_date = TODAY
    start_dt_utc, end_dt_utc, date_label = resolve_date_bounds(args.start_date, args.end_date, args.date_timezone)
    max_videos = args.max_videos if args.max_videos is not None else (0 if args.start_date else 200)
    if max_videos <= 0 and not (start_dt_utc or end_dt_utc):
        raise SystemExit("--max-videos <= 0 requires --start-date or --end-date to avoid fetching an unbounded history.")

    talents = read_csv(args.talents)
    stats = ApiStats()
    api_cache_dir = BUILD_DIR / "youtube-api"
    channel_rows = resolve_known_channels(
        talents,
        api_key=api_key,
        cache_dir=api_cache_dir,
        stats=stats,
        force_api=args.force_api,
        fetch_niji_details=args.fetch_niji_details,
        force_web=args.force_web,
        sleep_s=args.sleep,
    )

    resolved_channel_rows = [row for row in channel_rows if row["channel_id"] and row["uploads_playlist_id"]]
    unique_by_channel: dict[str, dict[str, str]] = {}
    for row in resolved_channel_rows:
        unique_by_channel.setdefault(row["channel_id"], row)
    unique_channels = list(unique_by_channel.values())
    if args.limit_channels:
        unique_channels = unique_channels[: args.limit_channels]

    owner_rows_by_channel: dict[str, list[dict[str, str]]] = {}
    for row in resolved_channel_rows:
        owner_rows_by_channel.setdefault(row["channel_id"], []).append(row)

    all_video_ids: list[str] = []
    for index, channel in enumerate(unique_channels, start=1):
        print(f"[{index}/{len(unique_channels)}] playlistItems {channel['channel_id']} {channel['channel_title']}", file=sys.stderr)
        video_ids = fetch_upload_video_ids(
            channel["uploads_playlist_id"],
            max_videos=max_videos,
            start_dt_utc=start_dt_utc,
            end_dt_utc=end_dt_utc,
            api_key=api_key,
            cache_dir=api_cache_dir,
            stats=stats,
            force_api=args.force_api,
            sleep_s=args.sleep,
        )
        for video_id in video_ids:
            if video_id not in all_video_ids:
                all_video_ids.append(video_id)

    videos: list[dict] = []
    for index, chunk in enumerate(list(chunks(all_video_ids, 50)), start=1):
        print(f"[videos {index}] details for {len(chunk)} ids", file=sys.stderr)
        videos.extend(
            fetch_video_details(
                chunk,
                api_key=api_key,
                cache_dir=api_cache_dir,
                stats=stats,
                force_api=args.force_api,
                sleep_s=args.sleep,
            )
        )

    if start_dt_utc or end_dt_utc:
        videos = [
            item
            for item in videos
            if in_published_range(
                parse_rfc3339(item.get("snippet", {}).get("publishedAt", "")),
                start_dt_utc=start_dt_utc,
                end_dt_utc=end_dt_utc,
            )
        ]

    video_rows, collab_rows = build_video_and_collab_rows(videos, owner_rows_by_channel, channel_rows)

    source_label = date_label or f"latest{max_videos}"
    suffix = f"{source_label}_{TODAY}"
    if args.limit_channels:
        suffix = f"{suffix}_sample{args.limit_channels}"
    write_csv(DATA_DIR / f"youtube_channels_current_{suffix}.csv", channel_rows, CHANNEL_FIELDS)
    write_csv(DATA_DIR / f"youtube_videos_{suffix}.csv", video_rows, VIDEO_FIELDS)
    write_csv(DATA_DIR / f"youtube_video_collaborators_{suffix}.csv", collab_rows, COLLAB_FIELDS)
    write_summary(
        DATA_DIR / f"youtube_fetch_summary_{suffix}.md",
        talents=talents,
        channel_rows=channel_rows,
        video_rows=video_rows,
        collab_rows=collab_rows,
        stats=stats,
        max_videos=max_videos,
        start_date=args.start_date,
        end_date=args.end_date,
        timezone_name=args.date_timezone,
    )

    print(f"talents: {len(talents)}")
    print(f"resolved channel rows: {sum(1 for row in channel_rows if row['channel_id'])}")
    print(f"unique channels fetched: {len(unique_channels)}")
    print(f"videos: {len(video_rows)}")
    print(f"collaboration candidate rows: {len(collab_rows)}")
    print(f"youtube api network requests: {stats.requests}")
    print(f"youtube api cache hits: {stats.cache_hits}")
    print(f"output_dir: {DATA_DIR}")


if __name__ == "__main__":
    main()
