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


def _commitment_coverage() -> dict:
    """Summarize controlled commitments without treating them as capacity proof.

    Public panels do not expose provider commitments. This table is populated
    only by a redacted owner export, so a non-zero row count is evidence of a
    declared commitment, not evidence that the capacity was delivered.
    """
    try:
        rows = data.q(
            f"""
            select count(*) as commitments,
                   count(distinct provider) as providers,
                   count(distinct model_id) as models,
                   count(distinct study_id) as studies,
                   count(verification_method) as verification_method_observed,
                   count(marginal_cost_usd_per_request) as marginal_cost_observed,
                   sum(committed_requests) as committed_requests
            from read_parquet('{data.table_glob("router_capacity_commitments")}')
            """
        ).fetchone()
        return {
            "commitments": int(rows[0]),
            "providers": int(rows[1]),
            "models": int(rows[2]),
            "studies": int(rows[3]),
            "verification_method_observed": int(rows[4]),
            "marginal_cost_observed": int(rows[5]),
            "committed_requests": float(rows[6] or 0.0),
        }
    except Exception:
        return {
            "commitments": 0,
            "providers": 0,
            "models": 0,
            "studies": 0,
            "verification_method_observed": 0,
            "marginal_cost_observed": 0,
            "committed_requests": 0.0,
        }


def _matched_attempt_commitment_coverage() -> dict:
    """Count selected attempts matched to the same provider/model/study epoch.

    The match identifies the data needed for a *controlled-study*
    counterfactual. It does not establish a router's market-wide allocation,
    delivered capacity, or causal effect of a commitment.
    """
    try:
        rows = data.q(
            f"""
            with attempts as (
                select source, event_id, study_id, model_id, selected_provider as provider,
                       try_cast(observed_at as timestamptz) as observed_at,
                       outcome, cost_usd
                from read_parquet('{data.table_glob("router_route_attempts")}')
                where selected_provider is not null
            ), commitments as (
                select study_id, model_id, provider,
                       try_cast(epoch_start as timestamptz) as epoch_start,
                       try_cast(epoch_end as timestamptz) as epoch_end,
                       verification_method, marginal_cost_usd_per_request
                from read_parquet('{data.table_glob("router_capacity_commitments")}')
            ), matched as (
                select a.*
                from attempts a
                where exists (
                    select 1
                    from commitments c
                    where a.study_id = c.study_id
                      and a.model_id = c.model_id
                      and a.provider = c.provider
                      and a.observed_at >= c.epoch_start
                      and a.observed_at < c.epoch_end
                )
            )
            select count(*) as matched_attempts,
                   count(distinct provider) as matched_providers,
                   count(distinct model_id) as matched_models,
                   count(distinct study_id) as matched_studies,
                   count(case when outcome = 'succeeded' then 1 end) as served_observed,
                   count(cost_usd) as realized_cost_observed
            from matched
            """
        ).fetchone()
        return {
            "matched_attempts": int(rows[0]),
            "matched_providers": int(rows[1]),
            "matched_models": int(rows[2]),
            "matched_studies": int(rows[3]),
            "served_observed": int(rows[4]),
            "realized_cost_observed": int(rows[5]),
        }
    except Exception:
        return {
            "matched_attempts": 0,
            "matched_providers": 0,
            "matched_models": 0,
            "matched_studies": 0,
            "served_observed": 0,
            "realized_cost_observed": 0,
        }


def enforcement_gate(attempts: dict, commitments: dict, matched: dict) -> dict:
    """Expose what remains unidentified for capacity/bond counterfactuals."""
    if not attempts["attempts"] or not commitments["commitments"]:
        status = "not_identified"
    elif not matched["matched_attempts"]:
        status = "unmatched_owned_telemetry"
    else:
        status = "partial_owned_telemetry"
    return {
        "status": status,
        "required_for_capacity_bond_calibration": [
            "provider/model/time capacity commitment",
            "allocated and served request counts",
            "redacted selected-provider route attempts",
            "realized serving cost or contribution margin",
        ],
        "identified_in_matched_controlled_study": {
            "selected_attempts": matched["matched_attempts"],
            "succeeded_attempts": matched["served_observed"],
            "realized_cost_observed": matched["realized_cost_observed"],
        },
        "not_established_by_this_contract": [
            "market-wide allocation or demand",
            "delivered capacity beyond a route-attempt outcome",
            "causal effect of commitment on routing",
            "optimal bond or welfare claim",
        ],
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = allocation_calibration(_load_public_simulation())
    attempts = _owned_attempt_coverage()
    commitments = _commitment_coverage()
    matched = _matched_attempt_commitment_coverage()
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
        "capacity_commitment_coverage": commitments,
        "matched_attempt_commitment_coverage": matched,
        "enforcement_gate": enforcement_gate(attempts, commitments, matched),
        "claim_boundary": (
            "The allocation-price elasticity is algebra implied by the disclosed inverse-square "
            "proxy. It is not an estimated realized router elasticity, an optimal mechanism, or "
            "evidence that providers currently post capacity bonds."
        ),
    }
    save_json(result, out_dir, "h48_summary")
    return result
