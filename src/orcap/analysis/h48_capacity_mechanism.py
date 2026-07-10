"""H48 — empirical calibration sheet for a capacity-certified routing mechanism.

H48 does not estimate an optimal mechanism. It maps the public OpenRouter
inverse-square allocation rule into the proposed mechanism's price incentive
and makes the unobserved enforcement inputs explicit: realized route attempts,
capacity commitments, shortfall, and cost/margin data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..mechanism import own_price_share_elasticity
from . import data
from .common import DEFAULT_OUT, save, save_json

ETA = 2.0
PANEL_COLUMNS = [
    "run_ts",
    "model_id",
    "scenario",
    "provider_name",
    "simulated_route_share",
    "expected_quote_usd",
    "mechanism_eta",
    "predicted_own_price_share_elasticity",
]


def allocation_calibration(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    panel = rows.copy()
    panel["simulated_route_share"] = pd.to_numeric(
        panel["simulated_route_share"], errors="coerce"
    )
    panel["expected_quote_usd"] = pd.to_numeric(panel["expected_quote_usd"], errors="coerce")
    panel = panel.dropna(subset=["simulated_route_share", "expected_quote_usd"])
    panel = panel[(panel["simulated_route_share"] >= 0) & (panel["expected_quote_usd"] > 0)]
    panel["mechanism_eta"] = ETA
    panel["predicted_own_price_share_elasticity"] = panel["simulated_route_share"].map(
        lambda share: own_price_share_elasticity(float(share), ETA)
    )
    return panel.loc[:, PANEL_COLUMNS].reset_index(drop=True)


def _load_public_simulation() -> pd.DataFrame:
    try:
        glob = data.table_glob("routing_simulation")
        return data.q(
            f"""
            with latest as (select max(run_ts) as run_ts from read_parquet('{glob}'))
            select source.run_ts, source.model_id, source.scenario, source.provider_name,
                   source.simulated_route_share, source.expected_quote_usd
            from read_parquet('{glob}') as source, latest
            where source.run_ts = latest.run_ts
            """
        ).df()
    except Exception:
        return pd.DataFrame()


def _owned_attempt_coverage() -> dict:
    try:
        rows = data.q(
            f"""
            select count(*) as attempts,
                   count(selected_provider) as selected_provider_observed,
                   count(cost_usd) as cost_observed
            from read_parquet('{data.table_glob("router_route_attempts")}')
            """
        ).fetchone()
        return {
            "attempts": int(rows[0]),
            "selected_provider_observed": int(rows[1]),
            "cost_observed": int(rows[2]),
        }
    except Exception:
        return {"attempts": 0, "selected_provider_observed": 0, "cost_observed": 0}


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = allocation_calibration(_load_public_simulation())
    attempts = _owned_attempt_coverage()
    save(panel, out_dir, "h48_capacity_mechanism_calibration")
    result = {
        "allocation_rule": "reliability_weighted_inverse_price",
        "eta": ETA,
        "calibrated_provider_rows": int(len(panel)),
        "median_predicted_own_price_share_elasticity": (
            float(panel["predicted_own_price_share_elasticity"].median())
            if not panel.empty
            else None
        ),
        "owned_attempt_coverage": attempts,
        "enforcement_gate": {
            "status": "not_identified" if not attempts["attempts"] else "partial_owned_telemetry",
            "required_for_capacity_bond_calibration": [
                "provider/model/time capacity commitment",
                "allocated and served request counts",
                "redacted selected-provider route attempts",
                "realized serving cost or contribution margin",
            ],
        },
        "claim_boundary": (
            "The allocation-price elasticity is algebra implied by the disclosed inverse-square "
            "proxy. It is not an estimated realized router elasticity, an optimal mechanism, or "
            "evidence that providers currently post capacity bonds."
        ),
    }
    save_json(result, out_dir, "h48_summary")
    return result
