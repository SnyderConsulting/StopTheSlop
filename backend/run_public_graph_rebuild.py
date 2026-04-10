#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys

from server import rebuild_public_graph_from_live_sources


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild the Stop The Slop public knowledge graph.")
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Rebuild without deleting the existing public graph namespace first.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = rebuild_public_graph_from_live_sources(force_reset=not args.no_reset)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
