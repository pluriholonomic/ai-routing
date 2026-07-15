"""WCV0 — authoritative data freeze and observability inventory."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

TABLES = [
    ("endpoints_snapshots", "curated", "public quote surface"),
    ("pricing_changes", "derived", "public repricing events"),
    ("effective_pricing_daily", "curated", "public provider token allocation"),
    ("congestion_intraday", "curated", "public router enforcement and capacity"),
    ("models_snapshots", "curated", "model and author anchors"),
    ("gpu_offers_snapshots", "curated", "GPU cost/supply proxy"),
    ("routing_simulation", "curated", "public shadow allocation"),
    ("router_route_attempts", "curated", "owned realized routing"),
    ("router_flow_aggregates", "curated", "router aggregate flow"),
    ("router_decision_events", "curated", "private-signal randomized study"),
    ("router_capacity_commitments", "curated", "declared capacity contracts"),
    ("router_capacity_epoch_outcomes", "curated", "delivered capacity outcomes"),
    ("router_experiment_manifests", "curated", "registered routing studies"),
    ("router_experiment_assignments", "curated", "randomized routing assignments"),
    ("router_reliability_audit_assignments", "curated", "reliability audits"),
]


def inventory_row(table: str, layer: str, role: str) -> dict:
    glob = data.table_glob(table, layer=layer)
    base = {"table": table, "layer": layer, "role": role}
    try:
        schema = data.q(
            f"describe select * from read_parquet('{glob}', union_by_name=true)"
        ).df()
        columns = set(schema["column_name"])
        expressions = ["count(*) as rows"]
        if "dt" in columns:
            expressions += [
                "count(distinct dt) as days",
                "cast(min(dt) as varchar) as first_dt",
                "cast(max(dt) as varchar) as last_dt",
            ]
        else:
            expressions += ["0 as days", "null as first_dt", "null as last_dt"]
        if "run_ts" in columns:
            expressions.append("count(distinct run_ts) as runs")
        else:
            expressions.append("0 as runs")
        result = data.q(
            f"select {', '.join(expressions)} from read_parquet('{glob}', union_by_name=true)"
        ).df().iloc[0]
        return base | {
            "status": "observed" if int(result["rows"]) > 0 else "empty",
            "rows": int(result["rows"]),
            "days": int(result["days"]),
            "runs": int(result["runs"]),
            "first_dt": result["first_dt"],
            "last_dt": result["last_dt"],
            "n_columns": int(len(columns)),
        }
    except Exception as exc:
        return base | {
            "status": "not_collected",
            "rows": 0,
            "days": 0,
            "runs": 0,
            "first_dt": None,
            "last_dt": None,
            "n_columns": 0,
            "error": str(exc)[:180],
        }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    frame = pd.DataFrame([inventory_row(*spec) for spec in TABLES])
    save(frame, out_dir, "wcv0_data_inventory")
    public = frame[frame["role"].str.startswith("public")]
    owned = frame[frame["role"].str.contains("owned|randomized|delivered", regex=True)]
    summary = {
        "evidence_status": "data_audit",
        "tables_observed": int((frame["status"] == "observed").sum()),
        "tables_not_collected": int((frame["status"] == "not_collected").sum()),
        "public_panel_max_days": int(public["days"].max()) if len(public) else 0,
        "owned_rows": int(owned["rows"].sum()) if len(owned) else 0,
        "inventory": frame.to_dict("records"),
        "claim_boundary": (
            "Rows and dates establish coverage, not independence, causal variation, correctness, "
            "or representativeness. HF is the authoritative store; local files are outputs only."
        ),
    }
    save_json(summary, out_dir, "wcv0_summary")
    return summary
