"""WF-17: category-conditioned screens for collusive-looking behavior.

Provider-model regimes are frozen by WF-16 on its training panel. This module
uses only the later WF-16 holdout. It measures several implications that can be
consistent with coordination, then applies competitive/common-anchor nulls.
None of the screens identifies communication, agreement, profits, or intent.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from statsmodels.stats.multitest import multipletests

from . import data
from .common import DEFAULT_OUT, save, save_json
from .wf16_provider_type_validation import (
    TYPE_ORDER,
    add_author_anchor,
    load_daily_quotes,
    load_price_changes,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "within_type_collusion_v1.toml"


def load_protocol(path: Path = DEFAULT_CONFIG) -> tuple[dict, str]:
    payload = path.read_bytes()
    return tomllib.loads(payload.decode("utf-8")), hashlib.sha256(payload).hexdigest()


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    rate = successes / total
    denominator = 1 + z**2 / total
    center = (rate + z**2 / (2 * total)) / denominator
    half = z * np.sqrt(rate * (1 - rate) / total + z**2 / (4 * total**2)) / denominator
    return [round(float(max(0, center - half)), 4), round(float(min(1, center + half)), 4)]


def build_within_type_response_panel(
    changes: pd.DataFrame,
    labels: pd.DataFrame,
    author_prices: pd.DataFrame,
    holdout_start: pd.Timestamp,
    *,
    response_hours: float,
    placebo_shift_hours: float,
    anchor_rtol: float,
) -> pd.DataFrame:
    columns = [
        "arm",
        "rival_event_id",
        "event_ts",
        "model_id",
        "provider_type",
        "target_provider",
        "rival_provider",
        "rival_sign",
        "rival_new_at_author_anchor",
        "responded",
        "same_direction",
        "response_lag_hours",
    ]
    ch = changes[changes["ts"] >= holdout_start].copy()
    if ch.empty or labels.empty:
        return pd.DataFrame(columns=columns)
    label_map = labels.set_index(["model_id", "provider_name"])["provider_type"]
    ch["provider_type"] = [
        label_map.get((model, provider))
        for model, provider in zip(ch["model_id"], ch["provider_name"], strict=True)
    ]
    ch = ch.dropna(subset=["provider_type"])
    if ch.empty:
        return pd.DataFrame(columns=columns)
    anchor_map = author_prices.set_index(["model_id", "dt"])["author_price"].to_dict()
    panel_end = ch["ts"].max()
    rows: list[dict] = []
    for _, target in labels.iterrows():
        own = ch[
            (ch["model_id"] == target["model_id"])
            & (ch["provider_name"] == target["provider_name"])
        ]
        rivals = ch[
            (ch["model_id"] == target["model_id"])
            & (ch["provider_name"] != target["provider_name"])
            & (ch["provider_type"] == target["provider_type"])
        ]
        for rival_id, event in rivals.iterrows():
            placebo_ts = event["ts"] + pd.Timedelta(placebo_shift_hours, unit="h")
            if placebo_ts + pd.Timedelta(response_hours, unit="h") > panel_end:
                continue
            event_day = event["ts"].normalize()
            author_price = anchor_map.get((event["model_id"], event_day), np.nan)
            at_anchor = bool(
                np.isfinite(author_price)
                and np.isclose(event["new_price"], author_price, rtol=anchor_rtol, atol=0)
            )
            for arm, event_ts in (("observed", event["ts"]), ("shifted_placebo", placebo_ts)):
                end = event_ts + pd.Timedelta(response_hours, unit="h")
                response = own[(own["ts"] > event_ts) & (own["ts"] <= end)].head(1)
                responded = not response.empty
                response_sign = (
                    float(np.sign(response.iloc[0]["new_price"] - response.iloc[0]["old_price"]))
                    if responded
                    else np.nan
                )
                rival_sign = float(np.sign(event["new_price"] - event["old_price"]))
                rows.append(
                    {
                        "arm": arm,
                        "rival_event_id": str(rival_id),
                        "event_ts": event_ts,
                        "model_id": target["model_id"],
                        "provider_type": target["provider_type"],
                        "target_provider": target["provider_name"],
                        "rival_provider": event["provider_name"],
                        "rival_sign": rival_sign,
                        "rival_new_at_author_anchor": at_anchor,
                        "responded": responded,
                        "same_direction": bool(responded and response_sign == rival_sign),
                        "response_lag_hours": (
                            (response.iloc[0]["ts"] - event_ts).total_seconds() / 3600
                            if responded
                            else np.nan
                        ),
                    }
                )
    return pd.DataFrame(rows, columns=columns)


def paired_response_inference(
    frame: pd.DataFrame, *, bootstrap_draws: int, seed: int
) -> dict:
    if frame.empty:
        return {"status": "power_gated", "gate": "no paired within-type events"}
    index = ["model_id", "target_provider", "rival_event_id"]
    paired = frame.pivot_table(index=index, columns="arm", values="responded", aggfunc="max")
    paired = paired.dropna(subset=["observed", "shifted_placebo"]).astype(float).reset_index()
    if paired.empty:
        return {"status": "power_gated", "gate": "no complete within-type event pairs"}
    paired["difference"] = paired["observed"] - paired["shifted_placebo"]
    observed_only = int(
        ((paired["observed"] == 1) & (paired["shifted_placebo"] == 0)).sum()
    )
    placebo_only = int(
        ((paired["observed"] == 0) & (paired["shifted_placebo"] == 1)).sum()
    )
    discordant = observed_only + placebo_only
    exact_p = (
        float(binomtest(observed_only, discordant, 0.5, alternative="greater").pvalue)
        if discordant
        else 1.0
    )
    clusters = paired.groupby(["model_id", "target_provider"])["difference"].mean().to_numpy()
    interval = None
    if len(clusters) >= 2:
        rng = np.random.default_rng(seed)
        boot = rng.choice(clusters, (bootstrap_draws, len(clusters)), replace=True).mean(axis=1)
        interval = [round(float(x), 4) for x in np.quantile(boot, [0.025, 0.975])]
    observed_successes = int(paired["observed"].sum())
    placebo_successes = int(paired["shifted_placebo"].sum())
    return {
        "status": "paired_timing_placebo",
        "paired_events": int(len(paired)),
        "clusters": int(len(clusters)),
        "observed_rate": round(observed_successes / len(paired), 4),
        "observed_rate_95ci": _wilson(observed_successes, len(paired)),
        "placebo_rate": round(placebo_successes / len(paired), 4),
        "placebo_rate_95ci": _wilson(placebo_successes, len(paired)),
        "observed_minus_placebo": round(float(paired["difference"].mean()), 4),
        "cluster_bootstrap_95ci": interval,
        "discordant_observed_only": observed_only,
        "discordant_placebo_only": placebo_only,
        "one_sided_exact_p_observed_greater": round(exact_p, 6),
    }


def _mean_pair_distance(values: np.ndarray) -> float:
    if len(values) < 2:
        return np.nan
    differences = np.abs(values[:, None] - values[None, :])
    return float(differences[np.triu_indices(len(values), k=1)].mean())


def price_clustering_test(
    holdout_quotes: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    permutations: int,
    seed: int,
) -> tuple[pd.DataFrame, dict]:
    panel = holdout_quotes.merge(
        labels[["model_id", "provider_name", "provider_type"]],
        on=["model_id", "provider_name"],
        how="inner",
    )
    cells: list[dict] = []
    grouped: list[tuple[np.ndarray, np.ndarray]] = []
    for (model, day), group in panel.groupby(["model_id", "dt"], sort=True):
        group = group.sort_values("provider_name", kind="mergesort")
        types = group["provider_type"].to_numpy(str)
        wedges = group["log_wedge"].to_numpy(float)
        grouped.append((types, wedges))
        for kind in TYPE_ORDER:
            values = wedges[types == kind]
            if len(values) >= 2:
                cells.append(
                    {
                        "model_id": model,
                        "dt": day,
                        "provider_type": kind,
                        "providers": int(len(values)),
                        "mean_pair_log_wedge_distance": _mean_pair_distance(values),
                    }
                )
    cell_frame = pd.DataFrame(cells)
    if cell_frame.empty:
        return cell_frame, {kind: {"status": "power_gated"} for kind in TYPE_ORDER}
    observed = cell_frame.groupby("provider_type")["mean_pair_log_wedge_distance"].mean()
    null = {kind: [] for kind in TYPE_ORDER}
    rng = np.random.default_rng(seed)
    for _ in range(permutations):
        draw_values = {kind: [] for kind in TYPE_ORDER}
        for types, wedges in grouped:
            shuffled = rng.permutation(types)
            for kind in TYPE_ORDER:
                values = wedges[shuffled == kind]
                if len(values) >= 2:
                    draw_values[kind].append(_mean_pair_distance(values))
        for kind in TYPE_ORDER:
            if draw_values[kind]:
                null[kind].append(float(np.mean(draw_values[kind])))
    results = {}
    for kind in TYPE_ORDER:
        draws = np.asarray(null[kind], dtype=float)
        if kind not in observed or not len(draws):
            results[kind] = {"status": "power_gated"}
            continue
        value = float(observed[kind])
        pvalue = float((1 + np.sum(draws <= value)) / (len(draws) + 1))
        results[kind] = {
            "status": "label_permutation_screen",
            "cells": int((cell_frame["provider_type"] == kind).sum()),
            "observed_mean_pair_distance": round(value, 6),
            "permuted_median": round(float(np.median(draws)), 6),
            "permuted_95_interval": [
                round(float(x), 6) for x in np.quantile(draws, [0.025, 0.975])
            ],
            "one_sided_p_more_clustered": round(pvalue, 6),
        }
    return cell_frame, results


def build_punishment_panel(
    changes: pd.DataFrame,
    labels: pd.DataFrame,
    holdout_start: pd.Timestamp,
    *,
    response_hours: float,
    revert_hours: float,
    episode_gap_hours: float,
    reversion_fraction: float,
) -> pd.DataFrame:
    columns = [
        "event_id",
        "event_ts",
        "model_id",
        "provider_name",
        "provider_type",
        "same_type_rivals",
        "followers",
        "follower_providers",
        "first_reverting_peer",
        "first_peer_raise_ts",
        "classification",
    ]
    ch = changes[changes["ts"] >= holdout_start].copy()
    label_map = labels.set_index(["model_id", "provider_name"])["provider_type"]
    ch["provider_type"] = [
        label_map.get((model, provider))
        for model, provider in zip(ch["model_id"], ch["provider_name"], strict=True)
    ]
    ch = ch.dropna(subset=["provider_type"])
    panel_end = ch["ts"].max() if not ch.empty else holdout_start
    rows = []
    cuts = ch[ch["new_price"] < ch["old_price"]].sort_values(
        ["ts", "model_id", "provider_name"], kind="mergesort"
    )
    last_episode: dict[tuple[str, str], pd.Timestamp] = {}
    for event_id, event in cuts.iterrows():
        episode_key = (str(event["model_id"]), str(event["provider_name"]))
        previous_episode = last_episode.get(episode_key)
        if previous_episode is not None and (
            event["ts"] - previous_episode
        ) < pd.Timedelta(episode_gap_hours, unit="h"):
            continue
        last_episode[episode_key] = event["ts"]
        response_end = event["ts"] + pd.Timedelta(response_hours, unit="h")
        revert_end = event["ts"] + pd.Timedelta(revert_hours, unit="h")
        if revert_end > panel_end:
            continue
        rivals = ch[
            (ch["model_id"] == event["model_id"])
            & (ch["provider_name"] != event["provider_name"])
            & (ch["provider_type"] == event["provider_type"])
        ]
        rival_names = int(rivals["provider_name"].nunique())
        followers = rivals[
            (rivals["ts"] > event["ts"])
            & (rivals["ts"] <= response_end)
            & (rivals["new_price"] < rivals["old_price"])
        ]
        first_peer_raise = pd.NaT
        if followers.empty:
            classification = "no_same_type_response"
            first_peer_raise_provider = None
        else:
            first_peer_raise_provider = None
            for follower in followers.itertuples(index=False):
                raises = rivals[
                    (rivals["provider_name"] == follower.provider_name)
                    & (rivals["ts"] > follower.ts)
                    & (rivals["ts"] <= revert_end)
                    & (rivals["new_price"] > rivals["old_price"])
                    & (rivals["new_price"] >= follower.old_price * reversion_fraction)
                ]
                if not raises.empty:
                    candidate = raises["ts"].min()
                    if pd.isna(first_peer_raise) or candidate < first_peer_raise:
                        first_peer_raise = candidate
                        first_peer_raise_provider = follower.provider_name
            if pd.isna(first_peer_raise):
                classification = "competitive_following"
            else:
                initiator_raise = ch[
                    (ch["model_id"] == event["model_id"])
                    & (ch["provider_name"] == event["provider_name"])
                    & (ch["ts"] > event["ts"])
                    & (ch["ts"] <= first_peer_raise)
                    & (ch["new_price"] >= event["old_price"] * reversion_fraction)
                ]
                classification = (
                    "cut_withdrawn"
                    if not initiator_raise.empty
                    else "punish_and_revert_candidate"
                )
        rows.append(
            {
                "event_id": str(event_id),
                "event_ts": event["ts"],
                "model_id": event["model_id"],
                "provider_name": event["provider_name"],
                "provider_type": event["provider_type"],
                "same_type_rivals": rival_names,
                "followers": int(followers["provider_name"].nunique()),
                "follower_providers": ", ".join(sorted(followers["provider_name"].unique())),
                "first_reverting_peer": first_peer_raise_provider,
                "first_peer_raise_ts": first_peer_raise,
                "classification": classification,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def leadership_panel(response: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    observed = response[response["arm"] == "observed"]
    if observed.empty:
        return pd.DataFrame(), {kind: {"status": "power_gated"} for kind in TYPE_ORDER}
    panel = observed.groupby(
        ["provider_type", "rival_provider"], as_index=False
    ).agg(
        response_opportunities=("rival_event_id", "size"),
        follower_responses=("responded", "sum"),
        same_direction_responses=("same_direction", "sum"),
    )
    panel["response_rate"] = panel["follower_responses"] / panel[
        "response_opportunities"
    ].clip(lower=1)
    summary = {}
    for kind, group in panel.groupby("provider_type"):
        responses = group["follower_responses"].to_numpy(float)
        total = float(responses.sum())
        shares = responses / total if total else np.zeros(len(responses))
        top = group.sort_values(
            ["follower_responses", "rival_provider"],
            ascending=[False, True],
            kind="mergesort",
        ).iloc[0]
        summary[str(kind)] = {
            "leaders": int(len(group)),
            "follower_responses": int(total),
            "leader_hhi": round(float(np.square(shares).sum()), 4) if total else None,
            "top_leader": str(top["rival_provider"]),
            "top_leader_response_share": round(float(top["follower_responses"] / total), 4)
            if total
            else None,
        }
    return panel, summary


def build_memory_panel(
    holdout_quotes: pd.DataFrame,
    holdout_changes: pd.DataFrame,
    labels: pd.DataFrame,
) -> pd.DataFrame:
    panel = holdout_quotes.merge(
        labels[["model_id", "provider_name", "provider_type"]],
        on=["model_id", "provider_name"],
        how="inner",
    )
    event_counts = holdout_changes.groupby(["dt", "model_id", "provider_name"]).size()
    panel["event"] = [
        int(event_counts.get((day, model, provider), 0) > 0)
        for day, model, provider in zip(
            panel["dt"], panel["model_id"], panel["provider_name"], strict=True
        )
    ]
    group_keys = ["dt", "model_id", "provider_type"]
    panel["same_type_events"] = panel.groupby(group_keys)["event"].transform("sum")
    panel["same_type_count"] = panel.groupby(group_keys)["event"].transform("size")
    panel["same_type_rival_rate"] = (
        (panel["same_type_events"] - panel["event"])
        / (panel["same_type_count"] - 1).replace(0, np.nan)
    ).fillna(0)
    model_keys = ["dt", "model_id"]
    panel["all_events"] = panel.groupby(model_keys)["event"].transform("sum")
    panel["all_count"] = panel.groupby(model_keys)["event"].transform("size")
    other_events = panel["all_events"] - panel["same_type_events"]
    other_count = panel["all_count"] - panel["same_type_count"]
    panel["other_type_rival_rate"] = (other_events / other_count.replace(0, np.nan)).fillna(0)
    panel["all_rival_rate"] = (
        (panel["all_events"] - panel["event"])
        / (panel["all_count"] - 1).replace(0, np.nan)
    ).fillna(0)
    panel["abs_log_wedge"] = panel["log_wedge"].abs()
    panel = panel.sort_values(["model_id", "provider_name", "dt"])
    pair = panel.groupby(["model_id", "provider_name"], sort=False)
    for column in (
        "event",
        "abs_log_wedge",
        "same_type_rival_rate",
        "other_type_rival_rate",
        "all_rival_rate",
    ):
        panel[f"lag_{column}"] = pair[column].shift(1)
    return panel.dropna(subset=["lag_event", "lag_abs_log_wedge"])


def memory_predictive_tests(
    panel: pd.DataFrame,
    *,
    bootstrap_draws: int,
    seed: int,
    minimum_train_events: int,
    minimum_test_events: int,
) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if panel.empty:
        return {kind: {"status": "power_gated"} for kind in TYPE_ORDER}
    dates = sorted(panel["dt"].unique())
    cutoff = dates[max(1, len(dates) // 2)] if len(dates) >= 2 else dates[0]
    base_columns = ["lag_event", "lag_abs_log_wedge", "lag_all_rival_rate"]
    typed_columns = [
        "lag_event",
        "lag_abs_log_wedge",
        "lag_same_type_rival_rate",
        "lag_other_type_rival_rate",
    ]
    output = {}
    for kind in TYPE_ORDER:
        group = panel[panel["provider_type"] == kind].copy()
        train = group[group["dt"] < cutoff]
        test = group[group["dt"] >= cutoff]
        if (
            len(train) < 50
            or len(test) < 20
            or train["event"].nunique() < 2
            or test["event"].nunique() < 2
            or int(train["event"].sum()) < minimum_train_events
            or int(test["event"].sum()) < minimum_test_events
        ):
            output[kind] = {
                "status": "power_gated",
                "n_train": int(len(train)),
                "n_test": int(len(test)),
                "events_train": int(train["event"].sum()),
                "events_test": int(test["event"].sum()),
            }
            continue
        base = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
        typed = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000))
        base.fit(train[base_columns], train["event"])
        typed.fit(train[typed_columns], train["event"])
        y = test["event"].to_numpy(int)
        base_probability = base.predict_proba(test[base_columns])[:, 1]
        typed_probability = typed.predict_proba(test[typed_columns])[:, 1]
        base_loss = -(y * np.log(base_probability) + (1 - y) * np.log(1 - base_probability))
        typed_loss = -(y * np.log(typed_probability) + (1 - y) * np.log(1 - typed_probability))
        gain = base_loss - typed_loss
        clusters = [
            gain[test["model_id"].to_numpy() == model]
            for model in sorted(test["model_id"].unique())
        ]
        clusters = [values for values in clusters if len(values)]
        interval = None
        if len(clusters) >= 2:
            rng = np.random.default_rng(seed)
            boot = []
            for _ in range(bootstrap_draws):
                chosen = rng.integers(0, len(clusters), size=len(clusters))
                boot.append(float(np.concatenate([clusters[index] for index in chosen]).mean()))
            interval = [round(float(x), 6) for x in np.quantile(boot, [0.025, 0.975])]
        output[kind] = {
            "status": "temporal_holdout_predictive_screen",
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "events_test": int(y.sum()),
            "model_clusters": int(len(clusters)),
            "base_log_loss": round(float(log_loss(y, base_probability)), 6),
            "typed_memory_log_loss": round(float(log_loss(y, typed_probability)), 6),
            "log_loss_improvement": round(float(gain.mean()), 6),
            "model_cluster_bootstrap_95ci": interval,
        }
    return output


def _holm_adjust(response: dict, clustering: dict) -> dict:
    entries = []
    for kind in TYPE_ORDER:
        response_p = response.get(kind, {}).get("one_sided_exact_p_observed_greater")
        cluster_p = clustering.get(kind, {}).get("one_sided_p_more_clustered")
        if response_p is not None:
            entries.append((kind, "response", float(response_p)))
        if cluster_p is not None:
            entries.append((kind, "clustering", float(cluster_p)))
    if not entries:
        return {}
    adjusted = multipletests([entry[2] for entry in entries], method="holm")[1]
    return {
        f"{kind}:{test}": {
            "raw_p": raw,
            "holm_p": round(float(corrected), 6),
        }
        for (kind, test, raw), corrected in zip(entries, adjusted, strict=True)
    }


def collusion_scorecard(
    response: dict,
    clustering: dict,
    memory: dict,
    punishment: pd.DataFrame,
    adjusted_pvalues: dict,
) -> dict:
    scorecard = {}
    for kind in TYPE_ORDER:
        response_ci = response.get(kind, {}).get("cluster_bootstrap_95ci")
        memory_ci = memory.get(kind, {}).get("model_cluster_bootstrap_95ci")
        response_p = adjusted_pvalues.get(f"{kind}:response", {}).get("holm_p", 1.0)
        cluster_p = adjusted_pvalues.get(f"{kind}:clustering", {}).get("holm_p", 1.0)
        response_leg = bool(response_ci and response_ci[0] > 0 and response_p <= 0.05)
        # The common public author price makes anchor clustering mechanical.
        clustering_leg = bool(kind != "anchor_adopter" and cluster_p <= 0.05)
        memory_leg = bool(memory_ci and memory_ci[0] > 0)
        punish_count = int(
            (
                (punishment["provider_type"] == kind)
                & (punishment["classification"] == "punish_and_revert_candidate")
            ).sum()
        ) if not punishment.empty else 0
        legs = int(response_leg) + int(clustering_leg) + int(memory_leg)
        dynamic_leg = response_leg or memory_leg
        status = (
            "multi_proxy_candidate_not_identified"
            if legs >= 2 and dynamic_leg
            else "single_proxy_only"
            if legs == 1
            else "no_positive_screen"
        )
        scorecard[kind] = {
            "excess_response_leg": response_leg,
            "excess_clustering_leg": clustering_leg,
            "typed_memory_predictive_leg": memory_leg,
            "punish_and_revert_candidates": punish_count,
            "independent_positive_legs": legs,
            "dynamic_leg_required_for_multi_proxy": True,
            "status": status,
            "collusion_identified": False,
        }
    return scorecard


def _render(
    out_dir: Path,
    response_summary: dict,
    clustering_summary: dict,
    memory_summary: dict,
    punishment: pd.DataFrame,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    x = np.arange(len(TYPE_ORDER))
    labels = [kind.replace("_", "\n") for kind in TYPE_ORDER]

    observed = [response_summary.get(kind, {}).get("observed_rate", np.nan) for kind in TYPE_ORDER]
    placebo = [response_summary.get(kind, {}).get("placebo_rate", np.nan) for kind in TYPE_ORDER]
    axes[0, 0].bar(x - 0.18, observed, 0.36, label="Observed same-regime move", color="#D45087")
    axes[0, 0].bar(x + 0.18, placebo, 0.36, label="Shifted-time placebo", color="#9CA3AF")
    axes[0, 0].set_xticks(x, labels)
    axes[0, 0].set_ylabel("Repriced within window")
    axes[0, 0].set_title("A. Same-regime response timing")
    axes[0, 0].legend(frameon=False, fontsize=8, loc="upper left")
    finite_rates = [
        value for value in [*observed, *placebo] if np.isfinite(value)
    ]
    axes[0, 0].set_ylim(0, max(finite_rates + [0.05]) * 1.15)
    for index, kind in enumerate(TYPE_ORDER):
        count = response_summary.get(kind, {}).get("paired_events", 0)
        height = max(
            value
            for value in (observed[index], placebo[index], 0)
            if np.isfinite(value)
        )
        axes[0, 0].text(index, height + 0.015, f"N={count}", ha="center", fontsize=8)

    observed_distance = [
        clustering_summary.get(kind, {}).get("observed_mean_pair_distance", np.nan)
        for kind in TYPE_ORDER
    ]
    null_distance = [
        clustering_summary.get(kind, {}).get("permuted_median", np.nan)
        for kind in TYPE_ORDER
    ]
    axes[0, 1].bar(x - 0.18, observed_distance, 0.36, label="Observed", color="#2F4B7C")
    axes[0, 1].bar(x + 0.18, null_distance, 0.36, label="Permuted labels", color="#FFA600")
    axes[0, 1].set_xticks(x, labels)
    axes[0, 1].set_ylabel("Mean pairwise log-price distance")
    axes[0, 1].set_title("B. Holdout clustering (anchor is a mechanical benchmark)")
    axes[0, 1].legend(frameon=False, fontsize=8)

    gains = [
        memory_summary.get(kind, {}).get("log_loss_improvement", np.nan)
        for kind in TYPE_ORDER
    ]
    if np.isfinite(np.asarray(gains, dtype=float)).any():
        axes[1, 0].bar(labels, gains, color="#7A5195")
        axes[1, 0].axhline(0, color="black", linewidth=1)
    else:
        axes[1, 0].set_xticks(x, labels)
        axes[1, 0].set_ylim(-0.05, 0.05)
        axes[1, 0].text(
            0.5,
            0.5,
            "Power-gated: no regime has enough\nfit and test repricing events",
            ha="center",
            va="center",
            transform=axes[1, 0].transAxes,
            fontsize=11,
        )
    axes[1, 0].set_ylabel("Holdout log-loss improvement")
    axes[1, 0].set_title("C. Value of typed rival memory")

    classes = [
        "no_same_type_response",
        "competitive_following",
        "cut_withdrawn",
        "punish_and_revert_candidate",
    ]
    colors = ["#B8C0CC", "#4C78A8", "#F58518", "#E45756"]
    bottom = np.zeros(len(TYPE_ORDER))
    for event_class, color in zip(classes, colors, strict=True):
        values = []
        for kind in TYPE_ORDER:
            group = punishment[punishment["provider_type"] == kind]
            values.append(
                float((group["classification"] == event_class).mean())
                if len(group)
                else 0
            )
        axes[1, 1].bar(
            labels,
            values,
            bottom=bottom,
            label=event_class.replace("_", " "),
            color=color,
        )
        bottom += np.asarray(values)
    for index, kind in enumerate(TYPE_ORDER):
        count = int((punishment["provider_type"] == kind).sum())
        axes[1, 1].text(index, 1.01, f"N={count}", ha="center", fontsize=8)
    axes[1, 1].set_ylim(0, 1.12)
    axes[1, 1].set_ylabel("Share of evaluable cuts")
    axes[1, 1].set_title("D. Within-regime cut-response taxonomy")
    axes[1, 1].legend(
        frameon=False,
        fontsize=7,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=2,
    )

    fig.suptitle(
        "Within-regime collusion screens: multiple nulls, no intent inference",
        fontsize=15,
    )
    for extension in ("png", "pdf"):
        fig.savefig(out_dir / f"wf17_within_type_collusion.{extension}", dpi=200)
    plt.close(fig)


def run(out_dir: Path = DEFAULT_OUT, config_path: Path = DEFAULT_CONFIG) -> dict:
    protocol, protocol_sha = load_protocol(config_path)
    label_path = out_dir / "wf16_provider_type_labels.parquet"
    wf16_summary_path = out_dir / "wf16_summary.json"
    if not label_path.exists() or not wf16_summary_path.exists():
        raise RuntimeError("WF17 requires WF16 labels and summary from the same output directory")
    labels = pd.read_parquet(label_path)
    wf16_summary = json.loads(wf16_summary_path.read_text())
    holdout_start = pd.Timestamp(wf16_summary["holdout_start"], tz="UTC")
    with data.pinned_analysis_source() as source:
        quotes = load_daily_quotes()
        changes = load_price_changes()
    anchored = add_author_anchor(quotes, float(protocol["thresholds"]["anchor_match_rtol"]))
    holdout_quotes = anchored[anchored["dt"] >= holdout_start]
    holdout_changes = changes[changes["dt"] >= holdout_start]
    author_prices = holdout_quotes[["model_id", "dt", "author_price"]].drop_duplicates()

    response = build_within_type_response_panel(
        changes,
        labels,
        author_prices,
        holdout_start,
        response_hours=float(protocol["windows"]["response_hours"]),
        placebo_shift_hours=float(protocol["windows"]["placebo_shift_hours"]),
        anchor_rtol=float(protocol["thresholds"]["anchor_match_rtol"]),
    )
    response_summary = {}
    for kind in TYPE_ORDER:
        group = response[response["provider_type"] == kind]
        if kind == "anchor_adopter":
            raw_anchor = paired_response_inference(
                group,
                bootstrap_draws=int(protocol["inference"]["bootstrap_draws"]),
                seed=int(protocol["inference"]["seed"]),
            )
            group = group[~group["rival_new_at_author_anchor"]]
        response_summary[kind] = paired_response_inference(
            group,
            bootstrap_draws=int(protocol["inference"]["bootstrap_draws"]),
            seed=int(protocol["inference"]["seed"]),
        )
        response_summary[kind]["anchor_adjustment"] = (
            "events landing on the public author anchor excluded"
            if kind == "anchor_adopter"
            else "not applicable"
        )
        if kind == "anchor_adopter":
            response_summary[kind]["including_public_anchor_events_descriptive"] = raw_anchor
    clustering_cells, clustering_summary = price_clustering_test(
        holdout_quotes,
        labels,
        permutations=int(protocol["inference"]["label_permutations"]),
        seed=int(protocol["inference"]["seed"]),
    )
    punishment = build_punishment_panel(
        changes,
        labels,
        holdout_start,
        response_hours=float(protocol["windows"]["punishment_response_hours"]),
        revert_hours=float(protocol["windows"]["revert_hours"]),
        episode_gap_hours=float(protocol["windows"]["episode_gap_hours"]),
        reversion_fraction=float(protocol["windows"]["reversion_fraction"]),
    )
    leadership, leadership_summary = leadership_panel(response)
    memory_panel = build_memory_panel(holdout_quotes, holdout_changes, labels)
    memory_summary = memory_predictive_tests(
        memory_panel,
        bootstrap_draws=int(protocol["inference"]["bootstrap_draws"]),
        seed=int(protocol["inference"]["seed"]),
        minimum_train_events=int(protocol["inference"]["minimum_train_events"]),
        minimum_test_events=int(protocol["inference"]["minimum_test_events"]),
    )
    adjusted = _holm_adjust(response_summary, clustering_summary)
    scorecard = collusion_scorecard(
        response_summary, clustering_summary, memory_summary, punishment, adjusted
    )

    save(response, out_dir, "wf17_within_type_response")
    save(clustering_cells, out_dir, "wf17_price_clustering_cells")
    save(punishment, out_dir, "wf17_punishment_events")
    save(leadership, out_dir, "wf17_leadership")
    save(memory_panel, out_dir, "wf17_memory_panel")
    _render(out_dir, response_summary, clustering_summary, memory_summary, punishment)

    event_taxonomy = (
        punishment.groupby("provider_type")["classification"]
        .value_counts()
        .unstack(fill_value=0)
        .to_dict("index")
        if not punishment.empty
        else {}
    )
    summary = {
        "study_id": protocol["study"]["id"],
        "evidence_status": "multi_null_holdout_screen",
        "source": source,
        "wf16_source_revision": wf16_summary["source"]["revision"],
        "protocol_sha256": protocol_sha,
        "holdout_start": wf16_summary["holdout_start"],
        "response_by_type": response_summary,
        "price_clustering_by_type": clustering_summary,
        "typed_memory_predictive_value": memory_summary,
        "leadership_by_type": leadership_summary,
        "cut_response_taxonomy": event_taxonomy,
        "holm_adjusted_pvalues": adjusted,
        "collusion_scorecard": scorecard,
        "collusion_identified": False,
        "interpretation_rule": (
            "A category becomes a multi-proxy candidate only when at least two independent "
            "holdout legs survive their stated nulls and at least one is dynamic response or "
            "typed-memory evidence. Event taxonomies and leadership concentration remain "
            "descriptive and do not independently promote a category."
        ),
        "claim_boundary": (
            "These tests measure price clustering, typed-rival predictability, response timing, "
            "leadership concentration, and punishment/reversion patterns within frozen "
            "provider-model-period regimes. Common costs, public signals, common pricing "
            "software, capacity shocks, and asynchronous competitive adjustment remain "
            "structural twins. Anchor clustering is never scored because the author price is a "
            "public focal point. Communication, agreement, profits, and intent are unobserved."
        ),
    }
    save_json(summary, out_dir, "wf17_summary")
    return summary


if __name__ == "__main__":
    run()
