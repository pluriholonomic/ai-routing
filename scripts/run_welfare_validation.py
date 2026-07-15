#!/usr/bin/env python3
"""Run the registered Brown-MacKay and welfare-validation sequence."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from orcap.analysis import data

MODULES = [
    "h4_routing",
    "h11_quality",
    "h23_toxicity",
    "h37_inventory",
    "h48_capacity_mechanism",
    "h50_controlled_routing",
    "h54_reliability_audit",
    "h69_experiment_readiness",
    "h80_matched_quote_firmness",
    "pm1_hazard_baseline",
    "pm2_sufficient_stats",
    "pm5_tie_microstructure",
    "pm6_event_reclassification",
    "pm9_author_anchor",
    "bm1_pricing_technology",
    "bm2_fast_slow_reactions",
    "bm3_quality_adjusted_premium",
    "bm4_reaction_rules",
    "bm5_competitive_null",
    "wcv0_data_audit",
    "wcv1_condition_audit",
    "wcv2_welfare_bounds",
    "wcv3_agent_regret",
    "wcv4_policy_evaluation",
    "wcv5_verdict",
    "wcv_dashboard",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("analysis"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    results = {}
    failures = []
    for name in MODULES:
        data.reset_connection()
        try:
            module = importlib.import_module(f"orcap.analysis.{name}")
            results[name] = module.run(args.out)
        except Exception as exc:
            results[name] = {"error": f"{type(exc).__name__}: {exc}"}
            failures.append(name)
            if args.strict:
                raise
    print(json.dumps({"failures": failures, "results": results}, indent=2, default=str))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
