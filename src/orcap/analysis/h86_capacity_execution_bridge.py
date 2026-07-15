"""H86 — transport public capacity state to owned pinned execution.

The design is frozen in
``docs/h86-h87-capacity-state-execution-preregistration.md``.  H86 reuses only
the already-public legacy H80 pilot and never reads prospective H80/H81/H87
outcomes.  It is a retrospective, predictive bridge rather than a causal
capacity estimate.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h80_matched_quote_firmness import (
    LEGACY_STUDY_ID,
    construct_probe_blocks,
)
from .h82_enforcement_substitution import (
    canonical_panel,
    discovery_panel,
    load_rows,
)

PINNED_POLICIES = ("pinned_cheapest", "pinned_second", "pinned_random")
MAX_ASOF_MINUTES = 10.0
PRICE_CALIPER_RATIO = 1.25
BOOTSTRAP_DRAWS = 10_000
PERMUTATION_DRAWS = 10_000
RANDOM_SEED = 86_870_715


def public_provider_states(rows: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the immutable H84 endpoint panel to exact-name provider state."""
    panel = discovery_panel(canonical_panel(rows))
    if panel.empty:
        return pd.DataFrame()
    frame = panel.copy()
    frame["price_completion"] = pd.to_numeric(
        frame["price_completion"], errors="coerce"
    )
    frame["capacity_ceiling_rpm"] = pd.to_numeric(
        frame["capacity_ceiling_rpm"], errors="coerce"
    )
    frame["recent_peak_rpm"] = pd.to_numeric(
        frame["recent_peak_rpm"], errors="coerce"
    )
    price_ok = (
        frame["price_completion"].gt(0)
        & np.isfinite(frame["price_completion"])
    ).fillna(False)
    cap_ok = (
        frame["capacity_ceiling_rpm"].gt(0)
        & np.isfinite(frame["capacity_ceiling_rpm"])
    ).fillna(False)
    peak_ok = (
        cap_ok
        & frame["recent_peak_rpm"].ge(0)
        & np.isfinite(frame["recent_peak_rpm"])
    ).fillna(False)
    frame["_price"] = frame["price_completion"].where(price_ok)
    frame["_capacity"] = frame["capacity_ceiling_rpm"].where(cap_ok)
    frame["_peak"] = frame["recent_peak_rpm"].where(peak_ok)
    frame["_capacity_endpoint"] = cap_ok.astype(int)
    frame["_peak_endpoint"] = peak_ok.astype(int)
    frame["_deranked"] = frame["is_deranked"].fillna(False).astype(bool)

    keys = ["run_ts", "ts", "model_permaslug", "provider_name"]
    states = (
        frame.groupby(keys, dropna=False, sort=False)
        .agg(
            provider_price=("_price", "min"),
            provider_capacity_ceiling_rpm=("_capacity", lambda x: x.sum(min_count=1)),
            provider_recent_peak_rpm=("_peak", lambda x: x.sum(min_count=1)),
            provider_endpoint_count=("endpoint_uuid", "nunique"),
            capacity_endpoint_count=("_capacity_endpoint", "sum"),
            peak_endpoint_count=("_peak_endpoint", "sum"),
            public_is_deranked=("_deranked", "max"),
        )
        .reset_index()
    )
    ceiling = pd.to_numeric(states["provider_capacity_ceiling_rpm"], errors="coerce")
    peak = pd.to_numeric(states["provider_recent_peak_rpm"], errors="coerce")
    states["provider_capacity_load"] = np.where(ceiling.gt(0), peak / ceiling, np.nan)
    states["log1p_provider_capacity_ceiling_rpm"] = np.log1p(ceiling.clip(lower=0))
    group = states.groupby(["model_permaslug", "run_ts"], dropna=False)
    states["capacity_load_percentile"] = group["provider_capacity_load"].rank(
        method="average", pct=True
    )
    states["capacity_ceiling_percentile"] = group[
        "log1p_provider_capacity_ceiling_rpm"
    ].rank(method="average", pct=True)
    states["capacity_risk"] = (
        states["capacity_load_percentile"] - states["capacity_ceiling_percentile"]
    )
    states["snapshot_ts"] = pd.to_datetime(states["ts"], utc=True, errors="coerce")
    return states.sort_values(
        ["model_permaslug", "provider_name", "snapshot_ts"]
    ).reset_index(drop=True)


def legacy_pinned_attempts(attempts: pd.DataFrame) -> pd.DataFrame:
    """Return only complete legacy H80 pinned rows; prospective studies stay isolated."""
    blocks = construct_probe_blocks(attempts)
    if blocks.empty:
        return blocks
    return blocks[
        blocks["block_source"].eq("legacy_time_match")
        & blocks["study_id"].astype(str).eq(LEGACY_STUDY_ID)
        & blocks["policy"].isin(PINNED_POLICIES)
        & blocks["block_complete"].astype(bool)
    ].copy()


def attach_public_state(attempts: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    """Exact-name, backward-only, ten-minute as-of join."""
    out = attempts.copy()
    if out.empty:
        return out
    state_columns = [
        "run_ts",
        "snapshot_ts",
        "provider_price",
        "provider_capacity_ceiling_rpm",
        "provider_recent_peak_rpm",
        "provider_capacity_load",
        "capacity_load_percentile",
        "capacity_ceiling_percentile",
        "capacity_risk",
        "provider_endpoint_count",
        "capacity_endpoint_count",
        "peak_endpoint_count",
        "public_is_deranked",
    ]
    for column in state_columns:
        out[f"public_{column}"] = pd.NA
    out["public_join_status"] = "no_exact_model_provider"
    out["public_state_age_minutes"] = np.nan

    if states.empty:
        return out
    lookup: dict[tuple[str, str], pd.DataFrame] = {}
    valid_states = states.dropna(
        subset=["model_permaslug", "provider_name", "snapshot_ts"]
    )
    for key, group in valid_states.groupby(
        ["model_permaslug", "provider_name"], sort=False
    ):
        lookup[(str(key[0]), str(key[1]))] = group.sort_values("snapshot_ts")

    for index, row in out.iterrows():
        key = (str(row.get("model_id")), str(row.get("requested_provider")))
        candidates = lookup.get(key)
        if candidates is None or candidates.empty:
            continue
        observed = pd.to_datetime(row.get("observed_ts"), utc=True, errors="coerce")
        if pd.isna(observed):
            out.at[index, "public_join_status"] = "invalid_attempt_time"
            continue
        times = candidates["snapshot_ts"].to_numpy(dtype="datetime64[ns]")
        position = int(np.searchsorted(times, observed.to_datetime64(), side="right") - 1)
        if position < 0:
            out.at[index, "public_join_status"] = "no_prior_snapshot"
            continue
        selected = candidates.iloc[position]
        age = float((observed - selected["snapshot_ts"]).total_seconds() / 60)
        out.at[index, "public_state_age_minutes"] = age
        if age < 0 or age > MAX_ASOF_MINUTES:
            out.at[index, "public_join_status"] = "prior_snapshot_too_old"
            continue
        out.at[index, "public_join_status"] = "matched_exact_backward"
        for column in state_columns:
            out.at[index, f"public_{column}"] = selected.get(column)

    numeric = [
        "public_provider_price",
        "public_provider_capacity_ceiling_rpm",
        "public_provider_recent_peak_rpm",
        "public_provider_capacity_load",
        "public_capacity_load_percentile",
        "public_capacity_ceiling_percentile",
        "public_capacity_risk",
        "public_provider_endpoint_count",
        "public_capacity_endpoint_count",
        "public_peak_endpoint_count",
    ]
    for column in numeric:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["failure"] = ~out["success"].astype(bool)
    out["relative_log_public_price"] = np.nan
    positive = out["public_provider_price"].gt(0)
    out.loc[positive, "_log_public_price"] = np.log(
        out.loc[positive, "public_provider_price"]
    )
    out.loc[positive, "relative_log_public_price"] = out.loc[positive].groupby(
        "block_id"
    )["_log_public_price"].transform(lambda values: values - values.median())
    out = out.drop(columns=["_log_public_price"], errors="ignore")
    return out


def risk_pairs(joined: pd.DataFrame) -> pd.DataFrame:
    """Choose the unique highest- and lowest-risk observed providers per block."""
    rows: list[dict[str, Any]] = []
    matched = joined[
        joined["public_join_status"].eq("matched_exact_backward")
        & joined["public_capacity_risk"].notna()
    ]
    for block_id, block in matched.groupby("block_id", sort=False):
        if len(block) < 2:
            continue
        high_value = block["public_capacity_risk"].max()
        low_value = block["public_capacity_risk"].min()
        high = block[np.isclose(block["public_capacity_risk"], high_value)]
        low = block[np.isclose(block["public_capacity_risk"], low_value)]
        if high_value <= low_value or len(high) != 1 or len(low) != 1:
            continue
        h = high.iloc[0]
        low_row = low.iloc[0]
        h_price = float(h["public_provider_price"])
        l_price = float(low_row["public_provider_price"])
        price_ratio = max(h_price, l_price) / min(h_price, l_price)
        rows.append(
            {
                "block_id": block_id,
                "model_id": str(h["model_id"]),
                "block_ts": min(h["observed_ts"], low_row["observed_ts"]),
                "cluster": f"{h['model_id']}|{h['observed_ts'].strftime('%Y-%m-%d')}",
                "high_provider": h["requested_provider"],
                "low_provider": low_row["requested_provider"],
                "high_failure": float(h["failure"]),
                "low_failure": float(low_row["failure"]),
                "failure_difference": float(h["failure"]) - float(low_row["failure"]),
                "high_429": float(h["rejected_429"]),
                "low_429": float(low_row["rejected_429"]),
                "rate_429_difference": float(h["rejected_429"])
                - float(low_row["rejected_429"]),
                "risk_difference": float(h["public_capacity_risk"])
                - float(low_row["public_capacity_risk"]),
                "capacity_load_difference": float(h["public_provider_capacity_load"])
                - float(low_row["public_provider_capacity_load"]),
                "log_capacity_ceiling_difference": float(
                    np.log1p(h["public_provider_capacity_ceiling_rpm"])
                    - np.log1p(low_row["public_provider_capacity_ceiling_rpm"])
                ),
                "relative_log_price_difference": float(np.log(h_price) - np.log(l_price)),
                "price_ratio": price_ratio,
                "within_price_caliper": bool(price_ratio <= PRICE_CALIPER_RATIO),
                "quoted_rank_difference": float(h["quoted_rank"] - low_row["quoted_rank"]),
                "policy_order_difference": float(
                    h["policy_order"] - low_row["policy_order"]
                ),
                "successful_latency_high_ms": (
                    float(h["latency_ms"]) if h["success"] and pd.notna(h["latency_ms"]) else np.nan
                ),
                "successful_latency_low_ms": (
                    float(low_row["latency_ms"])
                    if low_row["success"] and pd.notna(low_row["latency_ms"])
                    else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def cluster_interval(
    frame: pd.DataFrame,
    column: str,
    *,
    seed: int = RANDOM_SEED,
    draws: int = BOOTSTRAP_DRAWS,
) -> dict[str, Any]:
    valid = frame.dropna(subset=[column, "cluster"])
    if valid.empty:
        return {"n": 0, "n_clusters": 0, "mean": None, "ci95": [None, None]}
    grouped = {key: values[column].to_numpy(float) for key, values in valid.groupby("cluster")}
    keys = list(grouped)
    rng = np.random.default_rng(seed)
    estimates = np.empty(draws, dtype=float)
    for draw in range(draws):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        estimates[draw] = np.concatenate([grouped[key] for key in sampled]).mean()
    return {
        "n": int(len(valid)),
        "n_clusters": int(len(keys)),
        "mean": float(valid[column].mean()),
        "ci95": [float(np.quantile(estimates, 0.025)), float(np.quantile(estimates, 0.975))],
    }


def paired_sign_test(pairs: pd.DataFrame, column: str) -> dict[str, Any]:
    values = pd.to_numeric(pairs.get(column), errors="coerce").dropna()
    discordant = values[~np.isclose(values, 0)]
    positives = int(discordant.gt(0).sum())
    return {
        "discordant_pairs": int(len(discordant)),
        "positive_pairs": positives,
        "one_sided_p": (
            float(binomtest(positives, len(discordant), 0.5, alternative="greater").pvalue)
            if len(discordant)
            else None
        ),
    }


def permutation_reference(
    joined: pd.DataFrame,
    *,
    seed: int = RANDOM_SEED + 1,
    draws: int = PERMUTATION_DRAWS,
) -> dict[str, Any]:
    eligible = []
    matched = joined[
        joined["public_join_status"].eq("matched_exact_backward")
        & joined["public_capacity_risk"].notna()
    ]
    for _block_id, block in matched.groupby("block_id", sort=False):
        if len(block) < 2 or block["public_capacity_risk"].nunique() < 2:
            continue
        eligible.append(
            (
                block["public_capacity_risk"].to_numpy(float),
                block["failure"].to_numpy(float),
            )
        )
    if not eligible:
        return {"draws": draws, "blocks": 0, "observed": None, "null_mean": None, "p": None}
    observed = np.mean(
        [outcome[np.argmax(risk)] - outcome[np.argmin(risk)] for risk, outcome in eligible]
    )
    rng = np.random.default_rng(seed)
    simulated = np.empty(draws)
    for draw in range(draws):
        values = []
        for risk, outcome in eligible:
            permuted = rng.permutation(risk)
            values.append(outcome[np.argmax(permuted)] - outcome[np.argmin(permuted)])
        simulated[draw] = np.mean(values)
    return {
        "draws": draws,
        "blocks": len(eligible),
        "observed": float(observed),
        "null_mean": float(simulated.mean()),
        "one_sided_p": float((1 + np.sum(simulated >= observed - 1e-15)) / (draws + 1)),
    }


def _prediction_fit(frame: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    complete = frame.dropna(subset=[*features, "failure", "block_id", "observed_ts"]).copy()
    block_times = (
        complete.groupby("block_id")["observed_ts"].min().sort_values().reset_index()
    )
    if len(block_times) < 4:
        return {"features": features, "status": "insufficient_blocks"}
    cut = max(1, min(len(block_times) - 1, int(math.floor(0.7 * len(block_times)))))
    train_ids = set(block_times.iloc[:cut]["block_id"])
    test_ids = set(block_times.iloc[cut:]["block_id"])
    train = complete[complete["block_id"].isin(train_ids)]
    test = complete[complete["block_id"].isin(test_ids)]
    y_train = train["failure"].astype(int).to_numpy()
    y_test = test["failure"].astype(int).to_numpy()
    if len(np.unique(y_train)) < 2 or test.empty:
        return {
            "features": features,
            "status": "single_class_or_empty_split",
            "n_train": int(len(train)),
            "n_test": int(len(test)),
        }
    scaler = StandardScaler().fit(train[features])
    x_train = scaler.transform(train[features])
    x_test = scaler.transform(test[features])
    model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=10_000)
    model.fit(x_train, y_train)
    probability = model.predict_proba(x_test)[:, 1]
    return {
        "features": features,
        "status": "fit",
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "train_blocks": int(len(train_ids)),
        "test_blocks": int(len(test_ids)),
        "temporal_split_ts": str(block_times.iloc[cut]["observed_ts"]),
        "coefficients_standardized": {
            feature: float(value)
            for feature, value in zip(features, model.coef_[0], strict=True)
        },
        "heldout_log_loss": float(log_loss(y_test, probability, labels=[0, 1])),
        "heldout_brier_score": float(brier_score_loss(y_test, probability)),
        "heldout_auc": (
            float(roc_auc_score(y_test, probability)) if len(np.unique(y_test)) == 2 else None
        ),
        "heldout_failure_rate": float(y_test.mean()),
    }


def prediction_comparison(joined: pd.DataFrame) -> dict[str, Any]:
    sample = joined[
        joined["public_join_status"].eq("matched_exact_backward")
        & joined["public_capacity_risk"].notna()
    ].copy()
    features_baseline = ["relative_log_public_price", "quoted_rank"]
    features_capacity = [*features_baseline, "public_capacity_risk"]
    # Use one common complete-case sample so a score difference cannot be
    # produced by changing rows between specifications.
    sample = sample.dropna(subset=features_capacity)
    baseline = _prediction_fit(sample, features_baseline)
    capacity = _prediction_fit(sample, features_capacity)
    improvement = None
    if baseline.get("status") == "fit" and capacity.get("status") == "fit":
        improvement = float(baseline["heldout_log_loss"] - capacity["heldout_log_loss"])
    return {
        "baseline": baseline,
        "capacity_risk": capacity,
        "capacity_log_loss_improvement": improvement,
    }


def _leave_one_out(pairs: pd.DataFrame, key: str) -> dict[str, Any]:
    values = []
    identities: set[str] = set()
    if key == "provider":
        identities.update(pairs.get("high_provider", pd.Series(dtype=str)).dropna().astype(str))
        identities.update(pairs.get("low_provider", pd.Series(dtype=str)).dropna().astype(str))
        for identity in sorted(identities):
            kept = pairs[
                pairs["high_provider"].astype(str).ne(identity)
                & pairs["low_provider"].astype(str).ne(identity)
            ]
            if len(kept):
                values.append(float(kept["failure_difference"].mean()))
    else:
        identities.update(pairs.get("model_id", pd.Series(dtype=str)).dropna().astype(str))
        for identity in sorted(identities):
            kept = pairs[pairs["model_id"].astype(str).ne(identity)]
            if len(kept):
                values.append(float(kept["failure_difference"].mean()))
    return {
        "n_omissions": len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def summarize(joined: pd.DataFrame, pairs: pd.DataFrame) -> dict[str, Any]:
    match = joined["public_join_status"].eq("matched_exact_backward")
    risk_complete = match & joined["public_capacity_risk"].notna()
    status_counts = joined["public_join_status"].value_counts(dropna=False).to_dict()
    outcome_coverage = (
        joined.assign(state_matched=risk_complete)
        .groupby("failure", dropna=False)["state_matched"]
        .agg(["count", "sum", "mean"])
        .reset_index()
        .to_dict(orient="records")
    )
    primary = cluster_interval(pairs, "failure_difference")
    rate_429 = cluster_interval(pairs, "rate_429_difference", seed=RANDOM_SEED + 1)
    price_caliper = pairs[pairs["within_price_caliper"].astype(bool)] if len(pairs) else pairs
    latency_high = pd.to_numeric(pairs.get("successful_latency_high_ms"), errors="coerce")
    latency_low = pd.to_numeric(pairs.get("successful_latency_low_ms"), errors="coerce")
    return {
        "evidence_status": "retrospective_capacity_execution_bridge",
        "preregistration": "docs/h86-h87-capacity-state-execution-preregistration.md",
        "support": {
            "legacy_pinned_attempts": int(len(joined)),
            "legacy_blocks": int(joined["block_id"].nunique()) if len(joined) else 0,
            "exact_backward_matches": int(match.sum()),
            "capacity_risk_complete_attempts": int(risk_complete.sum()),
            "risk_pairs": int(len(pairs)),
            "models": int(pairs["model_id"].nunique()) if len(pairs) else 0,
            "high_or_low_providers": int(
                len(set(pairs.get("high_provider", [])).union(set(pairs.get("low_provider", []))))
            )
            if len(pairs)
            else 0,
            "join_status_counts": {str(key): int(value) for key, value in status_counts.items()},
            "outcome_join_coverage": outcome_coverage,
        },
        "primary_failure_contrast": primary,
        "paired_sign_test": paired_sign_test(pairs, "failure_difference"),
        "http_429_contrast": rate_429,
        "within_25pct_price_caliper": cluster_interval(
            price_caliper, "failure_difference", seed=RANDOM_SEED + 2
        ),
        "pre_outcome_pair_diagnostics": {
            column: cluster_interval(pairs, column, seed=RANDOM_SEED + 10 + offset)
            for offset, column in enumerate(
                [
                    "risk_difference",
                    "capacity_load_difference",
                    "log_capacity_ceiling_difference",
                    "relative_log_price_difference",
                    "quoted_rank_difference",
                    "policy_order_difference",
                ]
            )
        },
        "permutation_reference": permutation_reference(joined),
        "prediction": prediction_comparison(joined),
        "leave_one_provider_out": _leave_one_out(pairs, "provider"),
        "leave_one_model_out": _leave_one_out(pairs, "model"),
        "successful_latency_selected": {
            "high_risk_n": int(latency_high.notna().sum()),
            "low_risk_n": int(latency_low.notna().sum()),
            "high_risk_mean_ms": float(latency_high.mean()) if latency_high.notna().any() else None,
            "low_risk_mean_ms": float(latency_low.mean()) if latency_low.notna().any() else None,
        },
        "claim_boundary": (
            "H86 is a retrospective predictive bridge for fixed-order legacy pinned probes. "
            "It does not identify the causal effect of capacity, provider intent, other-user "
            "routing, front-running, or welfare."
        ),
    }


def plot_results(pairs: pd.DataFrame, summary: dict[str, Any], out_dir: Path) -> None:
    if pairs.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    ax = axes[0, 0]
    rates = [pairs["low_failure"].mean(), pairs["high_failure"].mean()]
    ax.bar([0, 1], rates, color=["#4c956c", "#c14953"])
    ax.set_xticks([0, 1], ["lower public risk", "higher public risk"])
    ax.set_ylabel("Pinned request failure rate")
    ax.set_ylim(0, max(0.05, min(1.0, max(rates) * 1.35)))
    ax.set_title("Matched legacy probe outcomes")

    ax = axes[0, 1]
    labels = ["failure", "HTTP 429"]
    metrics = [summary["primary_failure_contrast"], summary["http_429_contrast"]]
    means = [metric["mean"] or 0.0 for metric in metrics]
    lower = [
        mean - (metric["ci95"][0] if metric["ci95"][0] is not None else mean)
        for mean, metric in zip(means, metrics, strict=True)
    ]
    upper = [
        (metric["ci95"][1] if metric["ci95"][1] is not None else mean) - mean
        for mean, metric in zip(means, metrics, strict=True)
    ]
    ax.errorbar(range(2), means, yerr=[lower, upper], fmt="o", color="#333333", capsize=5)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(range(2), labels)
    ax.set_ylabel("Higher-risk minus lower-risk")
    ax.set_title("Paired contrasts (95% cluster CI)")

    ax = axes[1, 0]
    ax.scatter(
        pairs["risk_difference"],
        pairs["failure_difference"],
        alpha=0.45,
        color="#33658a",
    )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Public capacity-risk gap")
    ax.set_ylabel("Failure difference")
    ax.set_title("Block-level risk and execution")

    ax = axes[1, 1]
    prediction = summary["prediction"]
    names, losses = [], []
    for name, key in [("price/rank", "baseline"), ("+ capacity risk", "capacity_risk")]:
        result = prediction[key]
        if result.get("heldout_log_loss") is not None:
            names.append(name)
            losses.append(result["heldout_log_loss"])
    if losses:
        ax.bar(range(len(losses)), losses, color=["#9a9a9a", "#33658a"][: len(losses)])
        ax.set_xticks(range(len(losses)), names)
        ax.set_ylabel("Held-out failure log loss")
        ax.set_title("Temporal prediction (lower is better)")
    else:
        ax.text(0.5, 0.5, "Prediction sample insufficient", ha="center", va="center")
        ax.set_axis_off()

    fig.suptitle("H86 public capacity state and realized pinned execution")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "h86_capacity_execution_bridge.png", dpi=180)
    fig.savefig(out_dir / "h86_capacity_execution_bridge.pdf")
    plt.close(fig)


def analyze(
    attempts: pd.DataFrame,
    public_rows: pd.DataFrame,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    pinned = legacy_pinned_attempts(attempts)
    states = public_provider_states(public_rows)
    joined = attach_public_state(pinned, states)
    pairs = risk_pairs(joined)
    summary = summarize(joined, pairs)
    if out_dir is not None:
        save(states, out_dir, "h86_public_provider_states")
        save(joined, out_dir, "h86_legacy_probe_state_join")
        save(pairs, out_dir, "h86_capacity_risk_pairs")
        save_json(summary, out_dir, "h86_summary")
        plot_results(pairs, summary, out_dir)
    return summary


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    attempts = data.q(
        f"""
        select *
        from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
        """
    ).df()
    return analyze(attempts, load_rows(), out_dir)
