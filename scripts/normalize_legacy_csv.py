#!/usr/bin/env python3
"""Normalize the legacy wide CSV files into BigQuery-friendly CSVs."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import unicodedata


BASE_DIR = Path(__file__).resolve().parents[1]
KNOWN_NAME_FIXES = {
    "音乃瀬奏)": "音乃瀬奏",
}


def normalize_tag(tag: str) -> str:
    tag = tag.strip()
    if tag.startswith("#") or tag.startswith("＃"):
        tag = tag[1:]
    return unicodedata.normalize("NFKC", tag).lower()


def normalize_name(name: str) -> str:
    fixed = KNOWN_NAME_FIXES.get(name.strip(), name.strip())
    return unicodedata.normalize("NFKC", fixed)


def character_id(org: str, name: str) -> str:
    return f"{org}:{normalize_name(name)}"


def read_character_tags(repo_dir: Path) -> list[dict[str, str]]:
    specs = [
        ("nijisanji", repo_dir / "tag_niji.csv"),
        ("hololive", repo_dir / "tag_holo.csv"),
    ]
    rows: list[dict[str, str]] = []
    now = datetime.now(timezone.utc).isoformat()

    for org, path in specs:
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = normalize_name(row["name"])
                tag = row["tag"].strip()
                rows.append(
                    {
                        "org": org,
                        "character_id": character_id(org, name),
                        "character_name": name,
                        "fanart_tag": tag,
                        "fanart_tag_norm": normalize_tag(tag),
                        "twitter_handle": row.get("Twitter", "").strip(),
                        "active": "true",
                        "source_file": path.name,
                        "updated_at": now,
                    }
                )
    return rows


def read_legacy_posts(repo_dir: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    specs = [
        ("nijisanji", repo_dir / "tweets_tagged_niji.csv"),
        ("hololive", repo_dir / "tweets_tagged_holo.csv"),
    ]
    posts: list[dict[str, str]] = []
    post_characters: list[dict[str, str]] = []
    now = datetime.now(timezone.utc).isoformat()

    for org, path in specs:
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                continue
            character_columns = [
                field
                for field in reader.fieldnames
                if field not in {"", "user_id", "created_at", "text"}
            ]

            for row in reader:
                legacy_index = row.get("", "")
                post_id = f"legacy:{org}:{legacy_index}"
                posts.append(
                    {
                        "post_id": post_id,
                        "author_id": row.get("user_id", ""),
                        "created_at": row.get("created_at", ""),
                        "text": row.get("text", ""),
                        "source_file": path.name,
                        "fetched_at": now,
                    }
                )

                for name in character_columns:
                    if row.get(name, "").lower() != "true":
                        continue
                    clean_name = normalize_name(name)
                    post_characters.append(
                        {
                            "post_id": post_id,
                            "author_id": row.get("user_id", ""),
                            "created_at": row.get("created_at", ""),
                            "org": org,
                            "character_id": character_id(org, clean_name),
                            "character_name": clean_name,
                            "evidence_tag_norm": "",
                            "evidence_source": "legacy_wide_boolean",
                            "confidence": "1.0",
                            "fetched_at": now,
                        }
                    )
    return posts, post_characters


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-dir", type=Path, default=BASE_DIR)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=BASE_DIR / "build" / "legacy-normalized",
    )
    args = parser.parse_args()

    character_tags = read_character_tags(args.repo_dir)
    legacy_posts, post_characters = read_legacy_posts(args.repo_dir)

    write_csv(
        args.out_dir / "character_tags.csv",
        character_tags,
        [
            "org",
            "character_id",
            "character_name",
            "fanart_tag",
            "fanart_tag_norm",
            "twitter_handle",
            "active",
            "source_file",
            "updated_at",
        ],
    )
    write_csv(
        args.out_dir / "legacy_posts.csv",
        legacy_posts,
        ["post_id", "author_id", "created_at", "text", "source_file", "fetched_at"],
    )
    write_csv(
        args.out_dir / "post_characters.csv",
        post_characters,
        [
            "post_id",
            "author_id",
            "created_at",
            "org",
            "character_id",
            "character_name",
            "evidence_tag_norm",
            "evidence_source",
            "confidence",
            "fetched_at",
        ],
    )

    print(f"character_tags: {len(character_tags)}")
    print(f"legacy_posts: {len(legacy_posts)}")
    print(f"post_characters: {len(post_characters)}")
    print(f"out_dir: {args.out_dir}")


if __name__ == "__main__":
    main()

