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

    sub.add_parser("capture-gpu", help="snapshot GPU rental offers (vast.ai) + price indices")

    sub.add_parser("capture-direct", help="snapshot direct-provider list prices (H13 basis)")

    sub.add_parser("capture-hf", help="snapshot HF Hub model stats (demand leading indicator)")

    p_compact = sub.add_parser("compact", help="nightly compaction + pricing_changes derivation")
    p_compact.add_argument("--repo", default=None, help="HF repo id (default from config)")

    p_defi = sub.add_parser("defi", help="pull DeFi comparator series (BigQuery + Coinbase)")
    p_defi.add_argument("--force", action="store_true", help="refresh caches")

    p_analyze = sub.add_parser("analyze", help="run the empirical screen (H1-H6)")
    p_analyze.add_argument("--hypothesis", default=None, help="e.g. h2 (default: all)")
    p_analyze.add_argument("--out", default="analysis", help="output directory")

    sub.add_parser("memo", help="render the screening memo from latest analysis outputs")

    p_backfill = sub.add_parser("backfill", help="best-effort historical backfill (model-level)")
    p_backfill.add_argument(
        "--source",
        choices=["wayback", "orw", "litellm", "all"],
        default="all",
        help="backfill source",
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
    elif args.command == "capture-gpu":
        from .capture_gpu import main as gpu_main

        gpu_main()
    elif args.command == "capture-direct":
        from .capture_direct import main as direct_main

        direct_main()
    elif args.command == "capture-hf":
        from .capture_hf_stats import main as hf_main

        hf_main()
    elif args.command == "compact":
        from .compact import main as compact_main

        compact_main(repo=args.repo)
    elif args.command == "backfill":
        from .backfill import main as backfill_main

        backfill_main(source=args.source)
    elif args.command == "memo":
        from .memo import main as memo_main

        memo_main()
    elif args.command == "defi":
        from .defi_benchmarks import main as defi_main

        defi_main(force=args.force)
    elif args.command == "analyze":
        import importlib
        from pathlib import Path

        modules = {
            "h1": "h1_spells",
            "h1b": "h1b_litellm",
            "h2": "h2_dispersion",
            "h8": "h8_events",
            "h3": "h3_entry",
            "h4": "h4_routing",
            "h5": "h5_frontends",
            "h6": "h6_fees",
            "h7": "h7_passthrough",
            "h10": "h10_lastlook",
            "h11": "h11_quality",
            "h12": "h12_basis",
            "h13": "h13_venue_basis",
            "h14": "h14_ordertypes",
            "h17": "h17_events",
            "h18": "h18_predict",
            "h19": "h19_provider_types",
            "h19b": "h19_text",
            "h21": "h21_reactions",
            "h23": "h23_toxicity",
            "h26": "h26_entry",
            "h29": "h29_demand",
            "h32": "h32_distribution",
            "h33": "h33_scorecard",
            "h34": "h34_orderbook",
            "h35": "h35_term",
            "h36": "h36_carry",
            "h37": "h37_inventory",
            "h38": "h38_burstiness",
            "h39": "h39_arrivals",
        }
        chosen = [args.hypothesis] if args.hypothesis else list(modules)
        out = Path(args.out)
        results = {}
        for h in chosen:
            mod = importlib.import_module(f"orcap.analysis.{modules[h]}")
            try:
                results[h] = mod.run(out)
            except Exception as exc:  # keep going; screen reports partial results
                logging.exception("hypothesis %s failed", h)
                results[h] = {"error": str(exc)}
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
