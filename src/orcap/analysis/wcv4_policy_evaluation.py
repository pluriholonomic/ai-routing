"""WCV4 — fail-closed realized-routing and policy-evaluation audit."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json


def load_attempts() -> pd.DataFrame:
    try:
        glob = data.table_glob("router_route_attempts")
        return data.q(
            f"""
            select distinct *
            from read_parquet('{glob}', union_by_name=true)
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    attempts = load_attempts()
    if not attempts.empty and {"source", "event_id"}.issubset(attempts.columns):
        sort_columns = ["source", "event_id"]
        if "run_ts" in attempts:
            sort_columns.append("run_ts")
        attempts = attempts.sort_values(sort_columns).drop_duplicates(
            ["source", "event_id"], keep="last"
        )
    if attempts.empty:
        panel = pd.DataFrame(
            columns=[
                "policy",
                "attempts",
                "success_rate",
                "fallback_rate",
                "mean_cost_usd",
                "mean_latency_ms",
            ]
        )
    else:
        if "policy" not in attempts:
            attempts["policy"] = ""
        attempts["policy"] = attempts["policy"].astype("string").fillna("")
        attempts["success"] = attempts["outcome"].astype(str).eq("succeeded")
        if "fallback_triggered" not in attempts:
            attempts["fallback_triggered"] = False
        attempts["fallback"] = attempts["fallback_triggered"].fillna(False).astype(bool)
        attempts["cost_usd"] = pd.to_numeric(
            attempts["cost_usd"] if "cost_usd" in attempts else pd.Series(index=attempts.index),
            errors="coerce",
        )
        attempts["latency_ms"] = pd.to_numeric(
            attempts["latency_ms"]
            if "latency_ms" in attempts
            else pd.Series(index=attempts.index),
            errors="coerce",
        )
        panel = (
            attempts.groupby("policy", dropna=False)
            .agg(
                attempts=("event_id", "nunique"),
                success_rate=("success", "mean"),
                fallback_rate=("fallback", "mean"),
                mean_cost_usd=("cost_usd", "mean"),
                mean_latency_ms=("latency_ms", "mean"),
            )
            .reset_index()
        )
    save(panel, out_dir, "wcv4_policy_panel")
    try:
        h50 = json.loads((out_dir / "h50_summary.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        h50 = {}
    randomized = h50.get("evidence_status") == "supported_in_study_domain"
    summary = {
        "evidence_status": (
            "supported_in_study_domain"
            if randomized
            else ("descriptive_owned_traffic" if len(attempts) else "not_collected")
        ),
        "attempts": int(len(attempts)),
        "attempts_with_selected_provider": (
            int(attempts["selected_provider"].notna().sum())
            if len(attempts) and "selected_provider" in attempts
            else 0
        ),
        "policies_observed": int(panel["policy"].nunique()) if len(panel) else 0,
        "randomized_h50_ready": randomized,
        "off_policy_evaluation": "not_identified_without_logged_assignment_propensity_and_overlap",
        "policy_panel": panel.to_dict("records"),
        "claim_boundary": (
            "Policy aggregates are descriptive unless they inherit a valid pre-registered H50 "
            "randomization. OPE is intentionally refused without known propensities and overlap."
        ),
    }
    save_json(summary, out_dir, "wcv4_summary")
    return summary
