"""Recurring, revision-pinned online panel for the preregistered price tests."""

from __future__ import annotations

import argparse
import html
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from . import (
    bm1_pricing_technology,
    data,
    h2_dispersion,
    h13_venue_basis,
    h42_routing_mev,
    h46_rolling_routing_elasticity,
    h93_cross_router_price_policy,
    h94_cross_router_pass_through,
    h97_critical_memory_empirical,
)

STUDY_ID = "openrouter-online-price-tests-v1"


def _status(result: dict[str, Any]) -> str:
    for key in ("evidence_status", "status", "gated"):
        if result.get(key):
            return str(result[key])
    return "completed"


def _run_safely(
    runner: Callable[[Path], dict[str, Any]], output_dir: Path
) -> dict[str, Any]:
    try:
        return runner(output_dir)
    except Exception as exc:  # the registry must preserve unavailable tests
        return {
            "evidence_status": "unavailable",
            "error_type": type(exc).__name__,
            "claim_boundary": "No result is reported when its required public table is absent.",
        }


def run(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runners: dict[str, Callable[[Path], dict[str, Any]]] = {
        "h2": h2_dispersion.run,
        "h13": h13_venue_basis.run,
        "bm1": bm1_pricing_technology.run,
        "h42": h42_routing_mev.run,
        "h46": h46_rolling_routing_elasticity.run,
        "h93": h93_cross_router_price_policy.run,
        "h94": h94_cross_router_pass_through.run,
        "h97": h97_critical_memory_empirical.run,
    }
    with data.pinned_analysis_source() as source:
        results = {
            name: _run_safely(runner, output_dir / name)
            for name, runner in runners.items()
        }
    mapping = [
        ("P1", "routing price elasticity", "h46"),
        ("P2", "within-model posted-price dispersion", "h2"),
        ("P3", "pricing technology and update cadence", "bm1"),
        ("P4", "post-cut owned-routing response", "h97"),
        ("P5", "quote fading and adverse-selection proxy", "h42"),
        ("P6", "model-author benchmark basis", "h13"),
        ("P7", "cadence-premium segmentation", "bm1"),
        ("P8", "same-direction quote synchronization", "h97"),
        ("P9", "cross-router posted-price pass-through", "h94"),
    ]
    rows = [
        {
            "study_id": STUDY_ID,
            "analysis_at": datetime.now(UTC).isoformat(),
            "test_id": test_id,
            "estimand": estimand,
            "source_module": module,
            "status": _status(results[module]),
            "claim_boundary": str(results[module].get("claim_boundary") or ""),
        }
        for test_id, estimand, module in mapping
    ]
    panel = pd.DataFrame(rows)
    panel.to_parquet(output_dir / "price-tests-status.parquet", index=False)
    summary = {
        "study_id": STUDY_ID,
        "analysis_source": source,
        "tests": rows,
        "module_results": results,
        "claim_boundary": (
            "This monitoring panel combines observational public-price tests and owned-probe "
            "tests. Status significance does not convert an observational result into causality."
        ),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    table = "".join(
        "<tr><td>"
        + html.escape(str(row["test_id"]))
        + "</td><td>"
        + html.escape(str(row["estimand"]))
        + "</td><td>"
        + html.escape(str(row["status"]))
        + "</td><td>"
        + html.escape(str(row["source_module"]))
        + "</td></tr>"
        for row in rows
    )
    dashboard = """<!doctype html><meta charset="utf-8"><title>Online price tests</title>
<style>body{font:15px system-ui;max-width:1050px;margin:40px auto;color:#17202a}
table{border-collapse:collapse;width:100%}th,td{padding:9px;border-bottom:1px solid #d8dee4;
text-align:left}th{background:#f4f6f8}.boundary{border-left:4px solid #c78317;padding:12px}</style>
<h1>Online price-test registry</h1>
<p>Revision-pinned monitoring; unavailable cells remain explicit.</p>
<table><thead><tr><th>Test</th><th>Estimand</th><th>Status</th><th>Module</th></tr></thead>
<tbody>""" + table + "</tbody></table><p class='boundary'>" + html.escape(
        summary["claim_boundary"]
    ) + "</p>"
    (output_dir / "price-tests.html").write_text(dashboard, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/analysis/price-tests-online")
    )
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
