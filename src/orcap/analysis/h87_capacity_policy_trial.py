"""H87 — outcome-masked randomized public-capacity routing policy trial."""

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

from ..capture_capacity_policy_probes import POLICIES, STUDY_ID
from . import data
from .common import DEFAULT_OUT, save, save_json

RANDOM_SEED = 87_870_715
BOOTSTRAP_DRAWS = 10_000
RANDOMIZATION_DRAWS = 100_000
MAX_CROSS_STUDY_MINUTES = 5.0
DEFAULT_RELEASE_REQUIREMENTS = {
    "complete_days": 28,
    "assignments_per_arm": 150,
    "models": 10,
    "candidate_providers": 20,
    "max_requested_provider_dominance": 0.20,
    "min_pinned_treatment_compliance": 0.90,
    "require_seed_replay": True,
    "require_no_cross_study_overlap": True,
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
    out = frame.copy()
    out = out[out["study_id"].astype(str).eq(STUDY_ID)].copy()
    out = out.sort_values("run_ts").drop_duplicates("block_id", keep="last")
    out["candidate_ts"] = pd.to_datetime(
        out.get("request_observed_at", out.get("run_ts")), utc=True, errors="coerce"
    )
    for column in ["eligible_pair", "request_sent"]:
        out[column] = out.get(column, False).fillna(False).astype(bool)
    out["assignment"] = out.get("assignment", pd.Series(pd.NA, index=out.index)).astype("string")

    def replay(row: pd.Series) -> bool:
        try:
            assignment = row["assignment"]
            if pd.isna(assignment):
                return False
            return random.Random(int(row["block_seed"])).choice(POLICIES) == str(assignment)
        except (KeyError, TypeError, ValueError):
            return False

    out["seed_replay_pass"] = out.apply(replay, axis=1)
    safe_assignment = out["assignment"].eq("capacity_safe").fillna(False)
    risky_assignment = out["assignment"].eq("capacity_risky").fillna(False)
    expected = pd.Series(None, index=out.index, dtype="object")
    if "safe_provider" in out:
        expected.loc[safe_assignment] = out.loc[safe_assignment, "safe_provider"]
    if "risky_provider" in out:
        expected.loc[risky_assignment] = out.loc[risky_assignment, "risky_provider"]
    out["expected_requested_provider"] = expected
    out["candidate_cluster"] = (
        out["model_id"].astype(str) + "|" + out["candidate_ts"].dt.strftime("%Y-%m-%d")
    )
    return out


def prepare_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame.copy()
    out = out[out["study_id"].astype(str).eq(STUDY_ID)].copy()
    metadata = out.get("metadata_json", pd.Series("{}", index=out.index)).map(_metadata)
    out["block_id"] = [item.get("block_id") for item in metadata]
    out["attempt_candidate_state_hash"] = [item.get("candidate_state_hash") for item in metadata]
    out["attempt_ts"] = pd.to_datetime(out.get("observed_at"), utc=True, errors="coerce")
    out["success"] = out["outcome"].astype(str).eq("succeeded")
    out["rejected_429"] = (~out["success"]) & out.get(
        "retry_reason", pd.Series("", index=out.index)
    ).fillna("").astype(str).str.contains("429")
    out["observed_spend_usd"] = pd.to_numeric(out.get("cost_usd"), errors="coerce").where(
        out["success"], 0.0
    )
    out = out.sort_values("attempt_ts").drop_duplicates("block_id", keep="last")
    return out


def cross_study_overlap_blocks(candidates: pd.DataFrame, all_attempts: pd.DataFrame) -> set[str]:
    if candidates.empty or all_attempts.empty:
        return set()
    other = all_attempts[~all_attempts["study_id"].astype(str).eq(STUDY_ID)].copy()
    other["other_ts"] = pd.to_datetime(other.get("observed_at"), utc=True, errors="coerce")
    times = other["other_ts"].dropna().sort_values().to_numpy(dtype="datetime64[ns]")
    if not len(times):
        return set()
    overlap: set[str] = set()
    for row in candidates.dropna(subset=["candidate_ts"]).itertuples():
        target = row.candidate_ts.to_datetime64()
        position = int(np.searchsorted(times, target))
        neighbors = times[max(0, position - 1) : min(len(times), position + 1)]
        if any(
            abs((pd.Timestamp(value, tz="UTC") - row.candidate_ts).total_seconds())
            <= MAX_CROSS_STUDY_MINUTES * 60
            for value in neighbors
        ):
            overlap.add(str(row.block_id))
    return overlap


def assignment_ledger(
    candidates: pd.DataFrame, h87_attempts: pd.DataFrame, all_attempts: pd.DataFrame
) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    attempts = prepare_attempts(h87_attempts)
    attempt_fields = [
        "block_id",
        "event_id",
        "attempt_ts",
        "requested_provider",
        "selected_provider",
        "policy",
        "attempt_candidate_state_hash",
        "success",
        "rejected_429",
        "observed_spend_usd",
        "latency_ms",
        "outcome",
        "retry_reason",
    ]
    for column in attempt_fields:
        if column not in attempts:
            attempts[column] = pd.NA
    ledger = candidates.merge(
        attempts[attempt_fields], on="block_id", how="left", validate="one_to_one"
    )
    overlap = cross_study_overlap_blocks(candidates, all_attempts)
    ledger["cross_study_overlap"] = ledger["block_id"].astype(str).isin(overlap)
    ledger["attempt_present"] = ledger["event_id"].notna()
    ledger["assignment_payload_compliant"] = (
        ledger["policy"].astype("string").eq(ledger["assignment"])
        & ledger["requested_provider"]
        .fillna("<default>")
        .astype(str)
        .eq(ledger["expected_requested_provider"].fillna("<default>").astype(str))
        & ledger["attempt_candidate_state_hash"]
        .astype("string")
        .eq(ledger["candidate_state_hash"].astype("string"))
    ).fillna(False)
    successful_pinned = ledger["assignment"].isin(["capacity_safe", "capacity_risky"]) & ledger[
        "success"
    ].astype("boolean").fillna(False)
    selected_matches = (
        ledger["selected_provider"]
        .astype("string")
        .eq(ledger["expected_requested_provider"].astype("string"))
        .fillna(False)
    )
    ledger["treatment_compliant"] = ledger["assignment_payload_compliant"] & (
        ~successful_pinned | selected_matches
    )
    ledger["treatment_compliant"] = ledger["treatment_compliant"].fillna(False)
    ledger["valid_assignment"] = (
        ledger["eligible_pair"].astype("boolean").fillna(False)
        & ledger["request_sent"].astype("boolean").fillna(False)
        & ledger["attempt_present"].astype("boolean").fillna(False)
        & ledger["seed_replay_pass"].astype("boolean").fillna(False)
        & ledger["treatment_compliant"].astype("boolean").fillna(False)
        & ~ledger["cross_study_overlap"].astype("boolean").fillna(False)
    )
    return ledger


def support_summary(ledger: pd.DataFrame) -> dict[str, Any]:
    if ledger.empty:
        return {
            "candidate_rows": 0,
            "eligible_pairs": 0,
            "assignments_sent": 0,
            "valid_assignments": 0,
            "complete_days": 0,
            "assignment_counts": {policy: 0 for policy in POLICIES},
            "models": 0,
            "candidate_providers": 0,
            "requested_provider_dominance": None,
            "pinned_treatment_compliance": 0.0,
            "seed_replay_rate": 0.0,
            "cross_study_overlap_blocks": 0,
            "latest_timestamp": None,
        }
    sent = ledger[ledger["eligible_pair"].astype(bool) & ledger["request_sent"].astype(bool)]
    valid = ledger[ledger["valid_assignment"].astype(bool)]
    first = valid["candidate_ts"].min()
    latest = valid["candidate_ts"].max()
    complete_days = (
        max(0, int(math.floor((latest - first).total_seconds() / 86400)))
        if pd.notna(first) and pd.notna(latest)
        else 0
    )
    providers = set(valid.get("safe_provider", pd.Series(dtype=str)).dropna().astype(str))
    providers.update(valid.get("risky_provider", pd.Series(dtype=str)).dropna().astype(str))
    pinned = valid[valid["assignment"].isin(["capacity_safe", "capacity_risky"])]
    requested = pinned["expected_requested_provider"].dropna().astype(str)
    dominance = float(requested.value_counts(normalize=True).max()) if len(requested) else None
    return {
        "candidate_rows": int(len(ledger)),
        "eligible_pairs": int(ledger["eligible_pair"].astype(bool).sum()),
        "assignments_sent": int(sent["block_id"].nunique()),
        "valid_assignments": int(valid["block_id"].nunique()),
        "complete_days": complete_days,
        "assignment_counts": {
            policy: int(valid["assignment"].eq(policy).sum()) for policy in POLICIES
        },
        "models": int(valid["model_id"].nunique()),
        "candidate_providers": int(len(providers)),
        "requested_provider_dominance": dominance,
        "pinned_treatment_compliance": (
            float(pinned["treatment_compliant"].mean()) if len(pinned) else 0.0
        ),
        "seed_replay_rate": float(sent["seed_replay_pass"].mean()) if len(sent) else 0.0,
        "cross_study_overlap_blocks": int(sent["cross_study_overlap"].astype(bool).sum()),
        "latest_timestamp": str(latest) if pd.notna(latest) else None,
        "choice_state": {
            "median_capacity_risk_gap": (
                float(valid["capacity_risk_gap"].median()) if len(valid) else None
            ),
            "median_price_ratio": float(valid["price_ratio"].median()) if len(valid) else None,
        },
    }


def release_gates_pass(
    support: dict[str, Any], requirements: dict[str, Any] = DEFAULT_RELEASE_REQUIREMENTS
) -> bool:
    counts = support["assignment_counts"]
    return bool(
        support["complete_days"] >= requirements["complete_days"]
        and all(counts[policy] >= requirements["assignments_per_arm"] for policy in POLICIES)
        and support["models"] >= requirements["models"]
        and support["candidate_providers"] >= requirements["candidate_providers"]
        and support["requested_provider_dominance"] is not None
        and support["requested_provider_dominance"]
        <= requirements["max_requested_provider_dominance"]
        and support["pinned_treatment_compliance"]
        >= requirements["min_pinned_treatment_compliance"]
        and (
            not requirements["require_seed_replay"] or np.isclose(support["seed_replay_rate"], 1.0)
        )
        and (
            not requirements["require_no_cross_study_overlap"]
            or support["cross_study_overlap_blocks"] == 0
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
    # The arm and elapsed-time gates cheaply exclude almost every early row.
    cumulative = (
        pd.get_dummies(valid["assignment"]).reindex(columns=POLICIES, fill_value=0).cumsum()
    )
    first_ts = valid["candidate_ts"].iloc[0]
    possible = np.ones(len(valid), dtype=bool)
    for policy in POLICIES:
        possible &= cumulative[policy].to_numpy() >= requirements["assignments_per_arm"]
    possible &= (
        valid["candidate_ts"] - first_ts
    ).dt.total_seconds().to_numpy() / 86400 >= requirements["complete_days"]
    for position in np.flatnonzero(possible):
        prefix = ledger[ledger["candidate_ts"].le(valid.iloc[position]["candidate_ts"])]
        if release_gates_pass(support_summary(prefix), requirements):
            return valid.iloc[position]["candidate_ts"]
    return None


def cluster_arm_difference(
    rows: pd.DataFrame,
    arm_a: str,
    arm_b: str,
    column: str,
    *,
    seed: int,
    draws: int = BOOTSTRAP_DRAWS,
) -> dict[str, Any]:
    sample = rows[rows["assignment"].isin([arm_a, arm_b])].dropna(
        subset=[column, "candidate_cluster"]
    )
    a = sample[sample["assignment"].eq(arm_a)][column]
    b = sample[sample["assignment"].eq(arm_b)][column]
    if a.empty or b.empty:
        return {"arm_a": arm_a, "arm_b": arm_b, "mean": None, "ci95": [None, None]}
    observed = float(a.mean() - b.mean())
    grouped = {key: value for key, value in sample.groupby("candidate_cluster")}
    keys = list(grouped)
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(draws):
        boot = pd.concat([grouped[key] for key in rng.choice(keys, len(keys), replace=True)])
        boot_a = boot[boot["assignment"].eq(arm_a)][column]
        boot_b = boot[boot["assignment"].eq(arm_b)][column]
        if len(boot_a) and len(boot_b):
            estimates.append(float(boot_a.mean() - boot_b.mean()))
    return {
        "arm_a": arm_a,
        "arm_b": arm_b,
        "n_a": int(len(a)),
        "n_b": int(len(b)),
        "mean": observed,
        "ci95": (
            [float(np.quantile(estimates, 0.025)), float(np.quantile(estimates, 0.975))]
            if estimates
            else [None, None]
        ),
    }


def randomization_pvalue(
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
        return {"ht_difference": None, "one_sided_p": None, "draws": draws}
    outcome = sample[column].to_numpy(float)
    assignment = sample["assignment"].astype(str).to_numpy()
    n = len(sample)
    observed = float(
        (len(POLICIES) / n)
        * np.sum(outcome * ((assignment == arm_a).astype(int) - (assignment == arm_b).astype(int)))
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
        exceed += int(np.sum(simulated >= observed - 1e-15))
    return {
        "ht_difference": observed,
        "one_sided_p": float((1 + exceed) / (draws + 1)),
        "draws": draws,
    }


def _holm(values: list[float | None]) -> list[float | None]:
    valid = [(index, value) for index, value in enumerate(values) if value is not None]
    adjusted: list[float | None] = [None] * len(values)
    running = 0.0
    for rank, (index, value) in enumerate(sorted(valid, key=lambda item: item[1])):
        candidate = min(1.0, (len(valid) - rank) * float(value))
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted


def released_results(
    rows: pd.DataFrame,
    *,
    bootstrap_draws: int = BOOTSTRAP_DRAWS,
    randomization_draws: int = RANDOMIZATION_DRAWS,
) -> tuple[dict[str, Any], pd.DataFrame]:
    rows = rows.copy()
    rows["success_numeric"] = rows["success"].astype(float)
    comparisons = [
        ("capacity_safe", "capacity_risky"),
        ("openrouter_default", "capacity_safe"),
    ]
    contrast_rows = []
    p_values = []
    for offset, (arm_a, arm_b) in enumerate(comparisons):
        contrast = cluster_arm_difference(
            rows,
            arm_a,
            arm_b,
            "success_numeric",
            seed=RANDOM_SEED + offset,
            draws=bootstrap_draws,
        )
        randomization = randomization_pvalue(
            rows,
            arm_a,
            arm_b,
            "success_numeric",
            seed=RANDOM_SEED + 10 + offset,
            draws=randomization_draws,
        )
        row = {"comparison": f"{arm_a}_minus_{arm_b}", **contrast, **randomization}
        contrast_rows.append(row)
        p_values.append(randomization["one_sided_p"])
    adjusted = _holm(p_values)
    for row, p_value in zip(contrast_rows, adjusted, strict=True):
        row["holm_one_sided_p"] = p_value
    contrasts = pd.DataFrame(contrast_rows)
    arm_rows = []
    for policy in POLICIES:
        arm = rows[rows["assignment"].eq(policy)]
        arm_rows.append(
            {
                "policy": policy,
                "attempts": int(len(arm)),
                "success_rate": float(arm["success"].mean()),
                "http_429_rate": float(arm["rejected_429"].mean()),
                "observed_spend_mean_usd": (
                    float(arm["observed_spend_usd"].mean())
                    if arm["observed_spend_usd"].notna().any()
                    else None
                ),
                "successful_latency_mean_ms": (
                    float(
                        pd.to_numeric(arm.loc[arm["success"], "latency_ms"], errors="coerce").mean()
                    )
                    if arm.loc[arm["success"], "latency_ms"].notna().any()
                    else None
                ),
            }
        )
    result = {
        "arm_outcomes": arm_rows,
        "primary_contrasts": contrast_rows,
        "multiplicity": "Holm correction over two one-sided preregistered success tests",
    }
    return result, contrasts


def plot_released(result: dict[str, Any], contrasts: pd.DataFrame, out_dir: Path) -> None:
    arms = pd.DataFrame(result["arm_outcomes"]).set_index("policy").reindex(POLICIES)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    axes[0].bar(range(len(arms)), arms["success_rate"], color=["#4c956c", "#c14953", "#33658a"])
    axes[0].set_xticks(range(len(arms)), ["capacity safe", "capacity risky", "default"])
    axes[0].set_ylabel("Success rate")
    axes[0].set_ylim(0, 1)
    axes[0].set_title("H87 randomized first-and-only probes")
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
    fig.savefig(out_dir / "h87_capacity_policy_trial.png", dpi=180)
    fig.savefig(out_dir / "h87_capacity_policy_trial.pdf")
    plt.close(fig)


def analyze(
    candidates: pd.DataFrame,
    h87_attempts: pd.DataFrame,
    all_attempts: pd.DataFrame,
    out_dir: Path | None = None,
    *,
    requirements: dict[str, Any] = DEFAULT_RELEASE_REQUIREMENTS,
    bootstrap_draws: int = BOOTSTRAP_DRAWS,
    randomization_draws: int = RANDOMIZATION_DRAWS,
) -> dict[str, Any]:
    prepared = prepare_candidates(candidates)
    ledger = assignment_ledger(prepared, h87_attempts, all_attempts)
    support = support_summary(ledger)
    cutoff = first_release_cutoff(ledger, requirements)
    summary: dict[str, Any] = {
        "evidence_status": (
            "prospective_randomized_capacity_policy_released"
            if cutoff is not None
            else "prospective_randomized_capacity_policy_power_gated"
        ),
        "preregistration": "docs/h86-h87-capacity-state-execution-preregistration.md",
        "study_id": STUDY_ID,
        "outcomes_released": cutoff is not None,
        "release_cutoff": str(cutoff) if cutoff is not None else None,
        "support": support,
        "sample_release_requirements": requirements,
        "claim_boundary": (
            "H87 identifies routing-policy effects for public-state-eligible owned probes. "
            "It does not identify physical capacity, provider intent, front-running, other-user "
            "welfare, or a collateralized commitment effect."
        ),
    }
    if out_dir is not None:
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
            "capacity_risk_gap",
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
        save(
            ledger[[column for column in support_columns if column in ledger]],
            out_dir,
            "h87_assignment_support",
        )
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
            save(released, out_dir, "h87_released_trial_rows")
            save(contrasts, out_dir, "h87_primary_contrasts")
            plot_released(result, contrasts, out_dir)
    if out_dir is not None:
        save_json(summary, out_dir, "h87_summary")
    return summary


def _load_table(name: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select * from read_parquet('{data.table_glob(name)}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    candidates = _load_table("h87_capacity_policy_candidates")
    all_attempts = _load_table("router_route_attempts")
    h87_attempts = (
        all_attempts[all_attempts["study_id"].astype(str).eq(STUDY_ID)].copy()
        if not all_attempts.empty
        else all_attempts
    )
    return analyze(candidates, h87_attempts, all_attempts, out_dir)
