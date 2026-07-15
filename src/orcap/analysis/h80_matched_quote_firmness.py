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
from statsmodels.stats.proportion import proportion_confint

from . import data
from .common import DEFAULT_OUT, save, save_json

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
        "quoted_rank",
        "n_quoted",
    ):
        out[key] = meta.map(lambda item, k=key: item.get(k))
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
    return out.dropna(subset=["observed_ts", "model_id"])


def _explicit_blocks(rows: pd.DataFrame, *, source: str) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()
    keep: list[pd.DataFrame] = []
    for block_id, block in rows.groupby("block_id", sort=False):
        if not block_id or pd.isna(block_id):
            continue
        if block["policy"].duplicated().any():
            continue
        block = block.sort_values("observed_ts").copy()
        if block["policy_order"].isna().any():
            block["policy_order"] = np.arange(len(block))
        if block["policy_order"].duplicated().any():
            continue
        block["block_source"] = source
        block["block_complete"] = set(block["policy"]) == set(POLICIES)
        block["block_span_seconds"] = (
            block["observed_ts"].max() - block["observed_ts"].min()
        ).total_seconds()
        block["assignment_verified"] = _verify_assignment(block)
        keep.append(block)
    return pd.concat(keep, ignore_index=True) if keep else rows.iloc[0:0].copy()


def _verify_assignment(block: pd.DataFrame) -> bool:
    """Replay the published seed for complete four-policy v2 blocks."""
    try:
        seed = int(block["block_seed"].iloc[0])
        n_quoted = int(block["n_quoted"].dropna().iloc[0])
    except (IndexError, TypeError, ValueError):
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


def _first_position_audit(blocks: pd.DataFrame) -> dict[str, Any]:
    explicit = blocks[
        blocks["block_source"].eq("explicit_assignment")
        & blocks["study_id"].astype(str).eq(RANDOMIZED_STUDY_ID)
        & blocks["assignment_verified"].astype(bool)
    ]
    first = explicit[pd.to_numeric(explicit["policy_order"], errors="coerce").eq(0)]
    counts = first["policy"].value_counts().reindex(POLICIES, fill_value=0)
    rates = first.groupby("policy")["success"].mean().reindex(POLICIES)
    min_count = int(counts.min()) if len(counts) else 0
    return {
        "study_id": RANDOMIZED_STUDY_ID,
        "valid_position_zero_blocks": int(first["block_id"].nunique()),
        "complete_randomized_blocks": int(
            explicit.loc[explicit["block_complete"].astype(bool), "block_id"].nunique()
        ),
        "first_position_counts": {key: int(value) for key, value in counts.items()},
        "first_position_success_rates": {
            key: (None if pd.isna(value) else float(value)) for key, value in rates.items()
        },
        "min_first_position_per_policy": min_count,
        "target_per_policy": MIN_FIRST_POSITION_PER_POLICY,
        "evidence_status": (
            "randomized_first_position_ready"
            if min_count >= MIN_FIRST_POSITION_PER_POLICY
            else "randomized_first_position_power_gated"
        ),
        "identification": (
            "First-position differences are randomized policy effects before any within-block "
            "probe exposure. Later-position crossover comparisons require carryover controls."
        ),
    }


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
    randomized = _first_position_audit(blocks)
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
