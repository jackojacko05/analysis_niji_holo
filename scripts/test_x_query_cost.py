#!/usr/bin/env python3
"""Run one X API query batch and estimate pay-per-use cost.

This script never prints the bearer token. Set X_BEARER_TOKEN or pass
--bearer-token-env with another environment variable name.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "current"
BUILD_DIR = BASE_DIR / "build" / "x-api-test"
TODAY = date.today().isoformat()

POST_READ_USD = 0.005
COUNTS_RECENT_REQUEST_USD = 0.005


def load_batch(path: Path, batch_id: str) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"No query rows in {path}")
    if batch_id:
        for row in rows:
            if row["batch_id"] == batch_id:
                return row
        raise ValueError(f"batch_id not found: {batch_id}")
    return rows[0]


def request_json(url: str, token: str) -> tuple[dict, dict[str, str]]:
    req = Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "analysis-niji-holo/0.1"})
    with urlopen(req, timeout=30) as res:
        headers = dict(res.headers.items())
        return json.loads(res.read().decode("utf-8")), headers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queries",
        type=Path,
        default=DATA_DIR / f"x_search_queries_recent_{TODAY}.csv",
        help="OR query batch CSV.",
    )
    parser.add_argument("--batch-id", default="", help="Batch id to test. Defaults to the first row.")
    parser.add_argument("--mode", choices=["counts", "search"], default="counts")
    parser.add_argument("--max-results", type=int, default=10, help="Only used for --mode search. X recent search allows 10-100.")
    parser.add_argument("--bearer-token-env", default="X_BEARER_TOKEN")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    batch = load_batch(args.queries, args.batch_id)
    query = batch["query"]
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    if args.mode == "counts":
        params = urlencode({"query": query, "granularity": "day"})
        url = f"https://api.x.com/2/tweets/counts/recent?{params}"
    else:
        params = urlencode(
            {
                "query": query,
                "max_results": max(10, min(args.max_results, 100)),
                "tweet.fields": "created_at,entities,public_metrics,lang",
            }
        )
        url = f"https://api.x.com/2/tweets/search/recent?{params}"

    token = os.environ.get(args.bearer_token_env, "")
    print(f"batch_id: {batch['batch_id']}")
    print(f"org: {batch['org']}")
    print(f"tag_count: {batch['tag_count']}")
    print(f"query_length: {batch['query_length']}")
    print(f"mode: {args.mode}")

    if args.dry_run:
        print(f"request_url: {url}")
        if args.mode == "counts":
            print(f"estimated_request_cost_usd: {COUNTS_RECENT_REQUEST_USD:.3f}")
        else:
            max_cost = max(10, min(args.max_results, 100)) * POST_READ_USD
            print(f"estimated_max_cost_usd: {max_cost:.3f}")
        return

    if not token:
        raise SystemExit(f"Missing bearer token env var: {args.bearer_token_env}")

    data, headers = request_json(url, token)
    output_path = BUILD_DIR / f"{batch['batch_id']}_{args.mode}_{TODAY}.json"
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.mode == "counts":
        total = data.get("meta", {}).get("total_tweet_count", 0)
        print(f"total_tweet_count: {total}")
        print(f"actual_request_cost_usd: {COUNTS_RECENT_REQUEST_USD:.3f}")
        print(f"estimated_full_read_cost_usd: {total * POST_READ_USD:.3f}")
    else:
        returned = len(data.get("data", []))
        print(f"returned_posts: {returned}")
        print(f"actual_read_cost_usd: {returned * POST_READ_USD:.3f}")

    for header in ["x-rate-limit-limit", "x-rate-limit-remaining", "x-rate-limit-reset"]:
        if header in headers:
            print(f"{header}: {headers[header]}")
    print(f"response_json: {output_path}")


if __name__ == "__main__":
    main()
