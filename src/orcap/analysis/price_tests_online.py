"""Recurring, revision-pinned online panel for the preregistered price tests."""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import tempfile
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
    wf19_undercutting_incidence,
)

STUDY_ID = "openrouter-online-price-tests-v1"


def _runners() -> dict[str, Callable[[Path], dict[str, Any]]]:
    return {
        "h2": h2_dispersion.run,
        "h13": h13_venue_basis.run,
        "bm1": bm1_pricing_technology.run,
        "h42": h42_routing_mev.run,
        "h46": h46_rolling_routing_elasticity.run,
        "h93": h93_cross_router_price_policy.run,
        "h94": h94_cross_router_pass_through.run,
        "sync": _synchronization_monitor,
        "wf19": wf19_undercutting_incidence.run,
    }


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


def _synchronization_monitor(output_dir: Path) -> dict[str, Any]:
    """Track same-direction quote updates without assigning causal intent."""
    changes = data.q(
        f"""
        select changed_at_run_ts, model_id, provider_name,
               try_cast(old_value as double) old_price,
               try_cast(new_value as double) new_price
        from read_parquet(
          '{data.table_glob("pricing_changes", layer="derived")}',
          union_by_name=true
        )
        where field = 'price_completion'
          and try_cast(old_value as double) > 0
          and try_cast(new_value as double) > 0
          and old_value != new_value
        """
    ).df()
    if changes.empty:
        result = {
            "evidence_status": "power_gated",
            "n_price_changes": 0,
            "claim_boundary": "No synchronization result without public price changes.",
        }
    else:
        changes["direction"] = (changes["new_price"] > changes["old_price"]).map(
            {True: "raise", False: "cut"}
        )
        cells = (
            changes.groupby(["changed_at_run_ts", "model_id", "direction"])[
                "provider_name"
            ]
            .nunique()
            .reset_index(name="providers")
        )
        cells["provider_pairs"] = cells["providers"] * (cells["providers"] - 1) // 2
        result = {
            "evidence_status": "descriptive_synchronization_monitor",
            "n_price_changes": int(len(changes)),
            "n_models": int(changes["model_id"].nunique()),
            "n_providers": int(changes["provider_name"].nunique()),
            "same_direction_pairs": int(cells["provider_pairs"].sum()),
            "multi_provider_cells": int((cells["providers"] >= 2).sum()),
            "claim_boundary": (
                "Same-clock, same-direction public quote moves are descriptive. They do not "
                "identify shared algorithms, communication, intent, or a causal response."
            ),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        cells.to_parquet(output_dir / "synchronization-cells.parquet", index=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def _run_module(name: str, output_dir: Path) -> dict[str, Any]:
    runner = _runners().get(name)
    if runner is None:
        raise ValueError(f"unknown price-test module: {name}")
    with data.pinned_analysis_source() as source:
        result = _run_safely(runner, output_dir / name)
    return {"analysis_source": source, "result": result}


def _run_modules_in_process(output_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        name: _run_safely(runner, output_dir / name)
        for name, runner in _runners().items()
    }


def _run_modules_isolated(output_dir: Path) -> dict[str, dict[str, Any]]:
    """Run each hypothesis in a fresh process to bound peak runner memory."""
    results: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="orcap-price-tests-") as temp_dir:
        temp = Path(temp_dir)
        for name in _runners():
            result_file = temp / f"{name}.json"
            print(f"[price-tests] starting isolated module {name}", flush=True)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "orcap.analysis.price_tests_online",
                    "--output-dir",
                    str(output_dir),
                    "--module",
                    name,
                    "--result-file",
                    str(result_file),
                ],
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"isolated price-test module {name} exited "
                    f"{completed.returncode}"
                )
            if not result_file.is_file():
                raise RuntimeError(
                    f"isolated price-test module {name} produced no result file"
                )
            payload = json.loads(result_file.read_text(encoding="utf-8"))
            results[name] = payload["result"]
            print(f"[price-tests] completed isolated module {name}", flush=True)
    return results


def _assemble(
    output_dir: Path,
    source: dict[str, str | None],
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    mapping = [
        ("P1", "routing price elasticity", "h46"),
        ("P2", "within-model posted-price dispersion", "h2"),
        ("P3", "pricing technology and update cadence", "bm1"),
        ("P4", "post-cut routing-flow response", "h42"),
        ("P5", "quote fading and adverse-selection proxy", "h42"),
        ("P6", "model-author benchmark basis", "h13"),
        ("P7", "cadence-premium segmentation", "bm1"),
        ("P8", "same-direction quote synchronization", "sync"),
        ("P9", "cross-router posted-price pass-through", "h94"),
        ("P10", "active-undercutter share and revenue incidence", "wf19"),
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


def run(output_dir: Path, *, isolate_modules: bool = False) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with data.pinned_analysis_source() as source:
        if isolate_modules:
            results = _run_modules_isolated(output_dir)
        else:
            results = _run_modules_in_process(output_dir)
    return _assemble(output_dir, source, results)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/analysis/price-tests-online")
    )
    parser.add_argument(
        "--isolate-modules",
        action="store_true",
        help="run every hypothesis in a fresh process to bound peak memory",
    )
    parser.add_argument("--module", choices=tuple(_runners()))
    parser.add_argument("--result-file", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.module:
        payload = _run_module(args.module, args.output_dir)
        if args.result_file:
            args.result_file.parent.mkdir(parents=True, exist_ok=True)
            args.result_file.write_text(
                json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
                encoding="utf-8",
            )
        else:
            print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return
    if args.result_file:
        parser.error("--result-file requires --module")
    print(
        json.dumps(
            run(args.output_dir, isolate_modules=args.isolate_modules),
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
