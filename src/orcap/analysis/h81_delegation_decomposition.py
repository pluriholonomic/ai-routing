"""H81 — randomized decomposition of fallback and hidden-selection value."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h80_matched_quote_firmness import holm_adjust

STUDY_ID = "openrouter-fallback-selection-decomposition-v1"
POLICIES = (
    "delegated_default",
    "price_only_no_fallback",
    "price_order_fallback",
)
COMPARISONS = (
    ("fallback_option", "price_order_fallback", "price_only_no_fallback", True),
    ("hidden_selection", "delegated_default", "price_order_fallback", True),
    ("total_delegation", "delegated_default", "price_only_no_fallback", False),
)
MIN_FIRST_POSITION_PER_POLICY = 40
RANDOMIZATION_DRAWS = 100_000


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def prepare_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame[frame["study_id"].astype(str).eq(STUDY_ID)].copy()
    if {"source", "event_id"}.issubset(out.columns):
        out = out.sort_values(["source", "event_id", "run_ts"]).drop_duplicates(
            ["source", "event_id"], keep="last"
        )
    metadata = out.get("metadata_json", pd.Series("{}", index=out.index)).map(_metadata)
    keys = (
        "block_id",
        "block_policy_count",
        "policy_order",
        "block_seed",
        "assignment_probability_first",
        "randomized_order",
        "public_provider_count",
        "public_provider_order_sha256",
        "public_cheapest_provider",
        "public_cheapest_completion_price",
        "requested_order_length",
        "allow_fallbacks",
    )
    for key in keys:
        values = [item.get(key) for item in metadata]
        if key == "block_seed":
            out[key] = pd.Series(
                [str(value) if value is not None else None for value in values],
                index=out.index,
                dtype="string",
            )
        else:
            out[key] = pd.Series(values, index=out.index)
    out["policy_order"] = pd.to_numeric(out["policy_order"], errors="coerce")
    out["success"] = out["outcome"].astype(str).eq("succeeded")
    out["rejected_429"] = (~out["success"]) & out.get(
        "retry_reason", pd.Series("", index=out.index)
    ).fillna("").astype(str).str.contains("429")
    cost = pd.to_numeric(out.get("cost_usd"), errors="coerce")
    out["observed_spend_usd"] = cost.where(out["success"], 0.0)
    return out


def verify_first_assignment(block: pd.DataFrame) -> bool:
    try:
        seed = int(block["block_seed"].iloc[0])
        count = int(block["block_policy_count"].dropna().iloc[0])
    except (IndexError, TypeError, ValueError):
        return False
    first = block[block["policy_order"].eq(0)]
    if count != len(POLICIES) or len(first) != 1:
        return False
    expected = list(POLICIES)
    random.Random(seed).shuffle(expected)
    return str(first["policy"].iloc[0]) == expected[0]


def first_position_sample(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    attempts = prepare_attempts(frame)
    first_rows = []
    candidate_blocks = 0
    verified_blocks = 0
    complete_blocks = 0
    for block_id, block in attempts.groupby("block_id", sort=False, dropna=True):
        if not block_id:
            continue
        candidate_blocks += 1
        complete_blocks += int(
            len(block) == len(POLICIES)
            and set(block["policy"]) == set(POLICIES)
            and not block["policy"].duplicated().any()
            and not block["policy_order"].duplicated().any()
        )
        if not verify_first_assignment(block):
            continue
        first = block[block["policy_order"].eq(0)].iloc[0].copy()
        first["assignment_verified"] = True
        first_rows.append(first)
        verified_blocks += 1
    first = pd.DataFrame(first_rows)
    audit = {
        "candidate_blocks": candidate_blocks,
        "verified_first_position_blocks": verified_blocks,
        "complete_blocks": complete_blocks,
        "assignment_replay_rate": (
            verified_blocks / candidate_blocks if candidate_blocks else None
        ),
    }
    return first, audit


def _order_entropy(attempts: pd.DataFrame) -> float | None:
    if attempts.empty:
        return None
    values = []
    for policy in POLICIES:
        distribution = (
            attempts[attempts["policy"].eq(policy)]["policy_order"]
            .value_counts(normalize=True)
            .to_numpy(dtype=float)
        )
        if len(distribution):
            values.append(float(-(distribution * np.log(distribution)).sum() / math.log(3)))
    return float(np.mean(values)) if values else None


def analyze(
    frame: pd.DataFrame, *, simulations: int = RANDOMIZATION_DRAWS
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    attempts = prepare_attempts(frame)
    first, audit = first_position_sample(attempts)
    n_blocks = len(first)
    panel_rows = []
    for policy in POLICIES:
        arm = first[first["policy"].eq(policy)] if n_blocks else first
        n = len(arm)
        successes = int(arm["success"].sum()) if n else 0
        low, high = (
            proportion_confint(successes, n, method="wilson")
            if n
            else (np.nan, np.nan)
        )
        probability = pd.to_numeric(
            arm.get("assignment_probability_first"), errors="coerce"
        )
        spend_missing = int(arm["observed_spend_usd"].isna().sum()) if n else 0
        successful = arm[arm["success"]] if n else arm
        successful_latency = pd.to_numeric(
            successful.get(
                "latency_ms", pd.Series(index=successful.index, dtype=float)
            ),
            errors="coerce",
        )
        successful_provider = successful.get(
            "selected_provider", pd.Series(index=successful.index, dtype=object)
        )
        panel_rows.append(
            {
                "policy": policy,
                "first_position_attempts": n,
                "successes": successes,
                "success_rate": successes / n if n else np.nan,
                "success_ci_low": float(low),
                "success_ci_high": float(high),
                "ht_success_mean": (
                    float((arm["success"].astype(float) / probability).sum() / n_blocks)
                    if n_blocks and n and probability.notna().all()
                    else np.nan
                ),
                "rate_429": float(arm["rejected_429"].mean()) if n else np.nan,
                "fallback_observed_rate": (
                    float(arm["fallback_triggered"].mean()) if n else np.nan
                ),
                "spend_missing": spend_missing,
                "latency_missing_successes": int(successful_latency.isna().sum()),
                "selected_provider_missing_successes": int(
                    successful_provider.isna().sum()
                ),
                "mean_observed_spend_usd": (
                    float(arm["observed_spend_usd"].mean())
                    if n and not spend_missing
                    else np.nan
                ),
            }
        )
    panel = pd.DataFrame(panel_rows)

    model_rows = []
    if n_blocks:
        for (model_id, policy), arm in first.groupby(["model_id", "policy"], sort=True):
            model_blocks = int(first["model_id"].eq(model_id).sum())
            probability = pd.to_numeric(arm["assignment_probability_first"], errors="coerce")
            model_rows.append(
                {
                    "model_id": model_id,
                    "policy": policy,
                    "model_blocks": model_blocks,
                    "attempts": len(arm),
                    "success_rate": float(arm["success"].mean()),
                    "ht_success_mean_within_model": float(
                        (arm["success"].astype(float) / probability).sum() / model_blocks
                    ),
                }
            )
    model_panel = pd.DataFrame(model_rows)

    if n_blocks and simulations:
        outcomes = first["success"].astype(float).to_numpy()
        labels = np.random.default_rng(20260715).integers(
            0, len(POLICIES), size=(simulations, n_blocks), dtype=np.int8
        )
    else:
        outcomes = np.array([], dtype=float)
        labels = np.empty((0, 0), dtype=np.int8)
    policy_index = {policy: index for index, policy in enumerate(POLICIES)}
    probability = 1.0 / len(POLICIES)
    contrast_rows = []
    for name, positive, negative, primary in COMPARISONS:
        pos = first[first["policy"].eq(positive)] if n_blocks else first
        neg = first[first["policy"].eq(negative)] if n_blocks else first
        raw = (
            float(pos["success"].mean() - neg["success"].mean())
            if len(pos) and len(neg)
            else np.nan
        )
        if len(pos) and len(neg):
            ci_low, ci_high = confint_proportions_2indep(
                int(pos["success"].sum()),
                len(pos),
                int(neg["success"].sum()),
                len(neg),
                method="newcomb",
                compare="diff",
            )
        else:
            ci_low = ci_high = np.nan
        ht = (
            float(
                (
                    first["policy"].eq(positive).to_numpy() * outcomes / probability
                    - first["policy"].eq(negative).to_numpy() * outcomes / probability
                ).sum()
                / n_blocks
            )
            if n_blocks
            else np.nan
        )
        if n_blocks and simulations:
            simulated = (
                (
                    (labels == policy_index[positive]) * outcomes[None, :] / probability
                    - (labels == policy_index[negative]) * outcomes[None, :] / probability
                ).sum(axis=1)
                / n_blocks
            )
            p_greater = float((1 + (simulated >= ht - 1e-15).sum()) / (simulations + 1))
            p_two_sided = float(
                (1 + (np.abs(simulated) >= abs(ht) - 1e-15).sum()) / (simulations + 1)
            )
        else:
            p_greater = p_two_sided = np.nan
        spend_complete = bool(
            len(pos)
            and len(neg)
            and pos["observed_spend_usd"].notna().all()
            and neg["observed_spend_usd"].notna().all()
        )
        spend_difference = (
            float(pos["observed_spend_usd"].mean() - neg["observed_spend_usd"].mean())
            if spend_complete
            else np.nan
        )
        contrast_rows.append(
            {
                "estimand": name,
                "positive_policy": positive,
                "negative_policy": negative,
                "primary": primary,
                "n_blocks": n_blocks,
                "positive_n": len(pos),
                "negative_n": len(neg),
                "success_difference_hajek": raw,
                "success_difference_ci_low": float(ci_low),
                "success_difference_ci_high": float(ci_high),
                "success_difference_ht": ht,
                "randomization_p_greater": p_greater,
                "randomization_p_two_sided": p_two_sided,
                "spend_complete_both_arms": spend_complete,
                "observed_spend_difference_usd": spend_difference,
            }
        )
    contrasts = pd.DataFrame(contrast_rows)
    contrasts["holm_p_greater"] = np.nan
    primary_mask = contrasts["primary"].astype(bool)
    contrasts.loc[primary_mask, "holm_p_greater"] = holm_adjust(
        contrasts.loc[primary_mask, "randomization_p_greater"].tolist()
    )

    counts = panel.set_index("policy")["first_position_attempts"].reindex(POLICIES, fill_value=0)
    min_count = int(counts.min())
    audit.update(
        {
            "study_id": STUDY_ID,
            "first_position_counts": {key: int(value) for key, value in counts.items()},
            "models_represented": int(first["model_id"].nunique()) if n_blocks else 0,
            "model_ids": (
                sorted(first["model_id"].astype(str).unique().tolist())
                if n_blocks
                else []
            ),
            "normalized_order_entropy": _order_entropy(attempts),
            "target_per_policy": MIN_FIRST_POSITION_PER_POLICY,
            "randomization_draws": simulations,
            "evidence_status": (
                "randomized_decomposition_ready"
                if min_count >= MIN_FIRST_POSITION_PER_POLICY
                else "randomized_decomposition_power_gated"
            ),
            "claim_boundary": (
                "The fallback contrast holds the cheapest first provider fixed and changes "
                "fallback permission. The hidden-selection contrast compares delegated default "
                "with an explicit public-price order, both permitting fallback. It measures one "
                "owned account and does not reveal provider intent or private router scores."
            ),
        }
    )
    return panel, model_panel, contrasts, audit


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    frame = data.q(
        f"""
        select *
        from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
        """
    ).df()
    panel, model_panel, contrasts, summary = analyze(frame)
    save(panel, out_dir, "h81_policy_panel")
    save(model_panel, out_dir, "h81_model_policy_panel")
    save(contrasts, out_dir, "h81_contrasts")
    save_json(summary, out_dir, "h81_summary")
    return summary
