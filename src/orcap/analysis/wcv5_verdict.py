"""WCV5 — conservative verdict for the integrated experimental program."""

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


def conjecture_verdict(conditions: list[dict], randomized_ready: bool) -> str:
    statuses = {row.get("status") for row in conditions}
    if conditions and statuses == {"supported_in_study_domain"} and randomized_ready:
        return "supported_in_study_domain"
    if "inconsistent_with_condition" in statuses:
        return "decentralization_conditions_not_satisfied"
    return "not_identified"


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    wcv1 = _read(out_dir, "wcv1_summary")
    wcv2 = _read(out_dir, "wcv2_summary")
    wcv3 = _read(out_dir, "wcv3_summary")
    wcv4 = _read(out_dir, "wcv4_summary")
    bm5 = _read(out_dir, "bm5_summary")
    h4 = _read(out_dir, "h4_summary")
    h11 = _read(out_dir, "h11_summary")
    h48 = _read(out_dir, "h48_summary")
    h54 = _read(out_dir, "h54_summary")
    h69 = _read(out_dir, "h69_summary")
    conditions = wcv1.get("conditions", [])
    randomized_ready = bool(wcv4.get("randomized_h50_ready"))
    full = conjecture_verdict(conditions, randomized_ready)
    elasticity = h4.get("share_price_elasticity")
    se = h4.get("se")
    z_inverse_square = (
        (elasticity + 2.0) / se if elasticity is not None and se not in (None, 0) else None
    )
    naive_score = (
        "rejected"
        if z_inverse_square is not None and abs(z_inverse_square) > 1.96
        else "not_identified"
    )
    quality_share = h11.get("hedonic", {}).get(
        "within_model_var_explained_by_delivered_quality"
    )
    lemons_p = h11.get("lemons", {}).get("pvalue")
    price_score_verdict = (
        "rejected"
        if lemons_p is not None and lemons_p < 0.05
        else ("provisional_contrary_evidence" if quality_share is not None else "not_identified")
    )
    rows = [
        {
            "claim": "public inverse-square routing is the realized allocation rule",
            "verdict": naive_score,
            "reason": (
                f"H4 elasticity z versus -2 = {z_inverse_square:.2f}"
                if z_inverse_square
                else "missing H4"
            ),
        },
        {
            "claim": "price is a sufficient routing/welfare score",
            "verdict": price_score_verdict,
            "reason": (
                f"delivered quality explains {100 * quality_share:.1f}% of residual within-model "
                f"price variation; cheap-bad p={lemons_p:.3f}"
                if quality_share is not None and lemons_p is not None
                else "H11 quality panel is incomplete"
            ),
        },
        {
            "claim": "Brown-MacKay is the preferred competitive pricing null",
            "verdict": bm5.get("evidence_status", "not_estimated"),
            "reason": (
                "requires temporal holdout gain plus cadence premium and reaction predictions"
            ),
        },
        {
            "claim": "capacity-certified routing improves welfare",
            "verdict": h48.get("evidence_status", "not_identified"),
            "reason": "requires valid commitments, outcomes, costs, and randomized assignments",
        },
        {
            "claim": "fidelity monitoring is adequate",
            "verdict": h54.get("evidence_status", "not_identified"),
            "reason": "requires linked randomized reliability audits",
        },
        {
            "claim": "selfish optimization attains approximate global welfare",
            "verdict": full,
            "reason": "C1-C10 conjunction and causal policy comparison are required",
        },
    ]
    table = pd.DataFrame(rows)
    save(table, out_dir, "wcv5_verdict_table")
    summary = {
        "evidence_status": "final_audit",
        "full_conjecture_verdict": full,
        "naive_static_score_verdict": naive_score,
        "inverse_square_z": z_inverse_square,
        "brown_mackay_competitive_null": bm5.get("evidence_status", "not_estimated"),
        "condition_counts": wcv1.get("counts", {}),
        "randomized_policy_ready": randomized_ready,
        "sensitivity_analysis_ready": wcv2.get("evidence_status") == "sensitivity_analysis",
        "regret_screen_ready": wcv3.get("evidence_status") == "calibrated_regret_screen",
        "readiness_ledger_status": {
            "ready": h69.get("n_ready_gates", 0),
            "power_gated": h69.get("n_power_gated_gates", 0),
            "not_collected": h69.get("n_not_collected_gates", 0),
        },
        "verdicts": rows,
        "claim_boundary": (
            "Failure of observed decentralization conditions means the welfare conclusion is not "
            "licensed; it is not a structural estimate of welfare loss. Brown-MacKay can be a "
            "preferred competitive null without being causally confirmed."
        ),
    }
    save_json(summary, out_dir, "welfare_conjecture_verdict")
    save_json(summary, out_dir, "wcv5_summary")
    return summary
