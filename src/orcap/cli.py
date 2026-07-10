"""orcap command-line entry point."""

import argparse
import json
import logging
from collections.abc import Callable
from typing import Any


def _collector(source: str, fn: Callable[[], Any]) -> Any:
    """Run a collector and record success/failure for the source-health ledger."""
    from .observability import summary_rows, write_source_run

    try:
        result = fn()
    except Exception as exc:
        write_source_run(
            source,
            status="failed",
            detail={"error_type": type(exc).__name__, "message": str(exc)},
        )
        raise
    run_ts = None
    dt = None
    if isinstance(result, dict):
        run_ts, dt = result.get("run_ts"), result.get("dt")
    elif isinstance(result, list) and result and isinstance(result[-1], dict):
        run_ts, dt = result[-1].get("run_ts"), result[-1].get("dt")
    write_source_run(
        source,
        status="success",
        rows=summary_rows(result),
        run_ts=run_ts,
        dt=dt,
        detail={"summary": json.loads(json.dumps(result, default=str))},
    )
    return result


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

    sub.add_parser(
        "capture-gpu",
        help="snapshot Vast GPU offers plus Fabryka and Ornn public index histories",
    )

    sub.add_parser("capture-direct", help="snapshot direct-provider list prices (H13 basis)")

    sub.add_parser("capture-hf", help="snapshot HF Hub model stats (demand leading indicator)")

    p_hf_router = sub.add_parser(
        "capture-hf-router",
        help="snapshot public Hugging Face Inference Providers quotes and performance",
    )
    p_hf_router.add_argument("--samples", type=int, default=1, help="snapshots to take")
    p_hf_router.add_argument(
        "--interval-seconds", type=float, default=900.0, help="spacing between snapshots"
    )

    p_livepeer = sub.add_parser(
        "capture-livepeer",
        help="capture aggregate public Livepeer Gateway routing-adjustment metrics",
    )
    p_livepeer.add_argument("--samples", type=int, default=1, help="snapshots to take")
    p_livepeer.add_argument(
        "--interval-seconds", type=float, default=300.0, help="spacing between snapshots"
    )

    sub.add_parser(
        "capture-open-usage",
        help="capture public open-model download/pull and serving-runtime adoption proxies",
    )

    sub.add_parser("capture-devrel", help="snapshot npm/pypi/github/HN developer-adoption stats")

    p_market = sub.add_parser(
        "market-capture", help="capture DeFi and decentralized-compute comparison sources"
    )
    p_market.add_argument(
        "--with-uniswap",
        action="store_true",
        help="query finalized Uniswap logs (public bounded fallback or configured RPC)",
    )
    p_market.add_argument(
        "--with-akash", action="store_true", help="query configured Akash network endpoint"
    )

    p_quality = sub.add_parser("quality", help="check source freshness and run-health ledger")
    p_quality.add_argument("--profile", default="core", help="registry profile (default: core)")
    p_quality.add_argument(
        "--fail-on-degraded",
        action="store_true",
        help="treat optional degraded sources as failures",
    )

    p_compact = sub.add_parser("compact", help="nightly compaction + pricing_changes derivation")
    p_compact.add_argument("--repo", default=None, help="HF repo id (default from config)")

    p_defi = sub.add_parser("defi", help="pull DeFi comparator series (BigQuery + Coinbase)")
    p_defi.add_argument("--force", action="store_true", help="refresh caches")

    p_analyze = sub.add_parser("analyze", help="run the empirical screen (H1-H6)")
    p_analyze.add_argument("--hypothesis", default=None, help="e.g. h2 (default: all)")
    p_analyze.add_argument("--out", default="analysis", help="output directory")
    p_analyze.add_argument(
        "--allow-partial", action="store_true", help="report analysis exceptions without failing"
    )

    p_route_report = sub.add_parser(
        "route-sim-report",
        help="evaluate whether public quote snapshots changed simulated routing",
    )
    p_route_report.add_argument("--out", default="analysis", help="output directory")

    p_ingest_route = sub.add_parser(
        "ingest-route-attempts",
        help="validate and ingest redacted owned-router attempt telemetry from JSONL",
    )
    p_ingest_route.add_argument("--input", required=True, help="redacted JSONL export path")
    p_ingest_route.add_argument(
        "--format",
        default="canonical",
        choices=[
            "canonical",
            "openrouter-generation",
            "huggingface-inference-providers",
            "cloudflare-ai-gateway",
            "portkey",
            "litellm",
        ],
        help="redacted source export format (default: canonical)",
    )
    p_ingest_route.add_argument(
        "--study-id",
        default=None,
        help="controlled-study identifier; required for source-native formats",
    )
    p_ingest_route.add_argument(
        "--router",
        default=None,
        help="optional canonical router name override for source-native formats",
    )

    p_ingest_capacity = sub.add_parser(
        "ingest-capacity-commitments",
        help="validate and ingest redacted provider/model/epoch commitments from JSONL",
    )
    p_ingest_capacity.add_argument(
        "--input", required=True, help="redacted JSONL commitment export"
    )

    p_ingest_capacity_outcomes = sub.add_parser(
        "ingest-capacity-outcomes",
        help="validate and ingest redacted provider/model/epoch allocated and served aggregates",
    )
    p_ingest_capacity_outcomes.add_argument(
        "--input", required=True, help="redacted JSONL capacity-outcome export"
    )

    p_register_study = sub.add_parser(
        "register-routing-study",
        help="validate and register a payload-free randomized routing-study manifest",
    )
    p_register_study.add_argument(
        "--input", required=True, help="pre-outcome randomized-study manifest JSON"
    )

    p_ingest_assignments = sub.add_parser(
        "ingest-routing-assignments",
        help="validate and ingest pre-assigned payload-free model-epoch treatment arms",
    )
    p_ingest_assignments.add_argument(
        "--input", required=True, help="pre-assigned treatment-arm JSONL export"
    )

    p_import_policy = sub.add_parser(
        "import-router-policy",
        help="validate and snapshot a redacted Cloudflare, Portkey, or LiteLLM policy JSON",
    )
    p_import_policy.add_argument(
        "--input", required=True, help="redacted normalized policy JSON path"
    )

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
                _collector(
                    "openrouter_api",
                    lambda: capture_main(
                        samples=args.samples, interval_seconds=args.interval_seconds
                    ),
                ),
                indent=2,
                default=str,
            )
        )
    elif args.command == "push":
        from .hf_store import push

        push(message=args.message, delete_local=args.delete_local)
    elif args.command == "scrape":
        from .scrape_charts import main as scrape_main

        _collector("openrouter_frontend", lambda: scrape_main(limit=args.limit))
    elif args.command == "discover":
        from .discover import main as discover_main

        discover_main()
    elif args.command == "capture-gpu":
        from .capture_gpu import main as gpu_main

        _collector("vast", gpu_main)
    elif args.command == "capture-direct":
        from .capture_direct import main as direct_main

        _collector("direct_providers", direct_main)
    elif args.command == "capture-hf":
        from .capture_hf_stats import main as hf_main

        _collector("huggingface", hf_main)
    elif args.command == "capture-hf-router":
        from .capture_hf_router import main as hf_router_main

        print(
            json.dumps(
                _collector(
                    "huggingface_inference_providers",
                    lambda: hf_router_main(
                        samples=args.samples, interval_seconds=args.interval_seconds
                    ),
                ),
                indent=2,
                default=str,
            )
        )
    elif args.command == "capture-livepeer":
        from .capture_livepeer import main as livepeer_main

        print(
            json.dumps(
                livepeer_main(samples=args.samples, interval_seconds=args.interval_seconds),
                indent=2,
                default=str,
            )
        )
    elif args.command == "capture-open-usage":
        from .capture_open_usage import main as open_usage_main

        open_usage_main()
    elif args.command == "capture-devrel":
        from .capture_devrel import main as devrel_main

        _collector("devrel", devrel_main)
    elif args.command == "market-capture":
        from .capture_markets import main as market_main

        market_main(with_uniswap=args.with_uniswap, with_akash=args.with_akash)
    elif args.command == "register-routing-study":
        from .study_registry import register_main

        register_main(args.input)
    elif args.command == "ingest-routing-assignments":
        from .study_registry import assignments_main

        assignments_main(args.input)
    elif args.command == "quality":
        from .quality import main as quality_main

        quality_main(profile=args.profile, fail_on_degraded=args.fail_on_degraded)
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
            "h20": "h20_demand_price",
            "h21": "h21_reactions",
            "h23": "h23_toxicity",
            "h26": "h26_entry",
            "h29": "h29_demand",
            "h31": "h31_gpu_supply",
            "h32": "h32_distribution",
            "h33": "h33_scorecard",
            "h34": "h34_orderbook",
            "h35": "h35_term",
            "h36": "h36_carry",
            "h37": "h37_inventory",
            "h38": "h38_burstiness",
            "h39": "h39_arrivals",
            "h40": "h40_router_demand",
            "h41": "h41_market_comparison",
            "h42": "h42_routing_mev",
            "h43": "h43_routing_simulation",
            "h44": "h44_cross_router",
            "h45": "h45_shadow_execution",
            "h47": "h47_gpu_venue_basis",
            "h48": "h48_capacity_mechanism",
            "h49": "h49_solver_competition",
            "h50": "h50_controlled_routing",
            "h51": "h51_livepeer_gateway",
            "h52": "h52_cow_amm_basis",
        }
        chosen = [args.hypothesis] if args.hypothesis else list(modules)
        out = Path(args.out)
        results = {}
        failures = []
        for h in chosen:
            mod = importlib.import_module(f"orcap.analysis.{modules[h]}")
            try:
                results[h] = mod.run(out)
            except Exception as exc:  # keep going; screen reports partial results
                logging.exception("hypothesis %s failed", h)
                results[h] = {"error": str(exc)}
                failures.append(h)
        print(json.dumps(results, indent=2, default=str))
        if failures and not args.allow_partial:
            raise RuntimeError(f"required analyses failed: {', '.join(failures)}")
    elif args.command == "route-sim-report":
        from pathlib import Path

        from .analysis.h43_routing_simulation import run as route_simulation_report

        print(json.dumps(route_simulation_report(Path(args.out)), indent=2, default=str))
    elif args.command == "ingest-route-attempts":
        from pathlib import Path

        from .route_telemetry import load_jsonl, normalize_export, write_attempts

        events = load_jsonl(Path(args.input))
        normalized = normalize_export(
            events,
            export_format=args.format,
            study_id=args.study_id,
            router=args.router,
        )
        output = write_attempts(normalized)
        print(
            json.dumps(
                {
                    "rows": len(normalized),
                    "format": args.format,
                    "path": str(output) if output else None,
                },
                indent=2,
            )
        )
    elif args.command == "ingest-capacity-commitments":
        from pathlib import Path

        from .capacity_telemetry import load_jsonl, write_commitments

        records = load_jsonl(Path(args.input))
        output = write_commitments(records)
        print(json.dumps({"rows": len(records), "path": str(output) if output else None}, indent=2))
    elif args.command == "ingest-capacity-outcomes":
        from pathlib import Path

        from .capacity_telemetry import load_jsonl, write_outcomes

        records = load_jsonl(Path(args.input))
        output = write_outcomes(records)
        print(json.dumps({"rows": len(records), "path": str(output) if output else None}, indent=2))
    elif args.command == "import-router-policy":
        from pathlib import Path

        from .router_policy import (
            load_policy_document,
            normalize_policy_document,
            write_policy_snapshot,
        )

        document = load_policy_document(Path(args.input))
        rows = normalize_policy_document(document)
        output = write_policy_snapshot(document)
        print(json.dumps({"rows": len(rows), "path": str(output)}, indent=2))


if __name__ == "__main__":
    main()
