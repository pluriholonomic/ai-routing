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
    p_capture.add_argument(
        "--baseline-endpoints",
        default=None,
        help="optional retained endpoints parquet for first-snapshot price-event detection",
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

    p_gpu = sub.add_parser(
        "capture-gpu",
        help="snapshot Vast GPU offers plus Fabryka and Ornn public index histories",
    )
    p_gpu.add_argument(
        "--with-runpod",
        action="store_true",
        help="capture public Runpod Pods list prices; does not query account availability",
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

    sub.add_parser(
        "capture-router-catalogs",
        help="snapshot public Glama, Requesty, and NemoRouter provider/model quotes",
    )

    p_livepeer = sub.add_parser(
        "capture-livepeer",
        help="capture aggregate public Livepeer Gateway routing-adjustment metrics",
    )
    p_livepeer.add_argument("--samples", type=int, default=1, help="snapshots to take")
    p_livepeer.add_argument(
        "--interval-seconds", type=float, default=300.0, help="spacing between snapshots"
    )

    p_livepeer_history = sub.add_parser(
        "capture-livepeer-history",
        help="backfill bounded public aggregate Livepeer Gateway routing counters",
    )
    p_livepeer_history.add_argument(
        "--lookback-hours",
        type=int,
        default=24,
        help="public aggregate history to request (1-168; default: 24)",
    )
    p_livepeer_history.add_argument(
        "--step-minutes",
        type=int,
        default=5,
        help="aggregate LogQL window and sample step (1-60; default: 5)",
    )

    sub.add_parser(
        "capture-open-usage",
        help="capture public open-model download/pull and serving-runtime adoption proxies",
    )

    p_openrouter_usage = sub.add_parser(
        "capture-openrouter-usage",
        help="capture opt-in OpenRouter aggregate daily model token rankings",
    )
    p_openrouter_usage.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    p_openrouter_usage.add_argument("--end-date", default=None, help="YYYY-MM-DD")

    p_openrouter_apps = sub.add_parser(
        "capture-openrouter-apps",
        help="capture top public OpenRouter apps for each requested UTC day",
    )
    p_openrouter_apps.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    p_openrouter_apps.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    p_openrouter_apps.add_argument(
        "--sort", choices=["popular", "trending"], default="popular"
    )
    p_openrouter_apps.add_argument(
        "--category",
        choices=["coding", "creative", "productivity", "entertainment"],
        default=None,
    )
    p_openrouter_apps.add_argument("--subcategory", default=None)

    p_bittensor = sub.add_parser(
        "capture-bittensor",
        help="capture block-pinned public Bittensor subnet scoring and reward state",
    )
    p_bittensor.add_argument("--netuid", type=int, default=64)
    p_bittensor.add_argument("--mechid", type=int, default=0)
    p_bittensor.add_argument("--network", default="finney")

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
    p_market.add_argument(
        "--with-akash-open-book",
        action="store_true",
        help="run the expensive provider-wide open-bid diagnostic (not for hourly CI)",
    )
    p_market.add_argument(
        "--with-akash-provider-aggregates",
        action="store_true",
        help="capture public Akash aggregate provider lease-history and dashboard metrics",
    )
    p_market.add_argument(
        "--with-nosana",
        action="store_true",
        help="query public on-chain Nosana registered-node state",
    )
    p_market.add_argument(
        "--with-aethir",
        action="store_true",
        help="capture public Aethir aggregate dashboard metrics",
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
    p_compact.add_argument("--dt", default=None, help="UTC day (default: yesterday)")
    p_compact.add_argument("--shard-index", type=int, default=None)
    p_compact.add_argument("--shard-count", type=int, default=None)
    p_compact.add_argument(
        "--exclude-table",
        action="append",
        default=[],
        help="curated table to leave intact (repeatable)",
    )

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

    p_ingest_decisions = sub.add_parser(
        "ingest-router-decisions",
        help="validate and ingest payload-free timestamped router decision telemetry",
    )
    p_ingest_decisions.add_argument(
        "--input", required=True, help="redacted router-decision JSONL export"
    )

    p_ingest_flow = sub.add_parser(
        "ingest-router-flow-aggregates",
        help="validate and ingest payload-free fixed-interval router flow aggregates",
    )
    p_ingest_flow.add_argument(
        "--input", required=True, help="redacted fixed-interval flow aggregate JSONL export"
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

    p_register_reliability_audit = sub.add_parser(
        "register-reliability-audit",
        help="register a payload-free direct-provider reliability-audit manifest",
    )
    p_register_reliability_audit.add_argument(
        "--input", required=True, help="pre-outcome direct-provider audit manifest JSON"
    )

    p_ingest_reliability_assignments = sub.add_parser(
        "ingest-reliability-audit-assignments",
        help="ingest pre-assigned payload-free provider/model/epoch audit assignments",
    )
    p_ingest_reliability_assignments.add_argument(
        "--input", required=True, help="pre-assigned direct-provider audit JSONL export"
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
                        samples=args.samples,
                        interval_seconds=args.interval_seconds,
                        baseline_endpoints=args.baseline_endpoints,
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

        _collector("vast", lambda: gpu_main(with_runpod=args.with_runpod))
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
    elif args.command == "capture-router-catalogs":
        from .capture_router_catalogs import main as router_catalogs_main

        router_catalogs_main()
    elif args.command == "capture-livepeer":
        from .capture_livepeer import main as livepeer_main

        print(
            json.dumps(
                livepeer_main(samples=args.samples, interval_seconds=args.interval_seconds),
                indent=2,
                default=str,
            )
        )
    elif args.command == "capture-livepeer-history":
        from .capture_livepeer_history import main as livepeer_history_main

        livepeer_history_main(
            lookback_hours=args.lookback_hours,
            step_minutes=args.step_minutes,
        )
    elif args.command == "capture-open-usage":
        from .capture_open_usage import main as open_usage_main

        open_usage_main()
    elif args.command == "capture-openrouter-usage":
        from .capture_openrouter_datasets import main as openrouter_usage_main

        openrouter_usage_main(start_date=args.start_date, end_date=args.end_date)
    elif args.command == "capture-openrouter-apps":
        from .capture_openrouter_datasets import app_main as openrouter_apps_main

        openrouter_apps_main(
            start_date=args.start_date,
            end_date=args.end_date,
            sort=args.sort,
            category=args.category,
            subcategory=args.subcategory,
        )
    elif args.command == "capture-bittensor":
        from .capture_bittensor import main as bittensor_main

        bittensor_main(netuid=args.netuid, mechid=args.mechid, network=args.network)
    elif args.command == "capture-devrel":
        from .capture_devrel import main as devrel_main

        _collector("devrel", devrel_main)
    elif args.command == "market-capture":
        from .capture_markets import main as market_main

        market_main(
            with_uniswap=args.with_uniswap,
            with_akash=args.with_akash,
            with_akash_open_book=args.with_akash_open_book,
            with_akash_provider_aggregates=args.with_akash_provider_aggregates,
            with_nosana=args.with_nosana,
            with_aethir=args.with_aethir,
        )
    elif args.command == "register-routing-study":
        from .study_registry import register_main

        register_main(args.input)
    elif args.command == "ingest-routing-assignments":
        from .study_registry import assignments_main

        assignments_main(args.input)
    elif args.command == "register-reliability-audit":
        from .study_registry import register_reliability_audit_main

        register_reliability_audit_main(args.input)
    elif args.command == "ingest-reliability-audit-assignments":
        from .study_registry import reliability_audit_assignments_main

        reliability_audit_assignments_main(args.input)
    elif args.command == "quality":
        from .quality import main as quality_main

        quality_main(profile=args.profile, fail_on_degraded=args.fail_on_degraded)
    elif args.command == "compact":
        from .compact import main as compact_main

        compact_main(
            repo=args.repo,
            dt=args.dt,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            exclude_tables=set(args.exclude_table),
        )
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
            "h46": "h46_rolling_routing_elasticity",
            "h47": "h47_gpu_venue_basis",
            "h48": "h48_capacity_mechanism",
            "h49": "h49_solver_competition",
            "h50": "h50_controlled_routing",
            "h51": "h51_livepeer_gateway",
            "h52": "h52_cow_amm_basis",
            "h53": "h53_chutes_invocations",
            "h54": "h54_reliability_audit",
            "h55": "h55_akash_open_market_book",
            "h56": "h56_uniswap_tick_book",
            "h57": "h57_uniswap_virtual_depth",
            "h58": "h58_nosana_node_registry",
            "h59": "h59_nosana_job_activity",
            "h61": "h61_akash_dashboard",
            "h62": "h62_akash_provider_activity",
            "h64": "h64_openrouter_usage",
            "h66": "h66_simulated_provider_pricing",
            "h67": "h67_quote_pulse",
            "h68": "h68_router_enforcement",
            "h69": "h69_experiment_readiness",
            "h70": "h70_preselection_information",
            "h71": "h71_model_competition",
            "h72": "h72_openrouter_apps",
            "h75": "h75_bittensor_allocation",
            "h76": "h76_akash_lease_choice",
            "h80": "h80_matched_quote_firmness",
            "h81": "h81_delegation_decomposition",
            "h82": "h82_enforcement_substitution",
            "h83": "h83_capacity_overshoot",
            "h84": "h84_stale_quote_hazard",
            "h85": "h85_stale_quote_holdout",
            "h86": "h86_capacity_execution_bridge",
            "h86b": "h86b_canonical_capacity_bridge",
            "h87": "h87_capacity_policy_trial",
            "h88": "h88_enforcement_policy_trial",
            "h89": "h89_hf_policy_trial",
            "h90": "h90_akash_contract_termination",
            "manuscript_gate": "manuscript_promotion_gate",
            # Compute Brokerage Hypothesis modules are part of the full screen,
            # not static memo artifacts. Keep the scorecard last so it reads
            # summaries produced by this same invocation.
            "cbh1": "cbh1_repricer_census",
            "cbh2": "cbh2_gap_curve",
            "cbh3": "cbh3_price_vs_queue",
            "cbh4": "cbh4_reaction_typing",
            "cbh5": "cbh5_cadence_hierarchy",
            "cbh6": "cbh6_price_forensics",
            "cbh7": "cbh7_elasticity_wedge",
            "cbh8": "cbh8_passthrough_asym",
            "cbh9": "cbh9_forward_premium",
            "cbh10": "cbh10_price_parity",
            "cbh11": "cbh11_insulation",
            "cbh12": "cbh12_cold_start",
            "cbh13": "cbh13_spectral_dispatch",
            "cbh14": "cbh14_entry_law",
            "cbh_scorecard": "scorecard",
            # Pricing-model ladder and the Brown-MacKay competitive-null
            # sequence. BM modules consume PM outputs where available.
            "pm1": "pm1_hazard_baseline",
            "pm1_temporal": "pm1_temporal_validation",
            "pm2": "pm2_sufficient_stats",
            "pm5": "pm5_tie_microstructure",
            "pm5_heldout": "pm5_heldout_matched_market",
            "pm6": "pm6_event_reclassification",
            "pm9": "pm9_author_anchor",
            # Temporally frozen provider behavior types plus independent
            # holdout mechanism screens. WF16 does not consume WF13-WF15
            # artifacts and therefore avoids their same-panel classification.
            "wf13": "wf13_provider_strata",
            "wf14": "wf14_cohort_mechanisms",
            "wf15": "wf15_spread_explanations",
            "wf16": "wf16_provider_type_validation",
            "wf17": "wf17_within_type_collusion",
            "wf18": "wf18_signal_coupling",
            "paid_scope": "paid_market_scope",
            "bm1": "bm1_pricing_technology",
            "bm2": "bm2_fast_slow_reactions",
            "bm3": "bm3_quality_adjusted_premium",
            "bm4": "bm4_reaction_rules",
            "bm5": "bm5_competitive_null",
            # Outcome-free date selection plus executable nine-day/30-day
            # side-by-side manuscript release. Keep after the component BM
            # modules so a nightly run has already exercised their live paths.
            "manuscript_vintages": "manuscript_vintages",
            # Validation of C1-C10, counterfactual sensitivity, agent regret,
            # owned-policy identification, and the integrated verdict.
            "wcv0": "wcv0_data_audit",
            "wcv1": "wcv1_condition_audit",
            "wcv2": "wcv2_welfare_bounds",
            "wcv3": "wcv3_agent_regret",
            "wcv4": "wcv4_policy_evaluation",
            "wcv5": "wcv5_verdict",
            "wcv_dashboard": "wcv_dashboard",
        }
        chosen = [args.hypothesis] if args.hypothesis else list(modules)
        out = Path(args.out)
        results = {}
        failures = []
        from .analysis import data as analysis_data

        for h in chosen:
            # A caught optional-table error must not poison the DuckDB
            # transaction seen by a later required hypothesis.
            analysis_data.reset_connection()
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
    elif args.command == "ingest-router-decisions":
        from .router_decision_telemetry import decisions_main

        decisions_main(args.input)
    elif args.command == "ingest-router-flow-aggregates":
        from .router_decision_telemetry import flow_aggregates_main

        flow_aggregates_main(args.input)
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
