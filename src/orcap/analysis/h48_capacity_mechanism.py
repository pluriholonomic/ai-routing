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
MIN_CAPACITY_PROCUREMENT_COMMITMENTS = 100
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
        glob = data.table_glob("router_capacity_commitments")
        rows = data.q(
            f"""
            select count(*) as commitments,
                   count(distinct provider) as providers,
                   count(distinct model_id) as models,
                   count(distinct study_id) as studies,
                   count(verification_method) as verification_method_observed,
                   count(marginal_cost_usd_per_request) as marginal_cost_observed,
                   sum(committed_requests) as committed_requests
            from read_parquet('{glob}', union_by_name=true)
            """
        ).fetchone()
        result = {
            "commitments": int(rows[0]),
            "providers": int(rows[1]),
            "models": int(rows[2]),
            "studies": int(rows[3]),
            "verification_method_observed": int(rows[4]),
            "marginal_cost_observed": int(rows[5]),
            "committed_requests": float(rows[6] or 0.0),
            "capacity_linear_cost_observed": 0,
            "capacity_cost_curvature_observed": 0,
        }
        schema = data.q(
            f"describe select * from read_parquet('{glob}', union_by_name=true)"
        ).df()
        columns = set(schema["column_name"])
        if {
            "capacity_linear_cost_usd_per_request",
            "capacity_cost_curvature_usd_per_request_sq",
        }.issubset(columns):
            cost_rows = data.q(
                f"""
                select count(capacity_linear_cost_usd_per_request),
                       count(capacity_cost_curvature_usd_per_request_sq)
                from read_parquet('{glob}', union_by_name=true)
                """
            ).fetchone()
            result["capacity_linear_cost_observed"] = int(cost_rows[0])
            result["capacity_cost_curvature_observed"] = int(cost_rows[1])
        return result
    except Exception:
        return {
            "commitments": 0,
            "providers": 0,
            "models": 0,
            "studies": 0,
            "verification_method_observed": 0,
            "marginal_cost_observed": 0,
            "committed_requests": 0.0,
            "capacity_linear_cost_observed": 0,
            "capacity_cost_curvature_observed": 0,
        }


def _outcome_coverage() -> dict:
    """Summarize redacted allocated/served epoch aggregates when present."""
    try:
        rows = data.q(
            f"""
            with latest as (
                select *, row_number() over (
                    partition by outcome_id order by run_ts desc
                ) as recency_rank
                from read_parquet('{data.table_glob("router_capacity_epoch_outcomes")}')
            )
            select count(*) as outcomes,
                   count(distinct provider) as providers,
                   count(distinct model_id) as models,
                   count(distinct study_id) as studies,
                   sum(allocated_requests) as allocated_requests,
                   sum(served_requests) as served_requests,
                   sum(shortfall_requests) as shortfall_requests,
                   count(realized_cost_usd) as realized_cost_observed,
                   count(realized_revenue_usd) as realized_revenue_observed
            from latest
            where recency_rank = 1
            """
        ).fetchone()
        return {
            "outcomes": int(rows[0]),
            "providers": int(rows[1]),
            "models": int(rows[2]),
            "studies": int(rows[3]),
            "allocated_requests": float(rows[4] or 0.0),
            "served_requests": float(rows[5] or 0.0),
            "shortfall_requests": float(rows[6] or 0.0),
            "realized_cost_observed": int(rows[7]),
            "realized_revenue_observed": int(rows[8]),
        }
    except Exception:
        return {
            "outcomes": 0,
            "providers": 0,
            "models": 0,
            "studies": 0,
            "allocated_requests": 0.0,
            "served_requests": 0.0,
            "shortfall_requests": 0.0,
            "realized_cost_observed": 0,
            "realized_revenue_observed": 0,
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


def _matched_commitment_outcome_coverage() -> dict:
    """Match commitments to epoch outcomes on their full controlled-study key."""
    try:
        rows = data.q(
            f"""
            with commitments as (
                select *, row_number() over (
                    partition by commitment_id order by run_ts desc
                ) as recency_rank
                from read_parquet('{data.table_glob("router_capacity_commitments")}')
            ), outcomes as (
                select *, row_number() over (
                    partition by outcome_id order by run_ts desc
                ) as recency_rank
                from read_parquet('{data.table_glob("router_capacity_epoch_outcomes")}')
            ), matched as (
                select o.*
                from outcomes o
                where o.recency_rank = 1
                  and exists (
                      select 1
                      from commitments c
                      where c.recency_rank = 1
                        and o.study_id = c.study_id
                        and o.provider = c.provider
                        and o.model_id = c.model_id
                        and o.epoch_start = c.epoch_start
                        and o.epoch_end = c.epoch_end
                  )
            )
            select count(*) as matched_outcomes,
                   count(distinct provider) as matched_providers,
                   sum(allocated_requests) as allocated_requests,
                   sum(served_requests) as served_requests,
                   sum(shortfall_requests) as shortfall_requests,
                   count(realized_cost_usd) as realized_cost_observed,
                   count(realized_revenue_usd) as realized_revenue_observed
            from matched
            """
        ).fetchone()
        return {
            "matched_outcomes": int(rows[0]),
            "matched_providers": int(rows[1]),
            "allocated_requests": float(rows[2] or 0.0),
            "served_requests": float(rows[3] or 0.0),
            "shortfall_requests": float(rows[4] or 0.0),
            "realized_cost_observed": int(rows[5]),
            "realized_revenue_observed": int(rows[6]),
        }
    except Exception:
        return {
            "matched_outcomes": 0,
            "matched_providers": 0,
            "allocated_requests": 0.0,
            "served_requests": 0.0,
            "shortfall_requests": 0.0,
            "realized_cost_observed": 0,
            "realized_revenue_observed": 0,
        }


def _triple_matched_attempt_coverage() -> dict:
    """Count attempts in an epoch having both a commitment and outcome.

    This avoids treating an attempt-to-commitment match in one epoch and a
    commitment-to-outcome match in another as if they identified the same
    controlled study observation.
    """
    try:
        rows = data.q(
            f"""
            with attempts as (
                select event_id, study_id, model_id, selected_provider as provider,
                       try_cast(observed_at as timestamptz) as observed_at,
                       outcome, cost_usd
                from read_parquet('{data.table_glob("router_route_attempts")}')
                where selected_provider is not null
            ), commitments as (
                select *, row_number() over (
                    partition by commitment_id order by run_ts desc
                ) as recency_rank
                from read_parquet('{data.table_glob("router_capacity_commitments")}')
            ), outcomes as (
                select *, row_number() over (
                    partition by outcome_id order by run_ts desc
                ) as recency_rank
                from read_parquet('{data.table_glob("router_capacity_epoch_outcomes")}')
            ), matched_epochs as (
                select c.study_id, c.provider, c.model_id,
                       try_cast(c.epoch_start as timestamptz) as epoch_start,
                       try_cast(c.epoch_end as timestamptz) as epoch_end
                from commitments c
                where c.recency_rank = 1
                  and exists (
                      select 1
                      from outcomes o
                      where o.recency_rank = 1
                        and o.study_id = c.study_id
                        and o.provider = c.provider
                        and o.model_id = c.model_id
                        and o.epoch_start = c.epoch_start
                        and o.epoch_end = c.epoch_end
                  )
            ), matched as (
                select a.*
                from attempts a
                where exists (
                    select 1
                    from matched_epochs m
                    where a.study_id = m.study_id
                      and a.provider = m.provider
                      and a.model_id = m.model_id
                      and a.observed_at >= m.epoch_start
                      and a.observed_at < m.epoch_end
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


def enforcement_gate(
    attempts: dict,
    commitments: dict,
    outcomes: dict,
    matched_outcomes: dict,
    triple_matched_attempts: dict,
) -> dict:
    """Expose what remains unidentified for capacity/bond counterfactuals."""
    if not attempts["attempts"] or not commitments["commitments"] or not outcomes["outcomes"]:
        status = "not_identified"
    elif (
        not matched_outcomes["matched_outcomes"]
        or not triple_matched_attempts["matched_attempts"]
    ):
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
            "selected_attempts": triple_matched_attempts["matched_attempts"],
            "succeeded_attempts": triple_matched_attempts["served_observed"],
            "allocated_requests": matched_outcomes["allocated_requests"],
            "served_requests": matched_outcomes["served_requests"],
            "shortfall_requests": matched_outcomes["shortfall_requests"],
            "realized_attempt_cost_observed": triple_matched_attempts[
                "realized_cost_observed"
            ],
            "realized_epoch_cost_observed": matched_outcomes["realized_cost_observed"],
            "realized_epoch_revenue_observed": matched_outcomes["realized_revenue_observed"],
        },
        "not_established_by_this_contract": [
            "market-wide allocation or demand",
            "delivered capacity beyond a route-attempt outcome",
            "causal effect of commitment on routing",
            "optimal bond or welfare claim",
        ],
    }


def capacity_procurement_gate(commitments: dict) -> dict:
    """Expose whether the convex capacity-cost type is empirically observed."""
    observed = min(
        commitments["capacity_linear_cost_observed"],
        commitments["capacity_cost_curvature_observed"],
    )
    if not commitments["commitments"]:
        status = "not_identified"
    elif not observed:
        status = "cost_type_unobserved"
    elif observed < MIN_CAPACITY_PROCUREMENT_COMMITMENTS:
        status = "power_gated"
    else:
        status = "declared_cost_type_coverage"
    return {
        "status": status,
        "declared_linear_cost_rows": commitments["capacity_linear_cost_observed"],
        "declared_curvature_rows": commitments["capacity_cost_curvature_observed"],
        "minimum_declared_cost_rows": MIN_CAPACITY_PROCUREMENT_COMMITMENTS,
        "claim_boundary": (
            "Declared reservation-cost fields support only a controlled-study calibration input. "
            "They do not verify private cost, physical capacity, reliability, welfare, or a "
            "budget-balanced mechanism."
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = allocation_calibration(_load_public_simulation())
    attempts = _owned_attempt_coverage()
    commitments = _commitment_coverage()
    outcomes = _outcome_coverage()
    matched_attempts = _matched_attempt_commitment_coverage()
    matched_outcomes = _matched_commitment_outcome_coverage()
    triple_matched_attempts = _triple_matched_attempt_coverage()
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
        "capacity_outcome_coverage": outcomes,
        "matched_attempt_commitment_coverage": matched_attempts,
        "matched_commitment_outcome_coverage": matched_outcomes,
        "triple_matched_attempt_coverage": triple_matched_attempts,
        "enforcement_gate": enforcement_gate(
            attempts,
            commitments,
            outcomes,
            matched_outcomes,
            triple_matched_attempts,
        ),
        "capacity_procurement_gate": capacity_procurement_gate(commitments),
        "claim_boundary": (
            "The allocation-price elasticity is algebra implied by the disclosed inverse-square "
            "proxy. It is not an estimated realized router elasticity, an optimal mechanism, or "
            "evidence that providers currently post capacity bonds."
        ),
    }
    save_json(result, out_dir, "h48_summary")
    return result
