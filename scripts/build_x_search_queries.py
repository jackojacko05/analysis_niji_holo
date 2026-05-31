#!/usr/bin/env python3
"""Build X API OR-search query batches from the current fan-art tag CSV."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
from urllib.parse import quote


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "current"
TODAY = date.today().isoformat()

DEFAULT_SUFFIX = "-is:retweet has:images"


def query_tag_from_norm(tag_norm: str) -> str:
    return f"#{tag_norm.lstrip('#＃')}"


def load_unique_tags(path: Path) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["tag_kind"] != "fanart":
                continue
            key = (row["org"], row["tag_norm"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "org": row["org"],
                    "tag": query_tag_from_norm(row["tag_norm"]),
                    "original_tag": row["tag"],
                    "tag_norm": row["tag_norm"],
                    "name": row["name"],
                    "talent_id": row["talent_id"],
                }
            )
    return sorted(rows, key=lambda r: (r["org"], r["tag_norm"], r["tag"]))


def build_query(tags: list[str], suffix: str) -> str:
    body = " OR ".join(tags)
    return f"({body}) {suffix}".strip()


def pack_queries(rows: list[dict[str, str]], *, max_length: int, suffix: str) -> list[dict[str, str]]:
    batches: list[dict[str, str]] = []
    current: list[dict[str, str]] = []

    def flush() -> None:
        if not current:
            return
        tags = [row["tag"] for row in current]
        tag_norms = [row["tag_norm"] for row in current]
        query = build_query(tags, suffix)
        batches.append(
            {
                "org": current[0]["org"],
                "query": query,
                "query_length": str(len(query)),
                "url_encoded_length": str(len(quote(query, safe=""))),
                "tag_count": str(len(tags)),
                "tags": "|".join(tags),
                "original_tags": "|".join(row["original_tag"] for row in current),
                "tag_norms": "|".join(tag_norms),
            }
        )

    for row in rows:
        candidate = current + [row]
        query = build_query([item["tag"] for item in candidate], suffix)
        if current and len(query) > max_length:
            flush()
            current = [row]
            continue
        if len(query) > max_length:
            raise ValueError(f"Single tag query exceeds max length: {row['tag']} -> {query}")
        current = candidate

    flush()
    return batches


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=DATA_DIR / f"fanart_tags_current_{TODAY}.csv",
        help="Current fan-art tag CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / f"x_search_queries_recent_{TODAY}.csv",
        help="Output CSV for recent-search query batches.",
    )
    parser.add_argument("--max-length", type=int, default=500, help="Max decoded X query length. X recent search allows 512; default keeps a small margin.")
    parser.add_argument("--suffix", default=DEFAULT_SUFFIX, help="Query suffix appended to every OR batch.")
    args = parser.parse_args()

    rows = load_unique_tags(args.input)
    batches: list[dict[str, str]] = []
    for org in sorted({row["org"] for row in rows}):
        org_rows = [row for row in rows if row["org"] == org]
        for index, batch in enumerate(pack_queries(org_rows, max_length=args.max_length, suffix=args.suffix), start=1):
            batch["dataset_date"] = TODAY
            batch["endpoint"] = "/2/tweets/search/recent"
            batch["query_kind"] = "fanart_or_has_images_non_retweet"
            batch["batch_id"] = f"{org}-{index:03d}"
            batch["max_results"] = "100"
            batch["notes"] = "Decoded query length is kept under the X recent-search 512-character cap; no API requests are made by this script."
            batches.append(batch)

    fieldnames = [
        "dataset_date",
        "endpoint",
        "query_kind",
        "org",
        "batch_id",
        "query",
        "query_length",
        "url_encoded_length",
        "tag_count",
        "max_results",
        "tags",
        "original_tags",
        "tag_norms",
        "notes",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(batches)

    print(f"input_tags: {len(rows)}")
    print(f"query_batches: {len(batches)}")
    print(f"max_query_length: {max(int(row['query_length']) for row in batches)}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
