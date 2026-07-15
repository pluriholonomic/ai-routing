"""H89 — outcome-masked randomized Hugging Face routing-policy trial."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..capture_hf_policy_probes import POLICIES, STUDY_ID
from . import data
from . import h87_capacity_policy_trial as h87
from .common import DEFAULT_OUT, save, save_json

RANDOM_SEED = 89_071_601
BOOTSTRAP_DRAWS = 10_000
RANDOMIZATION_DRAWS = 100_000
FAILURE_LATENCY_CAP_MS = 60_000.0
VALUE_OF_TIME_USD_PER_SECOND = 0.0001
FAILURE_PENALTY_USD = 0.01
DEFAULT_RELEASE_REQUIREMENTS = {
    "elapsed_hours": 72,
    "assignments_per_arm": 120,
    "models": 8,
    "candidate_providers": 5,
    "max_public_provider_dominance": 0.75,
    "min_treatment_compliance": 0.95,
    "require_seed_replay": True,
}


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        result = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return result if isinstance(result, dict) else {}


def prepare_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame[frame["study_id"].astype(str).eq(STUDY_ID)].copy()
    out = out.sort_values("run_ts").drop_duplicates("block_id", keep="last")
    out["candidate_ts"] = pd.to_datetime(
        out.get("request_observed_at", out.get("run_ts")), utc=True, errors="coerce"
    )
    for column in ["eligible_model", "request_sent"]:
        out[column] = out.get(column, False).fillna(False).astype(bool)
    out["assignment"] = out.get("assignment", pd.Series(pd.NA, index=out.index)).astype(
        "string"
    )

    def replay(row: pd.Series) -> bool:
        try:
            assignment = row["assignment"]
            return not pd.isna(assignment) and random.Random(int(row["block_seed"])).choice(
                POLICIES
            ) == str(assignment)
        except (KeyError, TypeError, ValueError):
            return False

    out["seed_replay_pass"] = out.apply(replay, axis=1)
    out["candidate_cluster"] = (
        out["model_id"].astype(str) + "|" + out["candidate_ts"].dt.strftime("%Y-%m-%d")
    )
    return out


def prepare_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame[frame["study_id"].astype(str).eq(STUDY_ID)].copy()
    metadata = out.get("metadata_json", pd.Series("{}", index=out.index)).map(_metadata)
    out["block_id"] = [item.get("block_id") for item in metadata]
    out["attempt_candidate_state_hash"] = [
        item.get("candidate_state_hash") for item in metadata
    ]
    out["attempt_requested_model_suffix"] = [
        item.get("requested_model_suffix") for item in metadata
    ]
    out["status_code"] = [item.get("status_code") for item in metadata]
    out["attempt_ts"] = pd.to_datetime(out.get("observed_at"), utc=True, errors="coerce")
    out["success"] = out["outcome"].astype(str).eq("succeeded")
    out["logged_cost_usd"] = pd.to_numeric(out.get("cost_usd"), errors="coerce")
    out["observed_latency_ms"] = pd.to_numeric(out.get("latency_ms"), errors="coerce")
    return out.sort_values("attempt_ts").drop_duplicates("block_id", keep="last")


def assignment_ledger(candidates: pd.DataFrame, attempts: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    attempt_rows = prepare_attempts(attempts)
    fields = [
        "block_id",
        "event_id",
        "attempt_ts",
        "requested_provider",
        "selected_provider",
        "policy",
        "attempt_candidate_state_hash",
        "attempt_requested_model_suffix",
        "status_code",
        "success",
        "logged_cost_usd",
        "observed_latency_ms",
        "outcome",
        "retry_reason",
    ]
    for column in fields:
        if column not in attempt_rows:
            attempt_rows[column] = pd.NA
    ledger = candidates.merge(
        attempt_rows[fields], on="block_id", how="left", validate="one_to_one"
    )
    ledger["attempt_present"] = ledger["event_id"].notna()
    expected_suffix = ledger["assigned_requested_model"].astype("string").str.rsplit(
        ":", n=1
    ).str[-1]
    payload_compliant = (
        ledger["policy"].astype("string").eq(ledger["assignment"])
        & ledger["attempt_candidate_state_hash"]
        .astype("string")
        .eq(ledger["candidate_state_hash"].astype("string"))
        & ledger["attempt_requested_model_suffix"].astype("string").eq(expected_suffix)
    ).fillna(False)
    pinned = ledger["assignment"].eq("public_cost_caliper").fillna(False)
    requested_compliant = (
        ~pinned
        | ledger["requested_provider"]
        .astype("string")
        .eq(ledger["assigned_requested_provider"].astype("string"))
    ).fillna(False)
    successful = ledger["success"].astype("boolean").fillna(False)
    selected_present = ledger["selected_provider"].notna()
    selected_pinned_compliant = (
        ~pinned
        | ~successful
        | ledger["selected_provider"]
        .astype("string")
        .eq(ledger["assigned_requested_provider"].astype("string"))
    ).fillna(False)
    ledger["treatment_compliant"] = (
        payload_compliant
        & requested_compliant
        & (~successful | selected_present)
        & selected_pinned_compliant
    )
    ledger["valid_assignment"] = (
        ledger["eligible_model"].astype("boolean").fillna(False)
        & ledger["request_sent"].astype("boolean").fillna(False)
        & ledger["attempt_present"].astype("boolean").fillna(False)
        & ledger["seed_replay_pass"].astype("boolean").fillna(False)
        & ledger["treatment_compliant"].astype("boolean").fillna(False)
    )
    return ledger


def support_summary(ledger: pd.DataFrame) -> dict[str, Any]:
    if ledger.empty:
        return {
            "candidate_rows": 0,
            "eligible_models": 0,
            "assignments_sent": 0,
            "valid_assignments": 0,
            "elapsed_hours": 0,
            "assignment_counts": {policy: 0 for policy in POLICIES},
            "models": 0,
            "candidate_providers": 0,
            "public_provider_dominance": None,
            "treatment_compliance": 0.0,
            "seed_replay_rate": 0.0,
            "latest_timestamp": None,
        }
    sent = ledger[
        ledger["eligible_model"].astype(bool) & ledger["request_sent"].astype(bool)
    ]
    valid = ledger[ledger["valid_assignment"].astype(bool)]
    first, latest = valid["candidate_ts"].min(), valid["candidate_ts"].max()
    elapsed = (
        max(0, int(math.floor((latest - first).total_seconds() / 3600)))
        if pd.notna(first) and pd.notna(latest)
        else 0
    )
    candidate_provider_columns = [
        "public_cheapest_provider",
        "public_fastest_provider",
        "public_cost_caliper_provider",
    ]
    providers: set[str] = set()
    for column in candidate_provider_columns:
        if column in valid:
            providers.update(valid[column].dropna().astype(str))
    assigned = valid.get("public_assigned_provider", pd.Series(dtype=str)).dropna().astype(str)
    dominance = float(assigned.value_counts(normalize=True).max()) if len(assigned) else None
    return {
        "candidate_rows": int(len(ledger)),
        "eligible_models": int(ledger["eligible_model"].astype(bool).sum()),
        "assignments_sent": int(sent["block_id"].nunique()),
        "valid_assignments": int(valid["block_id"].nunique()),
        "elapsed_hours": elapsed,
        "assignment_counts": {
            policy: int(valid["assignment"].eq(policy).sum()) for policy in POLICIES
        },
        "models": int(valid["model_id"].nunique()),
        "candidate_providers": int(len(providers)),
        "public_provider_dominance": dominance,
        "treatment_compliance": (
            float(sent["treatment_compliant"].mean()) if len(sent) else 0.0
        ),
        "seed_replay_rate": float(sent["seed_replay_pass"].mean()) if len(sent) else 0.0,
        "latest_timestamp": str(latest) if pd.notna(latest) else None,
        "public_choice_state": {
            "median_assigned_quote_cap_usd": (
                float(pd.to_numeric(valid["public_assigned_quote_cap_usd"]).median())
                if len(valid)
                else None
            ),
            "models_with_distinct_public_cheapest_and_fastest": int(
                valid.loc[
                    valid["public_cheapest_provider"].astype(str)
                    != valid["public_fastest_provider"].astype(str),
                    "model_id",
                ].nunique()
            )
            if len(valid)
            else 0,
        },
    }


def release_gates_pass(
    support: dict[str, Any], requirements: dict[str, Any] = DEFAULT_RELEASE_REQUIREMENTS
) -> bool:
    counts = support["assignment_counts"]
    return bool(
        support["elapsed_hours"] >= requirements["elapsed_hours"]
        and all(counts[policy] >= requirements["assignments_per_arm"] for policy in POLICIES)
        and support["models"] >= requirements["models"]
        and support["candidate_providers"] >= requirements["candidate_providers"]
        and support["public_provider_dominance"] is not None
        and support["public_provider_dominance"]
        <= requirements["max_public_provider_dominance"]
        and support["treatment_compliance"] >= requirements["min_treatment_compliance"]
        and (
            not requirements["require_seed_replay"]
            or np.isclose(support["seed_replay_rate"], 1.0)
        )
    )


def first_release_cutoff(
    ledger: pd.DataFrame,
    requirements: dict[str, Any] = DEFAULT_RELEASE_REQUIREMENTS,
) -> pd.Timestamp | None:
    if ledger.empty or "valid_assignment" not in ledger:
        return None
    valid = ledger[ledger["valid_assignment"].astype(bool)].sort_values("candidate_ts")
    if valid.empty:
        return None
    cumulative = pd.get_dummies(valid["assignment"]).reindex(
        columns=POLICIES, fill_value=0
    ).cumsum()
    first_ts = valid["candidate_ts"].iloc[0]
    possible = np.ones(len(valid), dtype=bool)
    for policy in POLICIES:
        possible &= cumulative[policy].to_numpy() >= requirements["assignments_per_arm"]
    possible &= (
        (valid["candidate_ts"] - first_ts).dt.total_seconds().to_numpy() / 3600
        >= requirements["elapsed_hours"]
    )
    for position in np.flatnonzero(possible):
        cutoff = valid.iloc[position]["candidate_ts"]
        prefix = ledger[ledger["candidate_ts"].le(cutoff)]
        if release_gates_pass(support_summary(prefix), requirements):
            return cutoff
    return None


def randomization_pvalue_two_sided(
    rows: pd.DataFrame,
    arm_a: str,
    arm_b: str,
    column: str,
    *,
    seed: int,
    draws: int = RANDOMIZATION_DRAWS,
) -> dict[str, Any]:
    sample = rows.dropna(subset=[column])
    if sample.empty:
        return {"ht_difference": None, "two_sided_p": None, "draws": draws}
    outcome = sample[column].to_numpy(float)
    assignment = sample["assignment"].astype(str).to_numpy()
    n = len(sample)
    observed = float(
        (len(POLICIES) / n)
        * np.sum(outcome * ((assignment == arm_a).astype(int) - (assignment == arm_b)))
    )
    rng = np.random.default_rng(seed)
    exceed = 0
    batch = 2_000
    for start in range(0, draws, batch):
        size = min(batch, draws - start)
        labels = rng.integers(0, len(POLICIES), size=(size, n))
        weights = (labels == POLICIES.index(arm_a)).astype(int) - (
            labels == POLICIES.index(arm_b)
        ).astype(int)
        simulated = (len(POLICIES) / n) * (weights @ outcome)
        exceed += int(np.sum(np.abs(simulated) >= abs(observed) - 1e-15))
    return {
        "ht_difference": observed,
        "two_sided_p": float((1 + exceed) / (draws + 1)),
        "draws": draws,
    }


def released_results(
    rows: pd.DataFrame,
    *,
    bootstrap_draws: int = BOOTSTRAP_DRAWS,
    randomization_draws: int = RANDOMIZATION_DRAWS,
) -> tuple[dict[str, Any], pd.DataFrame]:
    rows = rows.copy()
    rows["success_numeric"] = rows["success"].astype(float)
    observed_latency = pd.to_numeric(rows["observed_latency_ms"], errors="coerce")
    rows["failure_penalized_latency_ms"] = observed_latency.clip(
        lower=0, upper=FAILURE_LATENCY_CAP_MS
    ).where(rows["success"], FAILURE_LATENCY_CAP_MS).fillna(FAILURE_LATENCY_CAP_MS)
    observed_cost = pd.to_numeric(rows["logged_cost_usd"], errors="coerce")
    public_cost = pd.to_numeric(rows["public_assigned_quote_cap_usd"], errors="coerce")
    rows["cost_penalty_usd"] = observed_cost.where(observed_cost.notna(), public_cost)
    rows["generalized_loss_usd"] = (
        rows["cost_penalty_usd"]
        + VALUE_OF_TIME_USD_PER_SECOND * rows["failure_penalized_latency_ms"] / 1000
        + FAILURE_PENALTY_USD * (~rows["success"]).astype(float)
    )
    comparisons = [
        ("hf_fastest", "hf_cheapest", "failure_penalized_latency_ms"),
        ("hf_cheapest", "hf_fastest", "cost_penalty_usd"),
        ("public_cost_caliper", "hf_fastest", "generalized_loss_usd"),
        ("public_cost_caliper", "hf_cheapest", "generalized_loss_usd"),
    ]
    contrast_rows: list[dict[str, Any]] = []
    p_values: list[float | None] = []
    for offset, (arm_a, arm_b, outcome) in enumerate(comparisons):
        contrast = h87.cluster_arm_difference(
            rows,
            arm_a,
            arm_b,
            outcome,
            seed=RANDOM_SEED + offset,
            draws=bootstrap_draws,
        )
        randomization = randomization_pvalue_two_sided(
            rows,
            arm_a,
            arm_b,
            outcome,
            seed=RANDOM_SEED + 10 + offset,
            draws=randomization_draws,
        )
        row = {
            "comparison": f"{arm_a}_minus_{arm_b}",
            "outcome": outcome,
            **contrast,
            **randomization,
        }
        contrast_rows.append(row)
        p_values.append(randomization["two_sided_p"])
    for row, adjusted in zip(contrast_rows, h87._holm(p_values), strict=True):
        row["holm_two_sided_p"] = adjusted
    arm_rows = []
    for policy in POLICIES:
        arm = rows[rows["assignment"].eq(policy)]
        arm_rows.append(
            {
                "policy": policy,
                "attempts": int(len(arm)),
                "success_rate": float(arm["success"].mean()),
                "failure_penalized_latency_mean_ms": float(
                    arm["failure_penalized_latency_ms"].mean()
                ),
                "logged_estimated_cost_mean_usd": (
                    float(arm["logged_cost_usd"].mean())
                    if arm["logged_cost_usd"].notna().any()
                    else None
                ),
                "cost_telemetry_rate": float(arm["logged_cost_usd"].notna().mean()),
                "generalized_loss_mean_usd": float(arm["generalized_loss_usd"].mean()),
            }
        )
    contrasts = pd.DataFrame(contrast_rows)
    return (
        {
            "arm_outcomes": arm_rows,
            "primary_contrasts": contrast_rows,
            "generalized_loss_definition": {
                "value_of_time_usd_per_second": VALUE_OF_TIME_USD_PER_SECOND,
                "failure_penalty_usd": FAILURE_PENALTY_USD,
                "failure_latency_cap_ms": FAILURE_LATENCY_CAP_MS,
                "missing_cost_rule": "contemporaneous public assigned quote cap",
            },
            "multiplicity": "Holm correction over four two-sided preregistered policy contrasts",
        },
        contrasts,
    )


def plot_support(rows: pd.DataFrame, out_dir: Path) -> None:
    if rows.empty:
        return
    valid = rows[rows["valid_assignment"].astype(bool)]
    if valid.empty:
        return
    colors = ["#33658a", "#f6ae2d", "#4c956c"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    counts = valid["assignment"].value_counts().reindex(POLICIES, fill_value=0)
    axes[0].bar(range(len(POLICIES)), counts, color=colors)
    axes[0].set_xticks(range(len(POLICIES)), ["fastest", "cheapest", "caliper"])
    axes[0].set_ylabel("Valid randomized assignments")
    axes[0].set_title("H89 outcome-masked enrollment")
    provider_counts = valid["public_assigned_provider"].value_counts().head(8)
    axes[1].barh(range(len(provider_counts)), provider_counts, color="#6c757d")
    axes[1].set_yticks(range(len(provider_counts)), provider_counts.index)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Assignments")
    axes[1].set_title("Public predicted provider (not realized)")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h89_hf_policy_support.png", dpi=180)
    fig.savefig(out_dir / "h89_hf_policy_support.pdf")
    plt.close(fig)


def plot_released(result: dict[str, Any], out_dir: Path) -> None:
    arms = pd.DataFrame(result["arm_outcomes"]).set_index("policy").reindex(POLICIES)
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.2))
    labels = ["fastest", "cheapest", "caliper"]
    colors = ["#33658a", "#f6ae2d", "#4c956c"]
    axes[0].bar(range(3), arms["success_rate"], color=colors)
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Success rate")
    axes[1].bar(range(3), arms["failure_penalized_latency_mean_ms"], color=colors)
    axes[1].set_ylabel("Failure-penalized latency (ms)")
    axes[2].bar(range(3), arms["generalized_loss_mean_usd"], color=colors)
    axes[2].set_ylabel("Registered generalized loss (USD)")
    for axis in axes:
        axis.set_xticks(range(3), labels)
    axes[0].set_title("Reliability")
    axes[1].set_title("Speed")
    axes[2].set_title("Cost-speed-failure objective")
    fig.suptitle("H89 randomized Hugging Face routing policies")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h89_hf_policy_trial.png", dpi=180)
    fig.savefig(out_dir / "h89_hf_policy_trial.pdf")
    plt.close(fig)


def analyze(
    candidates: pd.DataFrame,
    attempts: pd.DataFrame,
    out_dir: Path | None = None,
    *,
    requirements: dict[str, Any] = DEFAULT_RELEASE_REQUIREMENTS,
    bootstrap_draws: int = BOOTSTRAP_DRAWS,
    randomization_draws: int = RANDOMIZATION_DRAWS,
) -> dict[str, Any]:
    prepared = prepare_candidates(candidates)
    ledger = assignment_ledger(prepared, attempts)
    support = support_summary(ledger)
    cutoff = first_release_cutoff(ledger, requirements)
    summary: dict[str, Any] = {
        "evidence_status": (
            "prospective_randomized_hf_policy_released"
            if cutoff is not None
            else "prospective_randomized_hf_policy_power_gated"
        ),
        "preregistration": "docs/h89-huggingface-policy-trial-preregistration.md",
        "study_id": STUDY_ID,
        "outcomes_released": cutoff is not None,
        "release_cutoff": str(cutoff) if cutoff is not None else None,
        "support": support,
        "sample_release_requirements": requirements,
        "claim_boundary": (
            "H89 identifies owned one-token request effects of documented Hugging Face "
            "routing-policy suffixes and a public cost-caliper provider policy on a frozen "
            "model/workload population. It does not identify other-user allocation, provider "
            "capacity or intent, a direct-provider contract, or collateralized liability."
        ),
    }
    if out_dir is not None:
        support_columns = [
            "study_id",
            "run_ts",
            "block_id",
            "model_id",
            "candidate_ts",
            "assignment",
            "assignment_probability",
            "public_cheapest_provider",
            "public_fastest_provider",
            "public_cost_caliper_provider",
            "public_assigned_provider",
            "public_assigned_quote_cap_usd",
            "eligible_model",
            "request_sent",
            "exclusion_reason",
            "seed_replay_pass",
            "attempt_present",
            "treatment_compliant",
            "valid_assignment",
        ]
        support_frame = ledger[[column for column in support_columns if column in ledger]]
        save(support_frame, out_dir, "h89_assignment_support")
        plot_support(support_frame, out_dir)
    if cutoff is not None:
        released = ledger[
            ledger["valid_assignment"].astype(bool) & ledger["candidate_ts"].le(cutoff)
        ].copy()
        result, contrasts = released_results(
            released,
            bootstrap_draws=bootstrap_draws,
            randomization_draws=randomization_draws,
        )
        summary["released_results"] = result
        if out_dir is not None:
            save(released, out_dir, "h89_released_trial_rows")
            save(contrasts, out_dir, "h89_primary_contrasts")
            plot_released(result, out_dir)
    if out_dir is not None:
        save_json(summary, out_dir, "h89_summary")
    return summary


def _load_table(name: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select * from read_parquet('{data.table_glob(name)}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    candidates = _load_table("h89_hf_policy_candidates")
    all_attempts = _load_table("router_route_attempts")
    attempts = (
        all_attempts[all_attempts["study_id"].astype(str).eq(STUDY_ID)].copy()
        if not all_attempts.empty and "study_id" in all_attempts
        else all_attempts
    )
    return analyze(candidates, attempts, out_dir)
