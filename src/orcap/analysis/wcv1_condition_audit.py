"""WCV1 — evidence ledger for conditions C1-C10 of the conjecture."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .common import DEFAULT_OUT, save, save_json


def _read(out_dir: Path, name: str) -> dict:
    try:
        return json.loads((out_dir / f"{name}.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def condition_rows(summaries: dict[str, dict]) -> pd.DataFrame:
    h11 = summaries.get("h11_summary", {})
    h23 = summaries.get("h23_summary", {})
    h48 = summaries.get("h48_summary", {})
    h50 = summaries.get("h50_summary", {})
    h54 = summaries.get("h54_summary", {})
    h68 = summaries.get("h68_competition_summary", {})
    cbh14 = summaries.get("cbh14_summary", {})
    quality_p = h11.get("lemons", {}).get("pvalue")
    rows = [
        {
            "condition": "C1",
            "name": "tier prices equal congestion externality differences",
            "status": "not_identified",
            "evidence": "H14 observes tier shares but not value, priority, or marginal delay tolls",
            "blocking_data": (
                "tier-specific service order, willingness-to-pay, LRD delay externality"
            ),
        },
        {
            "condition": "C2",
            "name": "router objective aligns with aggregate user surplus",
            "status": (
                "supported_in_study_domain"
                if h50.get("evidence_status") == "supported_in_study_domain"
                else "not_identified"
            ),
            "evidence": "public elasticity is behavioral; only H50 can identify policy effects",
            "blocking_data": "randomized router assignments plus registered user-value outcome",
        },
        {
            "condition": "C3",
            "name": "no missing money for capacity",
            "status": (
                "approximately_consistent"
                if h48.get("capacity_commitment_coverage", {}).get("commitments", 0) > 0
                else "not_identified"
            ),
            "evidence": (
                "public capacity slack is consistent with adequacy, but H48 has no capacity "
                "commitments or cost curves"
            ),
            "blocking_data": "capacity cost curves, scarcity rents, commitment delivery outcomes",
        },
        {
            "condition": "C4",
            "name": "rationing is value ordered",
            "status": "approximately_consistent" if h23.get("n_days", 0) >= 28 else "power_gated",
            "evidence": (
                "tier-level and toxicity/rejection patterns are descriptive, not within-tier order"
            ),
            "blocking_data": "request value/tier and admission order during shared shortages",
        },
        {
            "condition": "C5",
            "name": "no pivotal provider",
            "status": (
                "approximately_consistent" if h68.get("n_models", 0) >= 100 else "power_gated"
            ),
            "evidence": (
                "multi-provider public quote competition is a proxy, not shortage-state pivotality"
            ),
            "blocking_data": (
                "realized eligibility sets and counterfactual shortfall without each provider"
            ),
        },
        {
            "condition": "C6",
            "name": "entry fixed-cost wedge is small",
            "status": "approximately_consistent" if cbh14 else "not_identified",
            "evidence": "entry scales weakly with token demand, consistent with cheap listing",
            "blocking_data": "provider fixed and capacity costs plus causal entry shocks",
        },
        {
            "condition": "C7",
            "name": "retry externality is internalized",
            "status": "inconsistent_with_condition",
            "evidence": (
                "market contracts do not price retries; telemetry does not yet quantify "
                "amplification"
            ),
            "blocking_data": (
                "attempt chains, retry policy, shortage state, and user-level arrival grouping"
            ),
        },
        {
            "condition": "C8",
            "name": "endpoint fidelity is monitored",
            "status": (
                "inconsistent_with_condition"
                if quality_p is not None and quality_p < 0.05
                else "power_gated"
            ),
            "evidence": (
                f"H11 cheap-bad association p={quality_p:.4g}; H54 audit status "
                f"{h54.get('evidence_status', 'not_run')}"
                if quality_p is not None
                else "quality audit missing"
            ),
            "blocking_data": "randomized fidelity audits linked to realized selections",
        },
        {
            "condition": "C9",
            "name": "no kickback steering and harnesses are wary",
            "status": "not_identified",
            "evidence": (
                "price parity cannot reveal provider-router compensation or hidden steering"
            ),
            "blocking_data": "rebates/commissions or a valid randomized steering instrument",
        },
        {
            "condition": "C10",
            "name": "no common pricing delegation",
            "status": "not_identified",
            "evidence": "BM cadence and reaction commonality do not reveal vendor identity",
            "blocking_data": "pricing-stack adoption dates or vendor-overlap disclosure",
        },
    ]
    return pd.DataFrame(rows)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    names = [
        "h11_summary",
        "h23_summary",
        "h48_summary",
        "h50_summary",
        "h54_summary",
        "h68_competition_summary",
        "cbh14_summary",
    ]
    summaries = {name: _read(out_dir, name) for name in names}
    frame = condition_rows(summaries)
    save(frame, out_dir, "wcv1_condition_audit")
    counts = frame["status"].value_counts().to_dict()
    summary = {
        "evidence_status": "condition_audit",
        "counts": {str(key): int(value) for key, value in counts.items()},
        "all_conditions_supported": bool((frame["status"] == "supported_in_study_domain").all()),
        "conditions": frame.to_dict("records"),
        "claim_boundary": (
            "A condition can be inconsistent with current evidence without proving the entire "
            "conjecture false. Unidentified conditions must never be silently treated as satisfied."
        ),
    }
    save_json(summary, out_dir, "wcv1_summary")
    return summary
