"""Integrity-first monitoring and fixed-horizon analysis for the paid study."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from ..adaptive_router import FIXED_HORIZON_BLOCKS, POLICY_SPECS, STUDY_ID

POLICIES = tuple(str(row["policy"]) for row in POLICY_SPECS)
FAILURE_LATENCY_MS = 90_000.0


def _read(data_root: Path, table: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in data_root.glob(f"curated/{table}/dt=*/*.parquet"):
        try:
            rows.extend(pq.ParquetFile(path).read().to_pylist())
        except OSError:
            continue
    return pd.DataFrame(rows)


def _attempt_tasks(attempts: pd.DataFrame) -> pd.DataFrame:
    if attempts.empty:
        return attempts.assign(task_id=pd.Series(dtype=str))
    output = attempts.copy()
    output["task_id"] = output["metadata_json"].map(
        lambda value: str(json.loads(value or "{}").get("task_id") or "")
    )
    output = output[output["task_id"] != ""]
    return output.sort_values("observed_at").drop_duplicates("task_id", keep="last")


def assignment_integrity(assignments: pd.DataFrame) -> dict[str, Any]:
    failures: list[str] = []
    if assignments.empty:
        return {
            "status": "waiting",
            "failures": ["no_assignments"],
            "written_blocks": 0,
            "written_tasks": 0,
        }
    if assignments["task_id"].duplicated().any():
        failures.append("duplicate_task_id")
    expected = set(POLICIES)
    bad_policy_blocks = 0
    for _, group in assignments.groupby("block_id"):
        if set(group["policy"]) != expected or len(group) != len(expected):
            bad_policy_blocks += 1
    if bad_policy_blocks:
        failures.append("nonrectangular_policy_blocks")
    numeric = assignments.copy()
    for column in ("provider_probability", "arm_probability", "joint_probability"):
        numeric[column] = pd.to_numeric(numeric[column], errors="coerce")
    if not numeric["provider_probability"].between(0, 1, inclusive="right").all():
        failures.append("invalid_provider_probability")
    if not np.allclose(numeric["arm_probability"], 1.0):
        failures.append("arm_inclusion_not_one")
    if not np.allclose(numeric["provider_probability"], numeric["joint_probability"]):
        failures.append("joint_probability_mismatch")
    if numeric["allow_fallbacks"].fillna(True).astype(bool).any():
        failures.append("fallbacks_not_disabled")
    probability_mismatches = 0
    for row in numeric.to_dict("records"):
        try:
            target = json.loads(str(row["target_probabilities_json"]))
            requested = str(row["requested_provider"] or "").casefold()
            keyed = {str(key).casefold(): float(value) for key, value in target.items()}
            if not np.isclose(sum(keyed.values()), 1.0) or not np.isclose(
                keyed[requested], float(row["provider_probability"])
            ):
                probability_mismatches += 1
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            probability_mismatches += 1
    if probability_mismatches:
        failures.append("target_probability_mismatch")
    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "written_blocks": int(assignments["block_id"].nunique()),
        "written_tasks": int(len(assignments)),
        "nonrectangular_policy_blocks": bad_policy_blocks,
        "probability_mismatches": probability_mismatches,
    }


def _paired_intervals(panel: pd.DataFrame, *, draws: int = 2_000) -> pd.DataFrame:
    rng = np.random.default_rng(20260721)
    outcomes = ("success", "cost_usd", "bounded_latency_ms")
    rows = []
    for policy in POLICIES:
        if policy == "baseline_eta2":
            continue
        for outcome in outcomes:
            pivot = panel.pivot(index="block_id", columns="policy", values=outcome)
            pair = pivot[["baseline_eta2", policy]].dropna()
            difference = pair[policy].to_numpy() - pair["baseline_eta2"].to_numpy()
            sampled = difference[
                rng.integers(0, len(difference), size=(draws, len(difference)))
            ].mean(axis=1)
            low, high = np.quantile(sampled, [0.025, 0.975])
            rows.append(
                {
                    "policy": policy,
                    "outcome": outcome,
                    "blocks": len(difference),
                    "paired_difference": float(difference.mean()),
                    "bootstrap_ci_low": float(low),
                    "bootstrap_ci_high": float(high),
                    "reference": "baseline_eta2",
                }
            )
    return pd.DataFrame(rows)


def analyze(
    *, data_root: Path, out_dir: Path, source_revision: str = "local"
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    assignments = _read(data_root, "adaptive_router_assignments")
    attempts = _attempt_tasks(_read(data_root, "adaptive_router_attempts"))
    if assignments.empty:
        assignments = pd.DataFrame(
            columns=[
                "task_id",
                "block_id",
                "policy",
                "study_id",
                "provider_probability",
                "arm_probability",
                "joint_probability",
                "allow_fallbacks",
                "target_probabilities_json",
                "requested_provider",
            ]
        )
    else:
        assignments = assignments[assignments["study_id"] == STUDY_ID].copy()
        assignments = assignments.drop_duplicates("task_id", keep="last")
    if not attempts.empty:
        attempts = attempts[attempts["study_id"] == STUDY_ID].copy()
    integrity = assignment_integrity(assignments)
    panel = assignments.merge(
        attempts[
            [
                "task_id",
                "observed_at",
                "outcome",
                "selected_provider",
                "cost_usd",
                "latency_ms",
                "fallback_triggered",
            ]
        ]
        if not attempts.empty
        else pd.DataFrame(columns=[
            "task_id",
            "observed_at",
            "outcome",
            "selected_provider",
            "cost_usd",
            "latency_ms",
            "fallback_triggered",
        ]),
        on="task_id",
        how="left",
        validate="one_to_one",
    )
    if not panel.empty:
        panel["attempted"] = panel["outcome"].notna()
        panel["success"] = (panel["outcome"] == "succeeded").astype(float)
        panel["cost_usd"] = pd.to_numeric(panel["cost_usd"], errors="coerce").fillna(0.0)
        latency = pd.to_numeric(panel["latency_ms"], errors="coerce")
        panel["bounded_latency_ms"] = latency.where(
            (panel["outcome"] == "succeeded") & latency.notna(), FAILURE_LATENCY_MS
        )
    complete_blocks = 0
    launched_blocks = 0
    analysis_panel = panel.copy()
    if not panel.empty:
        complete_blocks = int(
            panel.groupby("block_id")["attempted"].agg(["sum", "size"]).eval("sum == size").sum()
        )
        launched = (
            panel[panel["attempted"]]
            .groupby("block_id", as_index=False)["observed_at"]
            .min()
            .sort_values(["observed_at", "block_id"], kind="stable")
        )
        launched_blocks = int(len(launched))
        frozen_blocks = set(launched["block_id"].head(FIXED_HORIZON_BLOCKS))
        analysis_panel = panel[panel["block_id"].isin(frozen_blocks)].copy()
    release_ready = (
        integrity["status"] == "pass" and launched_blocks >= FIXED_HORIZON_BLOCKS
    )
    operational = {
        "study_id": STUDY_ID,
        "source_revision": source_revision,
        "written_blocks": integrity["written_blocks"],
        "complete_blocks": complete_blocks,
        "launched_blocks": launched_blocks,
        "fixed_horizon_blocks": FIXED_HORIZON_BLOCKS,
        "attempts": int(panel["attempted"].sum()) if not panel.empty else 0,
        "successful_requests": int(panel["success"].sum()) if not panel.empty else 0,
        "realized_cost_usd": float(panel["cost_usd"].sum()) if not panel.empty else 0.0,
        "assignment_integrity": integrity,
        "confirmatory_released": release_ready,
        "status": "released" if release_ready else "collecting",
        "claim_boundary": (
            "Before 120 launched rectangular blocks, outputs are operational health only. "
            "At the fixed horizon, paired owned-request effects identify the emulated "
            "allocation rules on sampled menus, not market-wide welfare or provider response."
        ),
    }
    (out_dir / "adaptive-router-live-status.json").write_text(
        json.dumps(operational, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    health = (
        panel.groupby("policy", as_index=False)
        .agg(planned_tasks=("task_id", "size"), attempted_tasks=("attempted", "sum"))
        if not panel.empty
        else pd.DataFrame(columns=["policy", "planned_tasks", "attempted_tasks"])
    )
    health.to_csv(out_dir / "adaptive-router-arm-health.csv", index=False)
    if release_ready:
        # Intention-to-treat: a launched block retains every frozen assignment.
        # Missing attempts are failures with the preregistered latency penalty.
        released = analysis_panel.copy()
        policy_results = released.groupby("policy", as_index=False).agg(
            blocks=("block_id", "nunique"),
            success_rate=("success", "mean"),
            mean_cost_usd=("cost_usd", "mean"),
            mean_bounded_latency_ms=("bounded_latency_ms", "mean"),
            selected_providers=("selected_provider", "nunique"),
        )
        intervals = _paired_intervals(released)
        policy_results.to_csv(out_dir / "adaptive-router-policy-results.csv", index=False)
        intervals.to_csv(out_dir / "adaptive-router-paired-results.csv", index=False)
    html = [
        "<!doctype html><meta charset='utf-8'><title>Adaptive router live monitor</title>",
        "<style>body{font:15px system-ui;max-width:1050px;margin:36px auto;color:#222}",
        "table{border-collapse:collapse}th,td{padding:7px 12px;border-bottom:1px solid #ddd}",
        "th{text-align:left}code{background:#f4f4f4;padding:2px 4px}</style>",
        "<h1>Adaptive router live monitor</h1>",
        f"<p><strong>{launched_blocks}/{FIXED_HORIZON_BLOCKS}</strong> launched blocks "
        f"({complete_blocks} complete); "
        f"confirmatory release: <code>{str(release_ready).lower()}</code>.</p>",
        health.to_html(index=False, border=0),
        "<p>Arm-specific outcomes remain frozen until the fixed horizon. This page is "
        "operational health, not a sequential significance dashboard.</p>",
    ]
    (out_dir / "adaptive-router-live.html").write_text("\n".join(html), encoding="utf-8")
    return operational


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/analysis/adaptive-router-live")
    )
    parser.add_argument("--source-revision", default="local")
    args = parser.parse_args()
    print(
        json.dumps(
            analyze(
                data_root=args.data_root,
                out_dir=args.output_dir,
                source_revision=args.source_revision,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
