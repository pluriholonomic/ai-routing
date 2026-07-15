"""H80 — matched quote firmness and randomized micro-probe crossover.

The legacy v1 probe placed OpenRouter's default policy first and then pinned
the public cheapest, second-cheapest, and a random quoted provider.  H80 turns
those near-simultaneous attempts into matched blocks, but labels every contrast
descriptive because policy and order are perfectly confounded.

The v2 collector publishes an auditable random permutation of the same four
policies.  Its primary estimand uses only the first attempt in each block.  A
first-position contrast is unbiased under the randomized assignment even if
earlier attempts affect the rate limits faced by later attempts.  Full-block
crossover contrasts remain secondary and require a no-carryover assumption.

Outputs:
  h80_probe_blocks.parquet
  h80_policy_panel.parquet
  h80_pairwise_contrasts.parquet
  h80_randomized_first_position.parquet
  h80_randomized_model_policy.parquet
  h80_randomized_contrasts.parquet
  h80_summary.json
  h80_quote_firmness.png / .pdf
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint

from . import data
from .common import DEFAULT_OUT, save, save_json
from .missingness_bounds import bounded_mean, difference_bounds, ht_bounded_mean

POLICIES = (
    "openrouter_default",
    "pinned_cheapest",
    "pinned_second",
    "pinned_random",
)
LEGACY_STUDY_ID = "openrouter-default-probes-v1"
RANDOMIZED_STUDY_ID = "openrouter-routing-crossover-v2"
MAX_LEGACY_BLOCK_SECONDS = 120
MIN_FIRST_POSITION_PER_POLICY = 40
RANDOMIZATION_DRAWS = 100_000


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def prepare_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate attempts and expose the payload-free assignment metadata."""
    if frame.empty:
        return frame.copy()
    out = frame.copy()
    if {"source", "event_id"}.issubset(out.columns):
        order = ["source", "event_id"] + (["run_ts"] if "run_ts" in out else [])
        out = out.sort_values(order).drop_duplicates(["source", "event_id"], keep="last")
    out = out[out["policy"].isin(POLICIES)].copy()
    out["observed_ts"] = pd.to_datetime(out["observed_at"], utc=True, errors="coerce")
    meta = out.get("metadata_json", pd.Series("{}", index=out.index)).map(_metadata)
    for key in (
        "block_id",
        "block_policy_count",
        "policy_order",
        "block_seed",
        "assignment_probability_first",
        "randomized_order",
        "quoted_price_completion",
        "public_quote_cost_cap_usd",
        "quote_cap_input_tokens",
        "request_timeout_ms",
        "quoted_rank",
        "n_quoted",
    ):
        values = [item.get(key) for item in meta]
        # Seeds are unsigned 64-bit integers.  An ordinary pandas column with
        # legacy nulls would coerce them to float and silently lose bits, while
        # Arrow's default signed integer conversion can overflow.  Decimal text
        # is exact, portable, and int(text) remains sufficient for replay.
        if key == "block_seed":
            values = [str(value) if value is not None else None for value in values]
            out[key] = pd.Series(values, index=out.index, dtype="string")
        else:
            out[key] = pd.Series(values, index=out.index)
    out["success"] = out["outcome"].astype(str).eq("succeeded")
    out["rejected_429"] = (~out["success"]) & out.get(
        "retry_reason", pd.Series("", index=out.index)
    ).fillna("").astype(str).str.contains("429")
    cost = pd.to_numeric(out.get("cost_usd"), errors="coerce")
    # Failed 429s have no generation and no observed charge.  Successful rows
    # with missing generation accounting stay missing rather than being imputed.
    out["observed_spend_usd"] = cost.where(out["success"], 0.0)
    out["policy_order"] = pd.to_numeric(out["policy_order"], errors="coerce")
    out["quoted_rank"] = pd.to_numeric(out["quoted_rank"], errors="coerce")
    for column in (
        "public_quote_cost_cap_usd",
        "quote_cap_input_tokens",
        "request_timeout_ms",
    ):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.dropna(subset=["observed_ts", "model_id"])


def _explicit_blocks(rows: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()
    keep: list[pd.DataFrame] = []
    for block_id, block in rows.groupby("block_id", sort=False):
        if not block_id or pd.isna(block_id):
            continue
        block = block.sort_values("observed_ts").copy()
        if block["policy_order"].isna().any():
            block["policy_order"] = np.arange(len(block))
        block["block_source"] = source
        block["block_complete"] = (
            len(block) == len(POLICIES)
            and not block["policy"].duplicated().any()
            and not block["policy_order"].duplicated().any()
            and set(block["policy"]) == set(POLICIES)
        )
        block["block_span_seconds"] = (
            block["observed_ts"].max() - block["observed_ts"].min()
        ).total_seconds()
        block["assignment_verified"] = _verify_assignment(block)
        block["first_assignment_verified"] = _verify_first_assignment(block)
        keep.append(block)
    return pd.concat(keep, ignore_index=True) if keep else rows.iloc[0:0].copy()


def _verify_assignment(block: pd.DataFrame) -> bool:
    """Replay the published seed for complete four-policy v2 blocks."""
    if block["policy"].duplicated().any() or block["policy_order"].duplicated().any():
        return False
    try:
        seed = int(block["block_seed"].iloc[0])
        n_quoted = int(block["n_quoted"].dropna().iloc[0])
        policy_count = int(block["block_policy_count"].dropna().iloc[0])
    except (IndexError, TypeError, ValueError):
        return False
    if policy_count != len(POLICIES) or n_quoted < 3:
        return False
    rng = random.Random(seed)
    expected_random_rank = rng.choice(range(2, n_quoted))
    expected = list(POLICIES)
    rng.shuffle(expected)
    for _, row in block.iterrows():
        position = int(row["policy_order"])
        if position >= len(expected) or str(row["policy"]) != expected[position]:
            return False
    if set(block["policy"]) == set(POLICIES):
        try:
            actual_random_rank = int(
                block.loc[block["policy"].eq("pinned_random"), "quoted_rank"].iloc[0]
            )
        except (IndexError, TypeError, ValueError):
            return False
        return actual_random_rank == expected_random_rank
    return True


def _verify_first_assignment(block: pd.DataFrame) -> bool:
    """Replay only position zero, the preregistered carryover-robust unit."""
    try:
        seed = int(block["block_seed"].iloc[0])
        n_quoted = int(block["n_quoted"].dropna().iloc[0])
        policy_count = int(block["block_policy_count"].dropna().iloc[0])
    except (IndexError, TypeError, ValueError):
        return False
    if policy_count != len(POLICIES) or n_quoted < 3:
        return False
    first = block[pd.to_numeric(block["policy_order"], errors="coerce").eq(0)]
    if len(first) != 1:
        return False
    rng = random.Random(seed)
    rng.choice(range(2, n_quoted))
    expected = list(POLICIES)
    rng.shuffle(expected)
    return str(first["policy"].iloc[0]) == expected[0]


def construct_probe_blocks(
    attempts: pd.DataFrame, max_legacy_seconds: int = MAX_LEGACY_BLOCK_SECONDS
) -> pd.DataFrame:
    """Construct explicit v2 blocks and conservative legacy v1 blocks."""
    frame = prepare_attempts(attempts)
    if frame.empty:
        return frame

    explicit = frame[frame["block_id"].notna() & frame["block_id"].astype(bool)].copy()
    explicit = _explicit_blocks(explicit, source="explicit_assignment")

    legacy_rows: list[pd.DataFrame] = []
    legacy = frame[frame["block_id"].isna() & frame["study_id"].astype(str).eq(LEGACY_STUDY_ID)]
    for _model_id, model in legacy.groupby("model_id", sort=False):
        model = model.sort_values("observed_ts")
        current: list[pd.Series] = []
        for _, row in model.iterrows():
            if row["policy"] == "openrouter_default":
                if current:
                    candidate = pd.DataFrame(current)
                    if set(candidate["policy"]) == set(POLICIES):
                        legacy_rows.append(candidate)
                current = [row]
            elif current:
                age = (row["observed_ts"] - current[0]["observed_ts"]).total_seconds()
                if age <= max_legacy_seconds and row["policy"] not in {
                    item["policy"] for item in current
                }:
                    current.append(row)
        if current:
            candidate = pd.DataFrame(current)
            if set(candidate["policy"]) == set(POLICIES):
                legacy_rows.append(candidate)

    legacy_blocks: list[pd.DataFrame] = []
    for candidate in legacy_rows:
        candidate = candidate.sort_values("observed_ts").copy()
        span = (candidate["observed_ts"].max() - candidate["observed_ts"].min()).total_seconds()
        if span > max_legacy_seconds or candidate["policy"].duplicated().any():
            continue
        default = candidate[candidate["policy"] == "openrouter_default"].iloc[0]
        candidate["block_id"] = f"legacy|{default['model_id']}|{default['event_id']}"
        # Use actual temporal position; this exposes the fixed-order confound.
        candidate["policy_order"] = np.arange(len(candidate))
        candidate["block_source"] = "legacy_time_match"
        candidate["block_complete"] = True
        candidate["block_span_seconds"] = span
        candidate["randomized_order"] = False
        candidate["assignment_verified"] = False
        candidate["first_assignment_verified"] = False
        legacy_blocks.append(candidate)
    legacy_frame = (
        pd.concat(legacy_blocks, ignore_index=True) if legacy_blocks else frame.iloc[0:0].copy()
    )
    blocks = pd.concat([legacy_frame, explicit], ignore_index=True)
    if blocks.empty:
        return blocks

    # Label the default provider's public-rank match within each block.
    rank_labels: dict[str, str] = {}
    for block_id, block in blocks.groupby("block_id"):
        default_rows = block.loc[block["policy"].eq("openrouter_default"), "selected_provider"]
        default_provider = default_rows.iloc[0] if len(default_rows) else None
        label = (
            "unobserved_default_provider"
            if pd.isna(default_provider)
            else "other_quoted_or_unmatched"
        )
        if pd.notna(default_provider):
            pinned = block[block["policy"].str.startswith("pinned")]
            match = pinned[pinned["requested_provider"].eq(default_provider)]
            if not match.empty:
                label = str(match.iloc[0]["policy"]).replace("pinned_", "")
        rank_labels[str(block_id)] = label
    blocks["default_selected_quote_class"] = blocks["block_id"].astype(str).map(rank_labels)
    default_times = blocks.groupby("block_id")["observed_ts"].min().dt.floor("h").astype(str)
    # The legacy job starts once per hour and covers four models.  Hour is the
    # conservative common-shock cluster for inference across those four blocks.
    blocks["cycle_id"] = blocks["block_id"].map(default_times)
    return blocks.sort_values(["observed_ts", "model_id", "policy_order"]).reset_index(drop=True)


def normalized_order_entropy(blocks: pd.DataFrame) -> float | None:
    """Mean policy-position entropy divided by log(number of policies)."""
    if blocks.empty:
        return None
    entropies = []
    k = len(POLICIES)
    for _, group in blocks.groupby("policy"):
        p = group["policy_order"].value_counts(normalize=True).to_numpy(dtype=float)
        entropies.append(float(-(p * np.log(p)).sum() / math.log(k)))
    return float(np.mean(entropies))


def paired_contrasts(blocks: pd.DataFrame, *, bootstrap: int = 5000) -> pd.DataFrame:
    """Default-minus-pinned contrasts, clustering the bootstrap by probe cycle."""
    if blocks.empty:
        return pd.DataFrame()
    success = blocks.pivot(index="block_id", columns="policy", values="success")
    spend = blocks.pivot(index="block_id", columns="policy", values="observed_spend_usd")
    cycle = blocks.groupby("block_id")["cycle_id"].first()
    rows = []
    rng = np.random.default_rng(20260715)
    for policy in POLICIES[1:]:
        pair = success[["openrouter_default", policy]].dropna().astype(float)
        diff = pair["openrouter_default"] - pair[policy]
        n = len(diff)
        if n:
            grouped = (
                pd.DataFrame({"difference": diff, "cycle_id": cycle.reindex(diff.index)})
                .groupby("cycle_id")["difference"]
                .agg(["sum", "count"])
            )
            cluster_count = len(grouped)
            indices = rng.integers(0, cluster_count, size=(bootstrap, cluster_count))
            boot = grouped["sum"].to_numpy()[indices].sum(axis=1) / grouped["count"].to_numpy()[
                indices
            ].sum(axis=1)
            ci_low, ci_high = np.quantile(boot, [0.025, 0.975])
            favorable = int(((pair["openrouter_default"] == 1) & (pair[policy] == 0)).sum())
            adverse = int(((pair["openrouter_default"] == 0) & (pair[policy] == 1)).sum())
            discordant = favorable + adverse
            p_exact = float(binomtest(favorable, discordant, 0.5).pvalue) if discordant else 1.0
            cluster_sums = grouped["sum"].to_numpy(dtype=float)
            signs = rng.choice((-1.0, 1.0), size=(100_000, cluster_count))
            random_stats = np.abs((signs * cluster_sums).sum(axis=1) / n)
            cluster_p = float((1 + (random_stats >= abs(diff.mean()) - 1e-15).sum()) / 100_001)
        else:
            ci_low = ci_high = p_exact = np.nan
            favorable = adverse = 0
            cluster_count = 0
            cluster_p = np.nan
        spend_pair = spend[["openrouter_default", policy]].dropna()
        spend_diff = (
            float((spend_pair["openrouter_default"] - spend_pair[policy]).mean())
            if len(spend_pair)
            else np.nan
        )
        success_diff = float(diff.mean()) if n else np.nan
        threshold = (
            spend_diff / success_diff if success_diff > 0 and np.isfinite(spend_diff) else np.nan
        )
        rows.append(
            {
                "comparison": f"openrouter_default_minus_{policy}",
                "n_blocks": n,
                "n_hourly_clusters": cluster_count,
                "default_success_rate": float(pair["openrouter_default"].mean()) if n else np.nan,
                "comparison_success_rate": float(pair[policy].mean()) if n else np.nan,
                "success_difference": success_diff,
                "success_difference_ci_low": float(ci_low),
                "success_difference_ci_high": float(ci_high),
                "discordant_default_only_success": favorable,
                "discordant_pinned_only_success": adverse,
                "mcnemar_exact_p": p_exact,
                "hour_cluster_signflip_p": cluster_p,
                "n_observed_spend_pairs": int(len(spend_pair)),
                "observed_spend_difference_usd": spend_diff,
                "break_even_value_per_success_usd": float(threshold),
            }
        )
    return pd.DataFrame(rows)


def policy_panel(blocks: pd.DataFrame) -> pd.DataFrame:
    if blocks.empty:
        return pd.DataFrame()
    rows = []
    for (source, policy), group in blocks.groupby(["block_source", "policy"]):
        successes = int(group["success"].sum())
        low, high = proportion_confint(successes, len(group), alpha=0.05, method="wilson")
        rows.append(
            {
                "block_source": source,
                "policy": policy,
                "attempts": len(group),
                "successes": successes,
                "success_rate": successes / len(group),
                "success_ci_low": float(low),
                "success_ci_high": float(high),
                "rate_429": float(group["rejected_429"].mean()),
                "mean_observed_spend_usd": float(group["observed_spend_usd"].mean()),
                "mean_latency_ms_success": float(
                    pd.to_numeric(group.loc[group["success"], "latency_ms"], errors="coerce").mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def holm_adjust(pvalues: list[float]) -> list[float]:
    """Holm step-down adjusted p-values in original order."""
    if not pvalues:
        return []
    values = np.asarray(pvalues, dtype=float)
    adjusted = np.full(len(values), np.nan, dtype=float)
    finite = np.flatnonzero(np.isfinite(values))
    order = finite[np.argsort(values[finite])]
    running = 0.0
    m = len(finite)
    for rank, index in enumerate(order):
        running = max(running, (m - rank) * values[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def first_balanced_prefix(
    frame: pd.DataFrame,
    policies: tuple[str, ...],
    min_per_policy: int,
) -> tuple[pd.DataFrame, bool, str | None]:
    """Freeze the earliest chronological prefix satisfying the balance gate."""
    if frame.empty:
        return frame.copy(), False, None
    sort_columns = [
        column for column in ("observed_ts", "observed_at", "run_ts", "block_id") if column in frame
    ]
    ordered = frame.sort_values(sort_columns, kind="stable").reset_index(drop=True)
    counts = {policy: 0 for policy in policies}
    minimum_total = len(policies) * min_per_policy
    for position, policy in enumerate(ordered["policy"].astype(str)):
        if policy in counts:
            counts[policy] += 1
        if position + 1 >= minimum_total and min(counts.values()) >= min_per_policy:
            cutoff_column = next(
                (
                    column
                    for column in ("observed_ts", "observed_at", "run_ts", "block_id")
                    if column in ordered
                ),
                None,
            )
            cutoff = str(ordered.loc[position, cutoff_column]) if cutoff_column else None
            return ordered.iloc[: position + 1].copy(), True, cutoff
    return ordered, False, None


def arm_missingness_bounds(arm: pd.DataFrame, *, total_blocks: int) -> dict[str, Any]:
    """Bound H80 secondary means without conditioning the primary ITT sample."""
    n = len(arm)
    policy = str(arm["policy"].iloc[0]) if n else ""
    spend = pd.to_numeric(
        arm.get("observed_spend_usd", pd.Series(index=arm.index, dtype=float)),
        errors="coerce",
    )
    quote_cap = pd.to_numeric(
        arm.get("public_quote_cost_cap_usd", pd.Series(index=arm.index, dtype=float)),
        errors="coerce",
    )
    if policy == "openrouter_default":
        quote_cap[:] = np.nan
    spend_bounds = bounded_mean(spend, lower=0.0, upper=quote_cap)
    ht_spend_bounds = ht_bounded_mean(
        spend,
        pd.to_numeric(
            arm.get(
                "assignment_probability_first",
                pd.Series(index=arm.index, dtype=float),
            ),
            errors="coerce",
        ),
        total_blocks=total_blocks,
        lower=0.0,
        upper=quote_cap,
    )

    successful = arm[arm["success"].astype(bool)] if n else arm
    latency = pd.to_numeric(
        successful.get("latency_ms", pd.Series(index=successful.index, dtype=float)),
        errors="coerce",
    )
    timeout = pd.to_numeric(
        successful.get(
            "request_timeout_ms",
            pd.Series(60_000.0, index=successful.index, dtype=float),
        ),
        errors="coerce",
    ).fillna(60_000.0)
    latency_bounds = bounded_mean(latency, lower=0.0, upper=timeout)
    selected = successful.get(
        "selected_provider", pd.Series(index=successful.index, dtype="string")
    ).astype("string")
    selected_missing = selected.fillna("").eq("")
    return {
        "spend_observed": spend_bounds["observed"],
        "spend_missing": spend_bounds["missing"],
        "spend_mean_lower_bound_usd": spend_bounds["mean_lower_bound"],
        "spend_mean_upper_bound_usd": spend_bounds["mean_upper_bound"],
        "ht_spend_mean_lower_bound_usd": ht_spend_bounds["mean_lower_bound"],
        "ht_spend_mean_upper_bound_usd": ht_spend_bounds["mean_upper_bound"],
        "spend_upper_support_complete_for_missing": spend_bounds[
            "upper_support_complete_for_missing"
        ],
        "spend_observed_upper_support_violations": spend_bounds[
            "observed_upper_support_violations"
        ],
        "successful_latency_observed": latency_bounds["observed"],
        "successful_latency_missing": latency_bounds["missing"],
        "successful_latency_mean_lower_bound_ms": latency_bounds["mean_lower_bound"],
        "successful_latency_mean_upper_bound_ms": latency_bounds["mean_upper_bound"],
        "selected_provider_observed_successes": int((~selected_missing).sum()),
        "selected_provider_missing_successes": int(selected_missing.sum()),
        "selected_provider_observation_rate_success": (
            float((~selected_missing).mean()) if len(successful) else None
        ),
    }


def randomized_support_diagnostics(first_positions: pd.DataFrame) -> dict[str, Any]:
    """Describe repeated model/time support without reading probe outcomes."""
    if first_positions.empty:
        return {
            "blocks": 0,
            "unique_models": 0,
            "hour_clusters": 0,
            "span_hours": 0.0,
        }
    counts = first_positions["model_id"].astype(str).value_counts()
    shares = counts.to_numpy(dtype=float) / counts.sum()
    observed_raw = first_positions.get(
        "observed_ts",
        first_positions.get("observed_at", pd.Series(pd.NaT, index=first_positions.index)),
    )
    observed = pd.Series(
        pd.to_datetime(observed_raw, errors="coerce", utc=True),
        index=first_positions.index,
    )
    span_hours = (
        float((observed.max() - observed.min()).total_seconds() / 3600)
        if observed.notna().sum() >= 2
        else 0.0
    )
    return {
        "blocks": int(len(first_positions)),
        "unique_models": int(len(counts)),
        "hour_clusters": int(observed.dt.floor("h").nunique()),
        "span_hours": span_hours,
        "model_block_counts": {str(key): int(value) for key, value in counts.items()},
        "model_support_dominance": float(shares.max()),
        "effective_model_count": float(1.0 / np.square(shares).sum()),
        "normalized_model_entropy": (
            float(-(shares * np.log(shares)).sum() / math.log(len(shares)))
            if len(shares) > 1
            else 0.0
        ),
        "claim_boundary": (
            "Support describes dynamically selected hot models observed by this account. "
            "Repeated model-hour blocks do not expand the target population to all models "
            "or other accounts."
        ),
    }


def randomized_first_position_analysis(
    blocks: pd.DataFrame, *, simulations: int = RANDOMIZATION_DRAWS
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Design-based v2 ITT estimates using only audited position-zero rows.

    Under the sharp null, each observed first-position outcome can be assigned
    to any of the four policies.  Monte Carlo randomization inference therefore
    conditions on the full vector of outcomes and does not require independent
    outcome shocks across models in the same hourly run.
    """
    if blocks.empty:
        valid = blocks.copy()
    else:
        verification_column = (
            "first_assignment_verified"
            if "first_assignment_verified" in blocks
            else "assignment_verified"
        )
        valid = blocks[
            blocks["block_source"].eq("explicit_assignment")
            & blocks["study_id"].astype(str).eq(RANDOMIZED_STUDY_ID)
            & blocks[verification_column].astype(bool)
            & pd.to_numeric(blocks["policy_order"], errors="coerce").eq(0)
            & blocks["randomized_order"].astype(bool)
        ].copy()
    valid = valid.sort_values("block_id").drop_duplicates("block_id", keep="first")
    collection_valid = valid.copy()
    valid, release_ready, confirmatory_cutoff = first_balanced_prefix(
        collection_valid, POLICIES, MIN_FIRST_POSITION_PER_POLICY
    )
    n_blocks = len(valid)

    panel_rows = []
    for policy in POLICIES:
        arm = valid[valid["policy"].eq(policy)]
        n = len(arm)
        successes = int(arm["success"].sum())
        low, high = (
            proportion_confint(successes, n, alpha=0.05, method="wilson") if n else (np.nan, np.nan)
        )
        probabilities = pd.to_numeric(arm["assignment_probability_first"], errors="coerce")
        ht_success = (
            float((arm["success"].astype(float) / probabilities).sum() / n_blocks)
            if n_blocks and n and probabilities.notna().all()
            else np.nan
        )
        missingness = arm_missingness_bounds(arm, total_blocks=n_blocks)
        panel_rows.append(
            {
                "policy": policy,
                "first_position_attempts": n,
                "successes": successes,
                "success_rate": successes / n if n else np.nan,
                "success_ci_low": float(low),
                "success_ci_high": float(high),
                "ht_success_mean": ht_success,
                "rate_429": float(arm["rejected_429"].mean()) if n else np.nan,
                **missingness,
                "mean_observed_spend_usd": (
                    float(arm["observed_spend_usd"].mean())
                    if n and missingness["spend_missing"] == 0
                    else np.nan
                ),
            }
        )
    panel = pd.DataFrame(panel_rows)

    model_rows = []
    for (model_id, policy), arm in valid.groupby(["model_id", "policy"], sort=True):
        probabilities = pd.to_numeric(arm["assignment_probability_first"], errors="coerce")
        model_blocks = int(valid["model_id"].eq(model_id).sum())
        successes = int(arm["success"].sum())
        model_rows.append(
            {
                "model_id": model_id,
                "policy": policy,
                "model_blocks": model_blocks,
                "first_position_attempts": len(arm),
                "successes": successes,
                "success_rate": successes / len(arm),
                "ht_success_mean_within_model": (
                    float((arm["success"].astype(float) / probabilities).sum() / model_blocks)
                    if model_blocks and probabilities.notna().all()
                    else np.nan
                ),
                "rate_429": float(arm["rejected_429"].mean()),
                "spend_missing": int(arm["observed_spend_usd"].isna().sum()),
            }
        )
    model_panel = pd.DataFrame(model_rows)

    contrast_rows = []
    if n_blocks:
        observed_outcomes = valid["success"].astype(float).to_numpy()
        labels = np.random.default_rng(20260715).integers(
            0,
            len(POLICIES),
            size=(simulations, n_blocks),
            dtype=np.int8,
        )
    else:
        observed_outcomes = np.array([], dtype=float)
        labels = np.empty((0, 0), dtype=np.int8)
    for policy_index, policy in enumerate(POLICIES[1:], start=1):
        default = valid[valid["policy"].eq("openrouter_default")]
        pinned = valid[valid["policy"].eq(policy)]
        nd, npin = len(default), len(pinned)
        raw_difference = (
            float(default["success"].mean() - pinned["success"].mean()) if nd and npin else np.nan
        )
        if nd and npin:
            ci_low, ci_high = confint_proportions_2indep(
                int(default["success"].sum()),
                nd,
                int(pinned["success"].sum()),
                npin,
                method="newcomb",
                compare="diff",
                alpha=0.05,
            )
        else:
            ci_low = ci_high = np.nan

        probability = 1.0 / len(POLICIES)
        observed_ht = (
            float(
                (
                    (valid["policy"].eq("openrouter_default").to_numpy() * observed_outcomes)
                    / probability
                    - (valid["policy"].eq(policy).to_numpy() * observed_outcomes) / probability
                ).sum()
                / n_blocks
            )
            if n_blocks
            else np.nan
        )
        if n_blocks and simulations:
            simulated = (
                (labels == 0) * observed_outcomes[None, :] / probability
                - (labels == policy_index) * observed_outcomes[None, :] / probability
            ).sum(axis=1) / n_blocks
            p_greater = float((1 + (simulated >= observed_ht - 1e-15).sum()) / (simulations + 1))
            p_two_sided = float(
                (1 + (np.abs(simulated) >= abs(observed_ht) - 1e-15).sum()) / (simulations + 1)
            )
        else:
            p_greater = p_two_sided = np.nan

        default_spend_complete = bool(nd and default["observed_spend_usd"].notna().all())
        pinned_spend_complete = bool(npin and pinned["observed_spend_usd"].notna().all())
        spend_difference = (
            float(default["observed_spend_usd"].mean() - pinned["observed_spend_usd"].mean())
            if default_spend_complete and pinned_spend_complete
            else np.nan
        )
        threshold = (
            spend_difference / raw_difference
            if raw_difference > 0 and np.isfinite(spend_difference)
            else np.nan
        )
        default_missingness = arm_missingness_bounds(default, total_blocks=n_blocks)
        pinned_missingness = arm_missingness_bounds(pinned, total_blocks=n_blocks)
        spend_bound_low, spend_bound_high = difference_bounds(
            {
                "mean_lower_bound": default_missingness["spend_mean_lower_bound_usd"],
                "mean_upper_bound": default_missingness["spend_mean_upper_bound_usd"],
            },
            {
                "mean_lower_bound": pinned_missingness["spend_mean_lower_bound_usd"],
                "mean_upper_bound": pinned_missingness["spend_mean_upper_bound_usd"],
            },
        )
        ht_spend_bound_low, ht_spend_bound_high = difference_bounds(
            {
                "mean_lower_bound": default_missingness["ht_spend_mean_lower_bound_usd"],
                "mean_upper_bound": default_missingness["ht_spend_mean_upper_bound_usd"],
            },
            {
                "mean_lower_bound": pinned_missingness["ht_spend_mean_lower_bound_usd"],
                "mean_upper_bound": pinned_missingness["ht_spend_mean_upper_bound_usd"],
            },
        )
        latency_bound_low, latency_bound_high = difference_bounds(
            {
                "mean_lower_bound": default_missingness["successful_latency_mean_lower_bound_ms"],
                "mean_upper_bound": default_missingness["successful_latency_mean_upper_bound_ms"],
            },
            {
                "mean_lower_bound": pinned_missingness["successful_latency_mean_lower_bound_ms"],
                "mean_upper_bound": pinned_missingness["successful_latency_mean_upper_bound_ms"],
            },
        )
        default_provider_rate = default_missingness["selected_provider_observation_rate_success"]
        pinned_provider_rate = pinned_missingness["selected_provider_observation_rate_success"]
        contrast_rows.append(
            {
                "comparison": f"openrouter_default_minus_{policy}",
                "n_blocks": n_blocks,
                "default_n": nd,
                "pinned_n": npin,
                "success_difference_hajek": raw_difference,
                "success_difference_ci_low": float(ci_low),
                "success_difference_ci_high": float(ci_high),
                "success_difference_ht": observed_ht,
                "randomization_p_greater": p_greater,
                "randomization_p_two_sided": p_two_sided,
                "spend_complete_both_arms": (default_spend_complete and pinned_spend_complete),
                "observed_spend_difference_usd": spend_difference,
                "spend_difference_lower_bound_usd": spend_bound_low,
                "spend_difference_upper_bound_usd": spend_bound_high,
                "ht_spend_difference_lower_bound_usd": ht_spend_bound_low,
                "ht_spend_difference_upper_bound_usd": ht_spend_bound_high,
                "successful_latency_difference_lower_bound_ms": latency_bound_low,
                "successful_latency_difference_upper_bound_ms": latency_bound_high,
                "selected_provider_observation_rate_difference": (
                    float(default_provider_rate - pinned_provider_rate)
                    if default_provider_rate is not None and pinned_provider_rate is not None
                    else np.nan
                ),
                "break_even_value_per_success_usd": float(threshold),
            }
        )
    contrasts = pd.DataFrame(contrast_rows)
    if len(contrasts):
        contrasts["holm_p_greater"] = holm_adjust(contrasts["randomization_p_greater"].tolist())

    analysis_counts = panel.set_index("policy")["first_position_attempts"].reindex(
        POLICIES, fill_value=0
    )
    collection_counts = collection_valid["policy"].value_counts().reindex(POLICIES, fill_value=0)
    min_count = int(collection_counts.min()) if len(collection_counts) else 0
    candidate = blocks.iloc[0:0].copy()
    if not blocks.empty:
        candidate = blocks[
            blocks["block_source"].eq("explicit_assignment")
            & blocks["study_id"].astype(str).eq(RANDOMIZED_STUDY_ID)
            & pd.to_numeric(blocks["policy_order"], errors="coerce").eq(0)
            & blocks["randomized_order"].astype(bool)
        ].copy()
    candidate_unique = candidate.drop_duplicates("block_id", keep="first")
    verification_column = (
        "first_assignment_verified"
        if "first_assignment_verified" in candidate_unique
        else "assignment_verified"
    )
    replay_passes = int(candidate_unique[verification_column].astype(bool).sum())
    audit = {
        "study_id": RANDOMIZED_STUDY_ID,
        "valid_position_zero_blocks": n_blocks,
        "candidate_position_zero_blocks": int(len(candidate_unique)),
        "assignment_replay_passes": replay_passes,
        "assignment_replay_rate": (
            replay_passes / len(candidate_unique) if len(candidate_unique) else None
        ),
        "first_position_counts": {key: int(value) for key, value in collection_counts.items()},
        "confirmatory_prefix_counts": {key: int(value) for key, value in analysis_counts.items()},
        "confirmatory_prefix_blocks": n_blocks if release_ready else 0,
        "confirmatory_cutoff": confirmatory_cutoff,
        "outcomes_released": release_ready,
        "models_represented": (
            int(collection_valid["model_id"].nunique()) if len(collection_valid) else 0
        ),
        "model_ids": (
            sorted(collection_valid["model_id"].astype(str).unique().tolist())
            if len(collection_valid) and "model_id" in collection_valid
            else []
        ),
        "support_diagnostics": randomized_support_diagnostics(collection_valid),
        "min_first_position_per_policy": min_count,
        "target_per_policy": MIN_FIRST_POSITION_PER_POLICY,
        "randomization_draws": simulations,
        "primary_multiplicity": "Holm adjustment over three one-sided default-greater contrasts",
        "evidence_status": (
            "randomized_first_position_ready"
            if release_ready
            else "randomized_first_position_power_gated"
        ),
        "identification": (
            "First-position HT differences are design-unbiased before within-block probe "
            "exposure. Hajek differences and Newcombe intervals are companion estimates; "
            "later-position crossover comparisons require carryover controls."
        ),
    }
    if not release_ready:
        for column in panel.columns:
            if column not in {"policy", "first_position_attempts"}:
                panel[column] = np.nan
        for column in model_panel.columns:
            if column not in {
                "model_id",
                "policy",
                "model_blocks",
                "first_position_attempts",
            }:
                model_panel[column] = np.nan
        for column in contrasts.columns:
            if column not in {"comparison", "n_blocks", "default_n", "pinned_n"}:
                contrasts[column] = np.nan
    return panel, model_panel, contrasts, audit


def _plot(panel: pd.DataFrame, out_dir: Path) -> None:
    if panel.empty:
        return
    import matplotlib.pyplot as plt

    legacy = panel[panel["block_source"].eq("legacy_time_match")].set_index("policy")
    if legacy.empty:
        return
    legacy = legacy.reindex(POLICIES)
    y = legacy["success_rate"].to_numpy()
    err = np.vstack(
        [y - legacy["success_ci_low"].to_numpy(), legacy["success_ci_high"].to_numpy() - y]
    )
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    colors = ["#2f6f9f", "#d77a2b", "#b54d4d", "#7c6baa"]
    ax.bar(range(len(POLICIES)), y, yerr=err, capsize=4, color=colors)
    ax.set_xticks(range(len(POLICIES)), ["Default", "Cheapest", "Second", "Random"])
    ax.set_ylabel("Probe success probability")
    ax.set_ylim(0, 1.08)
    ax.set_title("Matched public-quote firmness (legacy fixed-order blocks)")
    ax.text(
        0.01,
        -0.23,
        "Wilson 95% intervals. Descriptive only: default was always first; "
        "pinned arms disabled fallbacks.",
        transform=ax.transAxes,
        fontsize=8.5,
    )
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h80_quote_firmness.png", dpi=180)
    fig.savefig(out_dir / "h80_quote_firmness.pdf")
    plt.close(fig)


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    attempts = data.q(
        f"""
        select *
        from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
        """
    ).df()
    blocks = construct_probe_blocks(attempts)
    panel = policy_panel(blocks)
    legacy = blocks[blocks["block_source"].eq("legacy_time_match")]
    contrasts = paired_contrasts(legacy)
    save(blocks, out_dir, "h80_probe_blocks")
    save(panel, out_dir, "h80_policy_panel")
    save(contrasts, out_dir, "h80_pairwise_contrasts")
    randomized_panel, randomized_model_panel, randomized_contrasts, randomized = (
        randomized_first_position_analysis(blocks)
    )
    save(randomized_panel, out_dir, "h80_randomized_first_position")
    save(randomized_model_panel, out_dir, "h80_randomized_model_policy")
    save(randomized_contrasts, out_dir, "h80_randomized_contrasts")
    _plot(panel, out_dir)

    explicit = blocks[blocks["block_source"].eq("explicit_assignment")]
    order_audit = {
        "legacy_normalized_order_entropy": normalized_order_entropy(legacy),
        "randomized_normalized_order_entropy": normalized_order_entropy(explicit),
        "legacy_default_first_share": (
            float(legacy[legacy["policy"].eq("openrouter_default")]["policy_order"].eq(0).mean())
            if len(legacy)
            else None
        ),
    }
    default_classes = (
        legacy.groupby("block_id")["default_selected_quote_class"].first().value_counts().to_dict()
        if len(legacy)
        else {}
    )
    randomized["complete_randomized_blocks"] = (
        int(explicit.loc[explicit["block_complete"].astype(bool), "block_id"].nunique())
        if len(explicit)
        else 0
    )
    summary = {
        "evidence_status": (
            "randomized_first_position_ready"
            if randomized["evidence_status"] == "randomized_first_position_ready"
            else "matched_descriptive_fixed_order"
        ),
        "attempts_read": int(len(prepare_attempts(attempts))),
        "complete_legacy_blocks": int(legacy["block_id"].nunique()) if len(legacy) else 0,
        "legacy_models": int(legacy["model_id"].nunique()) if len(legacy) else 0,
        "legacy_median_block_span_seconds": (
            float(legacy.groupby("block_id")["block_span_seconds"].first().median())
            if len(legacy)
            else None
        ),
        "order_audit": order_audit,
        "default_selected_quote_class": {
            str(key): int(value) for key, value in default_classes.items()
        },
        "legacy_pairwise_contrasts": contrasts.to_dict("records"),
        "randomized_first_position": randomized,
        "estimand": (
            "For policy p and value v per successful response, Delta U_p(v) = "
            "v * Delta success_p - Delta observed spend_p. The reported break-even value is "
            "Delta spend_p / Delta success_p when the default success advantage is positive."
        ),
        "claim_boundary": (
            "Legacy v1 contrasts are matched but not causal: default is always first, pinned "
            "arms disable fallbacks, and this account's 429 state may not represent other users. "
            "A public quote is an eligibility advertisement, not a firm executable offer. "
            "Only the v2 first-position randomization identifies a policy contrast under "
            "arbitrary post-first probe interference."
        ),
    }
    save_json(summary, out_dir, "h80_summary")
    return summary
