"""H88 — outcome-masked randomized public-enforcement policy trial."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ..capture_enforcement_policy_probes import POLICIES, STUDY_ID
from . import data
from . import h87_capacity_policy_trial as h87
from .common import DEFAULT_OUT, save, save_json

INTERNAL_POLICIES = ("capacity_safe", "capacity_risky", "openrouter_default")
TO_INTERNAL = dict(zip(POLICIES, INTERNAL_POLICIES, strict=True))
FROM_INTERNAL = dict(zip(INTERNAL_POLICIES, POLICIES, strict=True))
DEFAULT_RELEASE_REQUIREMENTS = dict(h87.DEFAULT_RELEASE_REQUIREMENTS)


def _internal_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if out.empty:
        return out
    if "assignment" in out:
        out["assignment"] = out["assignment"].replace(TO_INTERNAL)
    if "enforcement_stress_gap" in out:
        out["capacity_risk_gap"] = out["enforcement_stress_gap"]
    return out


def _internal_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if out.empty or "study_id" not in out or "policy" not in out:
        return out
    current = out["study_id"].astype(str).eq(STUDY_ID)
    out.loc[current, "policy"] = out.loc[current, "policy"].replace(TO_INTERNAL)
    return out


def _external_support(support: dict[str, Any]) -> dict[str, Any]:
    out = dict(support)
    counts = support.get("assignment_counts", {})
    out["assignment_counts"] = {
        policy: int(counts.get(TO_INTERNAL[policy], 0)) for policy in POLICIES
    }
    choice_state = dict(support.get("choice_state", {}))
    if "median_capacity_risk_gap" in choice_state:
        choice_state["median_enforcement_stress_gap"] = choice_state.pop("median_capacity_risk_gap")
    out["choice_state"] = choice_state
    return out


def _external_results(
    result: dict[str, Any], contrasts: pd.DataFrame
) -> tuple[dict[str, Any], pd.DataFrame]:
    out = dict(result)
    arm_outcomes = []
    for row in result["arm_outcomes"]:
        external = dict(row)
        external["policy"] = FROM_INTERNAL.get(str(row["policy"]), row["policy"])
        arm_outcomes.append(external)
    contrast_rows = []
    for row in result["primary_contrasts"]:
        external = dict(row)
        external["arm_a"] = FROM_INTERNAL.get(str(row["arm_a"]), row["arm_a"])
        external["arm_b"] = FROM_INTERNAL.get(str(row["arm_b"]), row["arm_b"])
        external["comparison"] = f"{external['arm_a']}_minus_{external['arm_b']}"
        contrast_rows.append(external)
    out["arm_outcomes"] = arm_outcomes
    out["primary_contrasts"] = contrast_rows
    external_contrasts = contrasts.copy()
    if not external_contrasts.empty:
        external_contrasts["arm_a"] = external_contrasts["arm_a"].replace(FROM_INTERNAL)
        external_contrasts["arm_b"] = external_contrasts["arm_b"].replace(FROM_INTERNAL)
        external_contrasts["comparison"] = (
            external_contrasts["arm_a"].astype(str)
            + "_minus_"
            + external_contrasts["arm_b"].astype(str)
        )
    return out, external_contrasts


def plot_released(result: dict[str, Any], contrasts: pd.DataFrame, out_dir: Path) -> None:
    arms = pd.DataFrame(result["arm_outcomes"]).set_index("policy").reindex(POLICIES)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    axes[0].bar(
        range(len(arms)),
        arms["success_rate"],
        color=["#4c956c", "#c14953", "#33658a"],
    )
    axes[0].set_xticks(range(len(arms)), ["enforcement safe", "enforcement risky", "default"])
    axes[0].set_ylabel("Success rate")
    axes[0].set_ylim(0, 1)
    axes[0].set_title("H88 randomized first-and-only probes")
    means = contrasts["mean"].to_numpy(float)
    lower = means - contrasts["ci95"].map(lambda value: value[0]).to_numpy(float)
    upper = contrasts["ci95"].map(lambda value: value[1]).to_numpy(float) - means
    axes[1].errorbar(range(len(contrasts)), means, yerr=[lower, upper], fmt="o", capsize=5)
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_xticks(range(len(contrasts)), ["safe - risky", "default - safe"])
    axes[1].set_ylabel("Success difference")
    axes[1].set_title("Primary effects (95% cluster CI)")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h88_enforcement_policy_trial.png", dpi=180)
    fig.savefig(out_dir / "h88_enforcement_policy_trial.pdf")
    plt.close(fig)


def plot_support(rows: pd.DataFrame, out_dir: Path) -> None:
    """Render only public candidate state and assignment support."""
    if rows.empty or "eligible_pair" not in rows:
        return
    eligible = rows[rows["eligible_pair"].fillna(False).astype(bool)].copy()
    if eligible.empty:
        return
    colors = {
        "enforcement_safe": "#4c956c",
        "enforcement_risky": "#c14953",
        "openrouter_default": "#33658a",
    }
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for policy in POLICIES:
        arm = eligible[eligible["assignment"].eq(policy)]
        axes[0].scatter(
            arm["price_ratio"],
            arm["enforcement_stress_gap"],
            label=policy.replace("_", " "),
            color=colors[policy],
            s=48,
        )
    axes[0].axvline(1.25, color="black", linestyle="--", linewidth=0.8)
    axes[0].set_xlabel("Higher / lower completion price")
    axes[0].set_ylabel("Public enforcement-stress gap")
    axes[0].set_title("Eligible H88 candidate pairs")
    axes[0].legend(frameon=False, fontsize=8)
    counts = eligible["assignment"].value_counts().reindex(POLICIES, fill_value=0)
    axes[1].bar(
        range(len(counts)),
        counts,
        color=[colors[policy] for policy in POLICIES],
    )
    axes[1].set_xticks(range(len(counts)), ["safe", "risky", "default"])
    axes[1].set_ylabel("Assignments sent")
    axes[1].set_title("Outcome-masked enrollment")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h88_enforcement_policy_support.png", dpi=180)
    fig.savefig(out_dir / "h88_enforcement_policy_support.pdf")
    plt.close(fig)


def analyze(
    candidates: pd.DataFrame,
    h88_attempts: pd.DataFrame,
    all_attempts: pd.DataFrame,
    out_dir: Path | None = None,
    *,
    requirements: dict[str, Any] = DEFAULT_RELEASE_REQUIREMENTS,
    bootstrap_draws: int = h87.BOOTSTRAP_DRAWS,
    randomization_draws: int = h87.RANDOMIZATION_DRAWS,
) -> dict[str, Any]:
    """Analyze H88 while preserving H87's already-tested randomization engine."""
    internal_candidates = _internal_candidates(candidates)
    internal_h88_attempts = _internal_attempts(h88_attempts)
    internal_all_attempts = _internal_attempts(all_attempts)
    original_study_id = h87.STUDY_ID
    h87.STUDY_ID = STUDY_ID
    try:
        prepared = h87.prepare_candidates(internal_candidates)
        ledger = h87.assignment_ledger(prepared, internal_h88_attempts, internal_all_attempts)
        internal_support = h87.support_summary(ledger)
        cutoff = h87.first_release_cutoff(ledger, requirements)
        support = _external_support(internal_support)
        summary: dict[str, Any] = {
            "evidence_status": (
                "prospective_randomized_enforcement_policy_released"
                if cutoff is not None
                else "prospective_randomized_enforcement_policy_power_gated"
            ),
            "preregistration": "docs/h86-h87-capacity-state-execution-preregistration.md",
            "study_id": STUDY_ID,
            "outcomes_released": cutoff is not None,
            "release_cutoff": str(cutoff) if cutoff is not None else None,
            "support": support,
            "sample_release_requirements": requirements,
            "claim_boundary": (
                "H88 identifies owned-probe routing-policy effects for providers selected "
                "using contemporaneous public admission/enforcement stress. It does not "
                "identify physical capacity, provider intent, literal front-running, "
                "other-user welfare, or a collateralized commitment effect."
            ),
        }
        if out_dir is not None:
            support_frame = ledger.copy()
            if "assignment" in support_frame:
                support_frame["assignment"] = support_frame["assignment"].replace(FROM_INTERNAL)
            if "capacity_risk_gap" in support_frame:
                support_frame["enforcement_stress_gap"] = support_frame["capacity_risk_gap"]
            support_columns = [
                "study_id",
                "run_ts",
                "block_id",
                "model_id",
                "canonical_slug",
                "candidate_ts",
                "assignment",
                "assignment_probability",
                "safe_provider",
                "risky_provider",
                "safe_enforcement_stress",
                "risky_enforcement_stress",
                "enforcement_stress_gap",
                "price_ratio",
                "eligible_pair",
                "request_sent",
                "exclusion_reason",
                "seed_replay_pass",
                "cross_study_overlap",
                "attempt_present",
                "treatment_compliant",
                "valid_assignment",
            ]
            support_export = support_frame[
                [column for column in support_columns if column in support_frame]
            ]
            save(support_export, out_dir, "h88_assignment_support")
            plot_support(support_export, out_dir)
        if cutoff is not None:
            released = ledger[
                ledger["valid_assignment"].astype(bool) & ledger["candidate_ts"].le(cutoff)
            ].copy()
            internal_result, internal_contrasts = h87.released_results(
                released,
                bootstrap_draws=bootstrap_draws,
                randomization_draws=randomization_draws,
            )
            result, contrasts = _external_results(internal_result, internal_contrasts)
            summary["released_results"] = result
            if out_dir is not None:
                released["assignment"] = released["assignment"].replace(FROM_INTERNAL)
                if "capacity_risk_gap" in released:
                    released["enforcement_stress_gap"] = released["capacity_risk_gap"]
                save(released, out_dir, "h88_released_trial_rows")
                save(contrasts, out_dir, "h88_primary_contrasts")
                plot_released(result, contrasts, out_dir)
        if out_dir is not None:
            save_json(summary, out_dir, "h88_summary")
        return summary
    finally:
        h87.STUDY_ID = original_study_id


def _load_table(name: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select * from read_parquet('{data.table_glob(name)}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    candidates = _load_table("h88_enforcement_policy_candidates")
    all_attempts = _load_table("router_route_attempts")
    h88_attempts = (
        all_attempts[all_attempts["study_id"].astype(str).eq(STUDY_ID)].copy()
        if not all_attempts.empty and "study_id" in all_attempts
        else all_attempts
    )
    return analyze(candidates, h88_attempts, all_attempts, out_dir)
