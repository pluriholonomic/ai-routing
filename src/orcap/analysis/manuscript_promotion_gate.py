"""Outcome-free promotion gate for the empirical microstructure manuscript.

The reviewed paper has two mechanical confirmatory gates:

1. 500 assignment-verified first-position observations in every H80 arm.
2. 30 distinct five-minute quote-panel dates, with the original nine-day and
   earliest 30-day vintages re-estimated side by side.

This module publishes only assignment and calendar support before those gates.
It never reads H80 response, latency, provider-selection, or cost fields.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json
from .h80_matched_quote_firmness import (
    MIN_FIRST_POSITION_PER_POLICY,
    construct_randomized_assignment_blocks,
    randomized_gate_audit,
)

QUOTE_PANEL_TARGET_DAYS = 30
FROZEN_VINTAGE_DAYS = 9
REQUIRED_DUAL_VINTAGE_ANALYSES = (
    "pm1_hazard_baseline",
    "bm1_pricing_technology",
    "bm2_fast_slow_reactions",
    "bm3_quality_adjusted_premium",
    "bm4_reaction_rules",
)
REQUIRED_TEMPORAL_VALIDATIONS = ("pm1_temporal_validation",)


def _dates(values: Iterable[Any]) -> list[str]:
    parsed = pd.to_datetime(pd.Series(list(values)), errors="coerce", utc=True).dropna()
    return sorted(parsed.dt.strftime("%Y-%m-%d").unique().tolist())


def build_promotion_status(
    endpoint_dates: Iterable[Any],
    h80_audit: dict[str, Any],
    *,
    quote_target_days: int = QUOTE_PANEL_TARGET_DAYS,
    frozen_vintage_days: int = FROZEN_VINTAGE_DAYS,
) -> dict[str, Any]:
    """Combine quote-calendar and H80 assignment support without outcomes."""
    dates = _dates(endpoint_dates)
    quote_ready = len(dates) >= quote_target_days
    frozen_dates = dates[:frozen_vintage_days]
    confirmatory_dates = dates[:quote_target_days] if quote_ready else []
    first_counts = {
        str(policy): int(value)
        for policy, value in (h80_audit.get("first_position_counts") or {}).items()
    }
    h80_target = int(
        h80_audit.get("target_per_policy", MIN_FIRST_POSITION_PER_POLICY)
    )
    h80_ready = bool(h80_audit.get("outcomes_released")) and bool(first_counts)
    all_ready = quote_ready and h80_ready
    return {
        "evidence_status": "confirmatory_release_ready" if all_ready else "accruing",
        "all_promotion_gates_ready": all_ready,
        "quote_panel_gate": {
            "ready": quote_ready,
            "observed_distinct_days": len(dates),
            "target_distinct_days": int(quote_target_days),
            "remaining_distinct_days": max(0, int(quote_target_days - len(dates))),
            "first_observed_date": dates[0] if dates else None,
            "latest_observed_date": dates[-1] if dates else None,
            "frozen_vintage": {
                "days": frozen_dates,
                "start": frozen_dates[0] if frozen_dates else None,
                "end": frozen_dates[-1] if frozen_dates else None,
                "complete": len(frozen_dates) == frozen_vintage_days,
            },
            "confirmatory_vintage": {
                "days": confirmatory_dates,
                "start": confirmatory_dates[0] if confirmatory_dates else None,
                "end": confirmatory_dates[-1] if confirmatory_dates else None,
                "complete": quote_ready,
            },
            "required_side_by_side_analyses": list(REQUIRED_DUAL_VINTAGE_ANALYSES),
            "required_temporal_validations": list(REQUIRED_TEMPORAL_VALIDATIONS),
            "freeze_rule": (
                "Use the earliest observed nine-day prefix and earliest observed 30-day "
                "prefix; later dates belong to a continuation vintage."
            ),
        },
        "h80_first_position_gate": {
            "ready": h80_ready,
            "counts": first_counts,
            "target_per_policy": h80_target,
            "min_count": min(first_counts.values()) if first_counts else 0,
            "remaining_by_policy": {
                policy: max(0, h80_target - count) for policy, count in first_counts.items()
            },
            "assignment_replay_rate": h80_audit.get("assignment_replay_rate"),
            "confirmatory_cutoff": h80_audit.get("confirmatory_cutoff"),
            "outcome_access": h80_audit.get("outcome_access"),
            "accrual_projection": h80_audit.get("accrual_projection"),
            "freeze_rule": (
                "Use the earliest chronological assignment-verified prefix whose four arm "
                "counts each reach 500; later rows belong to a continuation sample."
            ),
        },
        "release_contract": {
            "outcomes_before_gate": "forbidden in promotion artifacts",
            "required_when_ready": [
                "Holm-adjusted one-sided randomization tests for three default-pinned contrasts",
                "first-position HT and Hajek estimates with assignment replay",
                "cheapest-second-random rank-gradient test",
                "nine-day and 30-day pricing tables in the same release",
                "leakage-free PM1 15-day/15-day temporal holdout",
                "updated source manifest, manuscript estimates, rendered PDF, and reviewer audit",
            ],
            "sign_flip_rule": (
                "Any reversal of the default-firmness or administered-menu signs reopens review."
            ),
        },
        "claim_boundary": (
            "This artifact proves collection and assignment support only. It contains no "
            "pre-gate H80 outcome estimate and does not promote the 10-day pricing panel."
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    endpoint_dates = data.q(
        f"""
        select distinct cast(dt as varchar) as dt
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        order by 1
        """
    ).df()["dt"].tolist()
    attempts = data.q(
        f"""
        select *
        from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
        """
    ).df()
    assignment_blocks = construct_randomized_assignment_blocks(attempts)
    h80_audit = randomized_gate_audit(assignment_blocks)
    summary = build_promotion_status(endpoint_dates, h80_audit)
    save_json(summary, out_dir, "manuscript_promotion_gate_summary")
    return summary
