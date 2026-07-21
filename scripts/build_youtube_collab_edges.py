#!/usr/bin/env python3
"""Aggregate YouTube description collaboration candidates into graph edges."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "current"
TODAY = date.today().isoformat()

EDGE_FIELDS = [
    "dataset_date",
    "owner_talent_id",
    "owner_name",
    "owner_org",
    "collaborator_talent_id",
    "collaborator_name",
    "collaborator_org",
    "same_org",
    "owner_video_count",
    "video_count",
    "video_share",
    "likely_boilerplate",
    "evidence_count",
    "evidence_types",
    "first_published_at",
    "last_published_at",
    "sample_video_id",
    "sample_video_url",
    "sample_title",
]


def latest_path(pattern: str) -> Path:
    paths = sorted(DATA_DIR.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not paths:
        raise FileNotFoundError(f"No {pattern} under {DATA_DIR}")
    return paths[-1]


def source_suffix(path: Path, prefix: str) -> str:
    stem = path.stem
    if stem.startswith(prefix):
        return stem[len(prefix) :]
    return TODAY


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EDGE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def split_pipe(value: str) -> list[str]:
    return [part for part in value.split("|") if part]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", type=Path, default=latest_path("youtube_channels_current_*.csv"))
    parser.add_argument("--videos", type=Path, default=latest_path("youtube_videos_*.csv"))
    parser.add_argument("--collabs", type=Path, default=latest_path("youtube_video_collaborators_*.csv"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--filtered-output",
        type=Path,
        default=None,
    )
    parser.add_argument("--boilerplate-min-videos", type=int, default=20)
    parser.add_argument("--boilerplate-share", type=float, default=0.40)
    args = parser.parse_args()
    suffix = source_suffix(args.collabs, "youtube_video_collaborators_")
    output = args.output or DATA_DIR / f"youtube_collab_edges_{suffix}.csv"
    filtered_output = args.filtered_output or DATA_DIR / f"youtube_collab_edges_filtered_{suffix}.csv"

    channels = read_csv(args.channels)
    videos = read_csv(args.videos)
    collabs = read_csv(args.collabs)
    talents = {
        row["talent_id"]: {
            "name": row["name"],
            "org": row["org"],
        }
        for row in channels
        if row.get("talent_id")
    }
    owner_video_ids: dict[str, set[str]] = defaultdict(set)
    for row in videos:
        for owner_id in split_pipe(row["owner_talent_ids"]):
            owner_video_ids[owner_id].add(row["video_id"])

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for row in collabs:
        collaborator_id = row["collaborator_talent_id"]
        for owner_id in split_pipe(row["owner_talent_ids"]):
            if owner_id == collaborator_id:
                continue
            key = (owner_id, collaborator_id)
            edge = grouped.setdefault(
                key,
                {
                    "videos": set(),
                    "evidence_count": 0,
                    "evidence_types": set(),
                    "published_at": [],
                    "sample": row,
                },
            )
            edge["videos"].add(row["video_id"])  # type: ignore[index]
            edge["evidence_count"] = int(edge["evidence_count"]) + 1
            edge["evidence_types"].add(row["evidence_type"])  # type: ignore[index]
            if row["published_at"]:
                edge["published_at"].append(row["published_at"])  # type: ignore[index]

    rows: list[dict[str, str]] = []
    for (owner_id, collaborator_id), edge in grouped.items():
        owner = talents.get(owner_id, {"name": "", "org": ""})
        collaborator = talents.get(collaborator_id, {"name": "", "org": ""})
        published = sorted(edge["published_at"])  # type: ignore[arg-type]
        sample = edge["sample"]  # type: ignore[assignment]
        owner_video_count = len(owner_video_ids.get(owner_id, set()))
        video_count = len(edge["videos"])  # type: ignore[arg-type]
        video_share = video_count / owner_video_count if owner_video_count else 0.0
        likely_boilerplate = (
            video_count >= args.boilerplate_min_videos
            and video_share >= args.boilerplate_share
        )
        rows.append(
            {
                "dataset_date": TODAY,
                "owner_talent_id": owner_id,
                "owner_name": owner["name"],
                "owner_org": owner["org"],
                "collaborator_talent_id": collaborator_id,
                "collaborator_name": collaborator["name"],
                "collaborator_org": collaborator["org"],
                "same_org": "true" if owner["org"] == collaborator["org"] else "false",
                "owner_video_count": str(owner_video_count),
                "video_count": str(video_count),
                "video_share": f"{video_share:.4f}",
                "likely_boilerplate": "true" if likely_boilerplate else "false",
                "evidence_count": str(edge["evidence_count"]),
                "evidence_types": "|".join(sorted(edge["evidence_types"])),  # type: ignore[arg-type]
                "first_published_at": published[0] if published else "",
                "last_published_at": published[-1] if published else "",
                "sample_video_id": sample["video_id"],
                "sample_video_url": sample["video_url"],
                "sample_title": sample["title"],
            }
        )

    rows.sort(
        key=lambda row: (
            -int(row["video_count"]),
            row["owner_org"],
            row["owner_name"],
            row["collaborator_org"],
            row["collaborator_name"],
        )
    )
    write_csv(output, rows)
    filtered_rows = [row for row in rows if row["likely_boilerplate"] != "true"]
    write_csv(filtered_output, filtered_rows)
    print(f"input collab rows: {len(collabs)}")
    print(f"directed edges: {len(rows)}")
    print(f"filtered directed edges: {len(filtered_rows)}")
    print(f"output: {output}")
    print(f"filtered_output: {filtered_output}")


if __name__ == "__main__":
    main()
