"""orcap command-line entry point."""

import argparse
import json
import logging


def main() -> None:
    parser = argparse.ArgumentParser(prog="orcap", description="OpenRouter market-history capture")
    sub = parser.add_subparsers(dest="command", required=True)

    p_capture = sub.add_parser(
        "capture", help="snapshot models/providers/endpoints from the v1 API"
    )
    p_capture.add_argument(
        "--samples", type=int, default=1, help="snapshots to take within this invocation"
    )
    p_capture.add_argument(
        "--interval-seconds", type=float, default=300.0, help="spacing between samples"
    )

    p_push = sub.add_parser("push", help="upload the local data dir to the HF dataset repo")
    p_push.add_argument("--message", default=None)
    p_push.add_argument(
        "--delete-local", action="store_true", help="clear the data dir after a successful push"
    )

    p_scrape = sub.add_parser(
        "scrape", help="capture frontend chart data (apps/activity/uptime/rankings)"
    )
    p_scrape.add_argument("--limit", type=int, default=None, help="max model×variant combos")

    sub.add_parser("discover", help="sniff a model page and dump internal API endpoints seen")

    p_compact = sub.add_parser("compact", help="nightly compaction + pricing_changes derivation")
    p_compact.add_argument("--repo", default=None, help="HF repo id (default from config)")

    p_backfill = sub.add_parser("backfill", help="best-effort historical backfill (model-level)")
    p_backfill.add_argument(
        "--source", choices=["wayback", "orw", "all"], default="all", help="backfill source"
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.command == "capture":
        from .capture_api import main as capture_main

        print(
            json.dumps(
                capture_main(samples=args.samples, interval_seconds=args.interval_seconds),
                indent=2,
                default=str,
            )
        )
    elif args.command == "push":
        from .hf_store import push

        push(message=args.message, delete_local=args.delete_local)
    elif args.command == "scrape":
        from .scrape_charts import main as scrape_main

        scrape_main(limit=args.limit)
    elif args.command == "discover":
        from .discover import main as discover_main

        discover_main()
    elif args.command == "compact":
        from .compact import main as compact_main

        compact_main(repo=args.repo)
    elif args.command == "backfill":
        from .backfill import main as backfill_main

        backfill_main(source=args.source)


if __name__ == "__main__":
    main()
