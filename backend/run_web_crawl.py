#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys

from server import crawl_web_feed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Stop The Slop web crawl.")
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        default=[],
        help="Override the default crawl queries. Pass multiple times for multiple queries.",
    )
    parser.add_argument(
        "--max-results-per-query",
        type=int,
        default=None,
        help="Maximum number of web search results to fetch per query.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Maximum total number of curated web posts to store in this run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = crawl_web_feed(
        queries=args.queries or None,
        max_results_per_query=args.max_results_per_query,
        max_items=args.max_items,
    )
    payload = {
        "queryCount": summary.get("queryCount", 0),
        "discoveredCount": summary.get("discoveredCount", 0),
        "storedCount": summary.get("storedCount", 0),
        "itemIds": [item.get("id") for item in summary.get("items", [])],
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
