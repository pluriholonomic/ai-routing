"""WF-16: temporally validated provider pricing types and mechanism screens.

The training panel creates four observable provider-model labels.  Every
outcome is then evaluated on later dates.  The labels describe quote behavior;
they do not identify technology, costs, subsidies, coordination, or intent.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tomllib
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest, mannwhitneyu

from . import data
from .common import DEFAULT_OUT, save, save_json
from .market_scope import paid_model_sql
from .pm9_author_anchor import is_author_provider
from .wf13_provider_strata import tier_of, tiers
from .wf15_spread_explanations import CHINA, WEB3

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "provider_type_validation_v1.toml"
TYPE_ORDER = [
    "premium_differentiated",
    "anchor_adopter",
    "static_discounter",
    "active_undercutter",
]


def load_protocol(path: Path = DEFAULT_CONFIG) -> tuple[dict, str]:
    payload = path.read_bytes()
    return tomllib.loads(payload.decode("utf-8")), hashlib.sha256(payload).hexdigest()


def _ts(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce")


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    p = successes / total
    den = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / den
    half = z * np.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / den
    return [round(float(max(0, center - half)), 4), round(float(min(1, center + half)), 4)]


def load_daily_quotes() -> pd.DataFrame:
    frame = data.q(
        f"""
        select cast(dt as varchar) as dt, model_id, provider_name,
               median(try_cast(price_completion as double)) as price_completion
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        where try_cast(price_completion as double) > 0 and {paid_model_sql("model_id")}
        group by 1, 2, 3
        """
    ).df()
    frame["dt"] = pd.to_datetime(frame["dt"], utc=True, errors="coerce")
    return frame.dropna(subset=["dt", "price_completion"])


def load_price_changes() -> pd.DataFrame:
    frame = data.q(
        f"""
        select changed_at_run_ts, cast(dt as varchar) as dt, model_id, provider_name,
               try_cast(old_value as double) as old_price,
               try_cast(new_value as double) as new_price
        from read_parquet(
          '{data.table_glob("pricing_changes", layer="derived")}', union_by_name=true
        )
        where field = 'price_completion' and {paid_model_sql("model_id")}
          and try_cast(old_value as double) > 0 and try_cast(new_value as double) > 0
        """
    ).df()
    frame["ts"] = _ts(frame["changed_at_run_ts"])
    frame["dt"] = pd.to_datetime(frame["dt"], utc=True, errors="coerce")
    return frame.dropna(subset=["ts", "dt"]).sort_values("ts").reset_index(drop=True)


def load_slug_map() -> pd.DataFrame:
    return data.q(
        f"""
        select canonical_slug, min(id) as model_id
        from read_parquet('{data.table_glob("models_snapshots")}', union_by_name=true)
        where canonical_slug is not null and {paid_model_sql("id")}
        group by 1
        """
    ).df()


def load_congestion() -> pd.DataFrame:
    frame = data.q(
        f"""
        select run_ts, cast(dt as varchar) as dt, model_permaslug, provider_name,
          try_cast(price_completion as double) as price_completion,
          try_cast(p50_throughput as double) as throughput,
          try_cast(p50_latency_ms as double) as latency,
          try_cast(request_count_30m as double) as requests,
          try_cast(recent_peak_rpm as double) as peak_rpm,
          try_cast(capacity_ceiling_rpm as double) as capacity_rpm,
          try_cast(rate_limited_30m as double) as rate_limited,
          try_cast(derankable_error_30m as double) as derankable_errors,
          try_cast(is_deranked as boolean) as is_deranked
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        """
    ).df()
    frame["ts"] = _ts(frame["run_ts"])
    frame["dt"] = pd.to_datetime(frame["dt"], utc=True, errors="coerce")
    return frame.dropna(subset=["dt"])


def load_paid_attempts() -> pd.DataFrame:
    """Load only the price-response study, never blinded H81/H95 outcomes."""
    try:
        frame = data.q(
            f"""
            select event_id, observed_at, run_ts, study_id, model_id,
                   requested_provider, selected_provider, outcome,
                   try_cast(cost_usd as double) as cost_usd,
                   try_cast(latency_ms as double) as latency_ms
            from read_parquet(
              '{data.table_glob("router_route_attempts")}', union_by_name=true
            )
            where study_id like 'openrouter-price-response%'
               or study_id = 'openrouter-default-probes-v1'
            """
        ).df()
    except Exception as exc:  # optional owned-traffic layer
        data.reset_connection()
        log.warning("price-response attempts unavailable: %s", exc)
        return pd.DataFrame()
    if frame.empty:
        return frame
    observed = pd.to_datetime(frame["observed_at"], utc=True, errors="coerce")
    fallback = _ts(frame["run_ts"])
    frame["ts"] = observed.fillna(fallback)
    frame["dt"] = frame["ts"].dt.normalize()
    return frame.dropna(subset=["ts"])


def add_author_anchor(quotes: pd.DataFrame, rtol: float) -> pd.DataFrame:
    q = quotes.copy()
    q["is_author"] = [
        is_author_provider(model, provider)
        for model, provider in zip(q["model_id"], q["provider_name"], strict=True)
    ]
    anchor = (
        q[q["is_author"]]
        .groupby(["model_id", "dt"], as_index=False)["price_completion"]
        .min()
        .rename(columns={"price_completion": "author_price"})
    )
    joined = q[~q["is_author"]].merge(anchor, on=["model_id", "dt"], how="inner")
    joined["at_anchor"] = np.isclose(
        joined["price_completion"], joined["author_price"], rtol=rtol, atol=0
    )
    joined["log_wedge"] = np.log(joined["price_completion"] / joined["author_price"])
    return joined


def split_dates(quotes: pd.DataFrame, train_fraction: float) -> tuple[pd.Timestamp, list[str]]:
    dates = sorted(pd.Timestamp(x) for x in quotes["dt"].dropna().unique())
    if len(dates) < 2:
        raise ValueError("provider-type validation requires at least two quote dates")
    cut_index = min(max(int(np.floor(len(dates) * train_fraction)), 1), len(dates) - 1)
    return dates[cut_index], [d.strftime("%Y-%m-%d") for d in dates]


def classify_pairs(
    anchored_quotes: pd.DataFrame,
    changes: pd.DataFrame,
    *,
    min_days: int,
    adoption_share: float,
    active_changes_per_day: float,
) -> pd.DataFrame:
    rows: list[dict] = []
    change_counts = changes.groupby(["model_id", "provider_name"]).size()
    for (model, provider), group in anchored_quotes.groupby(["model_id", "provider_name"]):
        days = int(group["dt"].nunique())
        if days < min_days:
            continue
        share_at_anchor = float(group["at_anchor"].mean())
        median_wedge = float(group["log_wedge"].median())
        n_changes = int(change_counts.get((model, provider), 0))
        change_rate = n_changes / days
        if share_at_anchor >= adoption_share:
            provider_type = "anchor_adopter"
        elif median_wedge >= 0:
            provider_type = "premium_differentiated"
        elif change_rate > active_changes_per_day:
            provider_type = "active_undercutter"
        else:
            provider_type = "static_discounter"
        rows.append(
            {
                "model_id": model,
                "provider_name": provider,
                "provider_type": provider_type,
                "n_days": days,
                "share_days_at_anchor": share_at_anchor,
                "median_log_wedge": median_wedge,
                "n_price_changes": n_changes,
                "changes_per_day": change_rate,
            }
        )
    return pd.DataFrame(rows)


def build_holdout_transitions(
    train_labels: pd.DataFrame,
    holdout_quotes: pd.DataFrame,
    holdout_changes: pd.DataFrame,
    protocol: dict,
) -> pd.DataFrame:
    thresholds = protocol["thresholds"]
    holdout_labels = classify_pairs(
        holdout_quotes,
        holdout_changes,
        min_days=int(thresholds["minimum_holdout_days"]),
        adoption_share=float(thresholds["anchor_adoption_share"]),
        active_changes_per_day=float(thresholds["active_changes_per_day"]),
    )
    keep = holdout_labels.rename(
        columns={
            "provider_type": "holdout_type",
            "n_days": "holdout_days",
            "share_days_at_anchor": "holdout_share_days_at_anchor",
            "median_log_wedge": "holdout_median_log_wedge",
            "n_price_changes": "holdout_price_changes",
            "changes_per_day": "holdout_changes_per_day",
        }
    )
    merged = train_labels.merge(keep, on=["model_id", "provider_name"], how="left")
    merged["holdout_type"] = merged["holdout_type"].fillna("insufficient_holdout")
    merged["type_persisted"] = merged["provider_type"] == merged["holdout_type"]
    return merged


def build_congestion_panels(
    congestion: pd.DataFrame,
    slug_map: pd.DataFrame,
    labels: pd.DataFrame,
    holdout_start: pd.Timestamp,
    gpu_hourly_cost: float,
    batching_factor: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if congestion.empty:
        return pd.DataFrame(), pd.DataFrame()
    panel = congestion[congestion["dt"] >= holdout_start].merge(
        slug_map, left_on="model_permaslug", right_on="canonical_slug", how="left"
    )
    panel["model_id"] = panel["model_id"].fillna(panel["model_permaslug"])
    panel = panel.merge(
        labels[["model_id", "provider_name", "provider_type", "median_log_wedge"]],
        on=["model_id", "provider_name"],
        how="inner",
    )
    if panel.empty:
        return panel, panel.copy()
    peak_utilization = (panel["peak_rpm"] / panel["capacity_rpm"]).replace(
        [np.inf, -np.inf], np.nan
    )
    request_utilization = (panel["requests"] / (30 * panel["capacity_rpm"])).replace(
        [np.inf, -np.inf], np.nan
    )
    panel["utilization"] = peak_utilization.fillna(request_utilization)
    panel["utilization_uses_request_fallback"] = (
        peak_utilization.isna() & request_utilization.notna()
    )
    panel["rate_limit_share"] = (
        panel["rate_limited"] / panel["requests"].clip(lower=1)
    ).clip(0, 1)
    panel["error_share"] = (
        panel["derankable_errors"] / panel["requests"].clip(lower=1)
    ).clip(0, 1)
    panel["log_throughput"] = np.log(panel["throughput"].where(panel["throughput"] > 0))
    panel["log_latency"] = np.log(panel["latency"].where(panel["latency"] > 0))
    for column in ("log_throughput", "log_latency", "utilization", "rate_limit_share"):
        panel[f"{column}_within_model_day"] = panel[column] - panel.groupby(
            ["model_id", "dt"]
        )[column].transform("mean")
    panel["cost_bound_per_token"] = gpu_hourly_cost / (
        panel["throughput"] * 3600 * batching_factor
    )
    panel["below_cost_bound"] = (
        (panel["throughput"] > 0)
        & (panel["price_completion"] > 0)
        & (panel["price_completion"] < panel["cost_bound_per_token"])
    )
    keys = ["model_id", "provider_name", "provider_type"]
    quality = panel.groupby(keys, as_index=False).agg(
        observations=("dt", "size"),
        price_completion=("price_completion", "median"),
        throughput=("throughput", "median"),
        latency=("latency", "median"),
        throughput_advantage=("log_throughput_within_model_day", "median"),
        latency_penalty=("log_latency_within_model_day", "median"),
        rate_limit_share=("rate_limit_share", "mean"),
        error_share=("error_share", "mean"),
    )
    capacity = panel.groupby(keys, as_index=False).agg(
        observations=("dt", "size"),
        utilization=("utilization", "median"),
        capacity_rpm=("capacity_rpm", "median"),
        rate_limit_share=("rate_limit_share", "mean"),
        deranked_share=("is_deranked", "mean"),
        utilization_fallback_share=("utilization_uses_request_fallback", "mean"),
        below_cost_bound_share=("below_cost_bound", "mean"),
        cost_bound_per_token=("cost_bound_per_token", "median"),
        price_completion=("price_completion", "median"),
    )
    return quality, capacity


def build_author_pass_through(
    changes: pd.DataFrame,
    labels: pd.DataFrame,
    holdout_start: pd.Timestamp,
    window_hours: float,
    rtol: float,
) -> pd.DataFrame:
    ch = changes[changes["ts"] >= holdout_start].copy()
    if ch.empty:
        return pd.DataFrame()
    ch["is_author"] = [
        is_author_provider(model, provider)
        for model, provider in zip(ch["model_id"], ch["provider_name"], strict=True)
    ]
    rows: list[dict] = []
    panel_end = ch["ts"].max()
    for event_id, event in ch[ch["is_author"]].reset_index(drop=True).iterrows():
        end = event["ts"] + pd.Timedelta(window_hours, unit="h")
        if end > panel_end:
            continue
        eligible = labels[labels["model_id"] == event["model_id"]]
        for _, pair in eligible.iterrows():
            responses = ch[
                (ch["model_id"] == event["model_id"])
                & (ch["provider_name"] == pair["provider_name"])
                & (ch["ts"] > event["ts"])
                & (ch["ts"] <= end)
            ]
            match = responses[
                np.isclose(responses["new_price"], event["new_price"], rtol=rtol, atol=0)
            ]
            first_match = match["ts"].min() if not match.empty else pd.NaT
            rows.append(
                {
                    "event_id": int(event_id),
                    "event_ts": event["ts"],
                    "model_id": event["model_id"],
                    "author_provider": event["provider_name"],
                    "author_new_price": event["new_price"],
                    "provider_name": pair["provider_name"],
                    "provider_type": pair["provider_type"],
                    "matched_new_anchor": bool(not match.empty),
                    "match_lag_hours": (
                        (first_match - event["ts"]).total_seconds() / 3600
                        if not pd.isna(first_match)
                        else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_response_panel(
    changes: pd.DataFrame,
    labels: pd.DataFrame,
    holdout_start: pd.Timestamp,
    window_hours: float,
    placebo_shift_hours: float,
) -> pd.DataFrame:
    """Compare post-rival response incidence with a frozen shifted-time placebo."""
    ch = changes[changes["ts"] >= holdout_start].copy()
    targets = labels[labels["provider_type"] == "active_undercutter"]
    if ch.empty or targets.empty:
        return pd.DataFrame()
    panel_end = ch["ts"].max()
    rows: list[dict] = []
    for _, target in targets.iterrows():
        own = ch[
            (ch["model_id"] == target["model_id"])
            & (ch["provider_name"] == target["provider_name"])
        ]
        rivals = ch[
            (ch["model_id"] == target["model_id"])
            & (ch["provider_name"] != target["provider_name"])
        ]
        for rival_id, event in rivals.iterrows():
            placebo_ts = event["ts"] + pd.Timedelta(placebo_shift_hours, unit="h")
            # Both arms must be observable for the same target-rival event.
            if placebo_ts + pd.Timedelta(window_hours, unit="h") > panel_end:
                continue
            for arm, event_ts in (
                ("observed", event["ts"]),
                ("shifted_placebo", placebo_ts),
            ):
                end = event_ts + pd.Timedelta(window_hours, unit="h")
                if event_ts < holdout_start:
                    continue
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
                        "rival_event_id": int(rival_id),
                        "event_ts": event_ts,
                        "model_id": target["model_id"],
                        "target_provider": target["provider_name"],
                        "rival_provider": event["provider_name"],
                        "rival_sign": rival_sign,
                        "responded": responded,
                        "same_direction": bool(responded and response_sign == rival_sign),
                        "response_lag_hours": (
                            (response.iloc[0]["ts"] - event_ts).total_seconds() / 3600
                            if responded
                            else np.nan
                        ),
                    }
                )
    return pd.DataFrame(rows)


def build_fade_panel(
    changes: pd.DataFrame,
    labels: pd.DataFrame,
    holdout_start: pd.Timestamp,
    fade_hours: float,
) -> pd.DataFrame:
    ch = changes[changes["ts"] >= holdout_start].copy()
    active = labels[labels["provider_type"] == "active_undercutter"]
    rows: list[dict] = []
    for _, pair in active.iterrows():
        own = ch[
            (ch["model_id"] == pair["model_id"])
            & (ch["provider_name"] == pair["provider_name"])
        ].sort_values("ts")
        cuts = own[own["new_price"] < own["old_price"]]
        for event_id, cut in cuts.iterrows():
            next_change = own[own["ts"] > cut["ts"]].head(1)
            faded = False
            lag = np.nan
            if not next_change.empty:
                lag = (next_change.iloc[0]["ts"] - cut["ts"]).total_seconds() / 3600
                faded = bool(
                    lag <= fade_hours and next_change.iloc[0]["new_price"] > cut["new_price"]
                )
            rows.append(
                {
                    "cut_event_id": int(event_id),
                    "cut_ts": cut["ts"],
                    "model_id": pair["model_id"],
                    "provider_name": pair["provider_name"],
                    "cut_fraction": 1 - cut["new_price"] / cut["old_price"],
                    "faded_within_window": faded,
                    "next_change_lag_hours": lag,
                }
            )
    return pd.DataFrame(rows)


def build_paid_fill_panel(
    attempts: pd.DataFrame, labels: pd.DataFrame, holdout_start: pd.Timestamp
) -> pd.DataFrame:
    columns = [
        "model_id",
        "provider_name",
        "provider_type",
        "probe_mode",
        "attempts",
        "successes",
        "selected_count",
        "mean_latency_ms",
        "total_cost_usd",
    ]
    if attempts.empty:
        return pd.DataFrame(columns=columns)
    frame = attempts[attempts["ts"] >= holdout_start].copy()
    requested_mask = frame["requested_provider"].fillna("").astype(str).str.len() > 0
    targeted = frame[requested_mask].merge(
        labels,
        left_on=["model_id", "requested_provider"],
        right_on=["model_id", "provider_name"],
        how="inner",
    )
    delegated = frame[~requested_mask].merge(
        labels,
        left_on=["model_id", "selected_provider"],
        right_on=["model_id", "provider_name"],
        how="inner",
    )
    targeted["probe_mode"] = "provider_targeted_admission"
    delegated["probe_mode"] = "delegated_routing_selection"
    requested = pd.concat([targeted, delegated], ignore_index=True)
    if requested.empty:
        return pd.DataFrame(columns=columns)
    requested["success"] = requested["outcome"].astype(str).str.lower().isin(
        {"succeeded", "success", "completed"}
    )
    requested["selected"] = requested["selected_provider"] == requested["provider_name"]
    return requested.groupby(
        ["model_id", "provider_name", "provider_type", "probe_mode"], as_index=False
    ).agg(
        attempts=("event_id", "nunique"),
        successes=("success", "sum"),
        selected_count=("selected", "sum"),
        mean_latency_ms=("latency_ms", "mean"),
        total_cost_usd=("cost_usd", "sum"),
    )


def build_dumping_scorecard(
    labels: pd.DataFrame,
    capacity: pd.DataFrame,
    fades: pd.DataFrame,
    fills: pd.DataFrame,
) -> pd.DataFrame:
    score = labels[["model_id", "provider_name", "provider_type", "median_log_wedge"]].copy()
    if capacity.empty:
        score["below_cost_bound_share"] = np.nan
        score["utilization"] = np.nan
    else:
        score = score.merge(
            capacity[
                [
                    "model_id",
                    "provider_name",
                    "below_cost_bound_share",
                    "utilization",
                ]
            ],
            on=["model_id", "provider_name"],
            how="left",
        )
    fade_rates = (
        fades.groupby(["model_id", "provider_name"], as_index=False).agg(
            cut_events=("cut_event_id", "size"),
            fade_share=("faded_within_window", "mean"),
        )
        if not fades.empty
        else pd.DataFrame(columns=["model_id", "provider_name", "cut_events", "fade_share"])
    )
    score = score.merge(fade_rates, on=["model_id", "provider_name"], how="left")
    if fills.empty:
        score["selected_count"] = 0
        score["paid_attempts"] = 0
    else:
        delegated = fills[fills["probe_mode"] == "delegated_routing_selection"]
        score = score.merge(
            delegated[["model_id", "provider_name", "attempts", "selected_count"]].rename(
                columns={"attempts": "paid_attempts"}
            ),
            on=["model_id", "provider_name"],
            how="left",
        )
    score["selected_count"] = score["selected_count"].fillna(0)
    score["paid_attempts"] = score["paid_attempts"].fillna(0)
    score["active_strategy_leg"] = score["provider_type"] == "active_undercutter"
    score["apparent_cost_sacrifice_leg"] = score["below_cost_bound_share"].fillna(0) >= 0.5
    score["temporary_cut_leg"] = score["fade_share"].fillna(0) > 0
    score["realized_flow_leg"] = score["selected_count"] > 0
    legs = [
        "active_strategy_leg",
        "apparent_cost_sacrifice_leg",
        "temporary_cut_leg",
        "realized_flow_leg",
    ]
    score["candidate_score"] = score[legs].sum(axis=1).astype(int)
    score["dumping_candidate"] = score[legs].all(axis=1)
    score["dumping_supported"] = False
    score["missing_identification_leg"] = (
        "marginal cost and later recoupment/subsidy are not observed"
    )
    return score.sort_values(["candidate_score", "median_log_wedge"], ascending=[False, True])


def response_inference(response: pd.DataFrame, bootstrap_draws: int = 5000) -> dict:
    if response.empty:
        return {"evidence_status": "power_gated", "gate": "no paired response windows"}
    index = ["model_id", "target_provider", "rival_event_id"]
    paired = response.pivot_table(index=index, columns="arm", values="responded", aggfunc="max")
    paired = paired.dropna(subset=["observed", "shifted_placebo"])
    if paired.empty:
        return {"evidence_status": "power_gated", "gate": "no complete response pairs"}
    paired = paired.astype(float).reset_index()
    paired["difference"] = paired["observed"] - paired["shifted_placebo"]
    discordant_positive = int(
        ((paired["observed"] == 1) & (paired["shifted_placebo"] == 0)).sum()
    )
    discordant_negative = int(
        ((paired["observed"] == 0) & (paired["shifted_placebo"] == 1)).sum()
    )
    discordant = discordant_positive + discordant_negative
    pvalue = (
        float(binomtest(discordant_positive, discordant, 0.5, alternative="greater").pvalue)
        if discordant
        else 1.0
    )
    clusters = paired.groupby(["model_id", "target_provider"])["difference"].mean().to_numpy()
    rng = np.random.default_rng(20260720)
    if len(clusters) >= 2:
        draws = rng.choice(
            clusters, size=(bootstrap_draws, len(clusters)), replace=True
        ).mean(axis=1)
        interval = [round(float(x), 4) for x in np.quantile(draws, [0.025, 0.975])]
    else:
        interval = None
    return {
        "evidence_status": "paired_placebo_screen",
        "paired_events": int(len(paired)),
        "target_provider_model_clusters": int(len(clusters)),
        "observed_minus_placebo": round(float(paired["difference"].mean()), 4),
        "target_cluster_bootstrap_95ci": interval,
        "discordant_observed_only": discordant_positive,
        "discordant_placebo_only": discordant_negative,
        "one_sided_exact_p_observed_greater": round(pvalue, 6),
        "claim_boundary": (
            "The exact test is event-paired but events share provider-model clusters; the "
            "cluster bootstrap is therefore the preferred uncertainty summary. The shifted "
            "window is a timing placebo, not randomized treatment."
        ),
    }


def qos_inference(quality: pd.DataFrame) -> dict:
    if quality.empty:
        return {"evidence_status": "power_gated", "gate": "no matched QoS observations"}
    premium = quality[quality["provider_type"] == "premium_differentiated"]
    other = quality[quality["provider_type"] != "premium_differentiated"]
    output = {"evidence_status": "holdout_association"}
    for metric, alternative in (
        ("throughput_advantage", "greater"),
        ("latency_penalty", "less"),
    ):
        left = premium[metric].dropna()
        right = other[metric].dropna()
        if len(left) < 3 or len(right) < 3:
            output[metric] = {"gate": "fewer than three pairs in a comparison arm"}
            continue
        test = mannwhitneyu(left, right, alternative=alternative)
        output[metric] = {
            "premium_pairs": int(len(left)),
            "other_pairs": int(len(right)),
            "premium_median": round(float(left.median()), 5),
            "other_median": round(float(right.median()), 5),
            "one_sided_pvalue": round(float(test.pvalue), 6),
        }
    output["claim_boundary"] = (
        "Tests use provider-model aggregates of within-model-day residuals. They are "
        "associational and do not identify custom hardware, kernels, or selection into QoS data."
    )
    return output


def _group_summary(frame: pd.DataFrame, group: str, value: str) -> dict:
    if frame.empty or value not in frame:
        return {}
    output = {}
    for name, values in frame.groupby(group)[value]:
        clean = values.dropna()
        output[str(name)] = {
            "n": int(len(clean)),
            "median": round(float(clean.median()), 5) if len(clean) else None,
            "mean": round(float(clean.mean()), 5) if len(clean) else None,
        }
    return output


def _render_figure(
    out_dir: Path,
    transitions: pd.DataFrame,
    quality: pd.DataFrame,
    response: pd.DataFrame,
    dumping: pd.DataFrame,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)

    matrix = pd.crosstab(transitions["provider_type"], transitions["holdout_type"])
    matrix = matrix.reindex(index=TYPE_ORDER, columns=TYPE_ORDER, fill_value=0)
    denom = matrix.sum(axis=1).replace(0, np.nan)
    shares = matrix.div(denom, axis=0).fillna(0)
    im = axes[0, 0].imshow(shares, vmin=0, vmax=1, cmap="Blues")
    for row in range(len(TYPE_ORDER)):
        for column in range(len(TYPE_ORDER)):
            axes[0, 0].text(
                column,
                row,
                f"{shares.iloc[row, column]:.0%}\n(n={matrix.iloc[row, column]})",
                ha="center",
                va="center",
                fontsize=8,
                color="white" if shares.iloc[row, column] > 0.55 else "black",
            )
    axes[0, 0].set_xticks(range(len(TYPE_ORDER)), [x.replace("_", "\n") for x in TYPE_ORDER])
    axes[0, 0].set_yticks(range(len(TYPE_ORDER)), [x.replace("_", " ") for x in TYPE_ORDER])
    axes[0, 0].set_title("A. Out-of-sample type persistence")
    axes[0, 0].set_xlabel("Holdout label")
    axes[0, 0].set_ylabel("Training label")
    fig.colorbar(im, ax=axes[0, 0], fraction=0.046, label="Row share")

    wedge_data = [
        transitions.loc[transitions["provider_type"] == kind, "holdout_median_log_wedge"].dropna()
        for kind in TYPE_ORDER
    ]
    axes[0, 1].boxplot(wedge_data, tick_labels=[x.replace("_", "\n") for x in TYPE_ORDER])
    axes[0, 1].axhline(0, color="black", linewidth=1)
    axes[0, 1].set_title("B. Holdout quote wedge by frozen type")
    axes[0, 1].set_ylabel("log(provider price / author price)")

    colors = dict(zip(TYPE_ORDER, ["#7A5195", "#2F4B7C", "#FFA600", "#D45087"], strict=True))
    if quality.empty:
        axes[1, 0].text(0.5, 0.5, "No matched holdout QoS", ha="center", va="center")
    else:
        for kind, group in quality.groupby("provider_type"):
            axes[1, 0].scatter(
                group["throughput_advantage"],
                group["latency_penalty"],
                s=np.clip(group["observations"], 10, 180),
                alpha=0.65,
                label=kind.replace("_", " "),
                color=colors.get(kind, "grey"),
            )
        axes[1, 0].axhline(0, color="grey", linewidth=0.8)
        axes[1, 0].axvline(0, color="grey", linewidth=0.8)
        axes[1, 0].legend(fontsize=7, frameon=False)
    axes[1, 0].set_title("C. Delivered QoS relative to same model-day")
    axes[1, 0].set_xlabel("log throughput advantage (right is better)")
    axes[1, 0].set_ylabel("log latency penalty (down is better)")

    response_rates = (
        response.groupby("arm")["responded"].agg(["mean", "size"])
        if not response.empty
        else pd.DataFrame()
    )
    if response_rates.empty:
        axes[1, 1].text(0.5, 0.5, "No eligible rival-move windows", ha="center", va="center")
    else:
        labels = ["Observed rival move", "Shifted-time placebo"]
        keys = ["observed", "shifted_placebo"]
        values = [
            float(response_rates.loc[key, "mean"]) if key in response_rates.index else 0
            for key in keys
        ]
        ns = [
            int(response_rates.loc[key, "size"]) if key in response_rates.index else 0
            for key in keys
        ]
        bars = axes[1, 1].bar(labels, values, color=["#D45087", "#9CA3AF"])
        for bar, value, n in zip(bars, values, ns, strict=True):
            axes[1, 1].text(
                bar.get_x() + bar.get_width() / 2,
                value,
                f"{value:.1%}\nN={n}",
                ha="center",
                va="bottom",
            )
        axes[1, 1].set_ylim(0, min(1, max(values + [0.05]) * 1.3))
    candidates = int(dumping["dumping_candidate"].sum()) if not dumping.empty else 0
    axes[1, 1].set_title(f"D. Active-undercutter response timing (strict candidates: {candidates})")
    axes[1, 1].set_ylabel("Repriced within frozen window")

    fig.suptitle(
        "Provider pricing types: frozen labels, future outcomes, bounded interpretation",
        fontsize=15,
    )
    for extension in ("png", "pdf"):
        fig.savefig(out_dir / f"wf16_provider_type_validation.{extension}", dpi=200)
    plt.close(fig)


def run(out_dir: Path = DEFAULT_OUT, config_path: Path = DEFAULT_CONFIG) -> dict:
    protocol, protocol_sha = load_protocol(config_path)
    thresholds = protocol["thresholds"]
    windows = protocol["windows"]
    cost = protocol["cost_screen"]
    with data.pinned_analysis_source() as source:
        quotes = load_daily_quotes()
        changes = load_price_changes()
        slug_map = load_slug_map()
        congestion = load_congestion()
        attempts = load_paid_attempts()

    anchored = add_author_anchor(quotes, float(thresholds["anchor_match_rtol"]))
    holdout_start, all_dates = split_dates(anchored, float(protocol["study"]["train_fraction"]))
    train_quotes = anchored[anchored["dt"] < holdout_start]
    holdout_quotes = anchored[anchored["dt"] >= holdout_start]
    train_changes = changes[changes["dt"] < holdout_start]
    holdout_changes = changes[changes["dt"] >= holdout_start]
    labels = classify_pairs(
        train_quotes,
        train_changes,
        min_days=int(thresholds["minimum_train_days"]),
        adoption_share=float(thresholds["anchor_adoption_share"]),
        active_changes_per_day=float(thresholds["active_changes_per_day"]),
    )
    if labels.empty:
        raise RuntimeError("no provider-model pairs passed the frozen training support gate")
    registry = tiers()
    labels["capital_tier"] = [tier_of(provider, registry) for provider in labels["provider_name"]]
    provider_lower = labels["provider_name"].str.lower()
    labels["china_linked_name_tag"] = provider_lower.str.contains("|".join(CHINA), regex=True)
    labels["web3_name_tag"] = provider_lower.str.contains("|".join(WEB3), regex=True)

    transitions = build_holdout_transitions(
        labels, holdout_quotes, holdout_changes, protocol
    )
    quality, capacity = build_congestion_panels(
        congestion,
        slug_map,
        labels,
        holdout_start,
        float(cost["gpu_hourly_cost_usd"]),
        float(cost["batching_factor"]),
    )
    pass_through = build_author_pass_through(
        changes,
        labels,
        holdout_start,
        float(windows["author_pass_through_hours"]),
        float(thresholds["anchor_match_rtol"]),
    )
    response = build_response_panel(
        changes,
        labels,
        holdout_start,
        float(windows["rival_response_hours"]),
        float(windows["placebo_shift_hours"]),
    )
    fades = build_fade_panel(
        changes, labels, holdout_start, float(windows["fade_hours"])
    )
    fills = build_paid_fill_panel(attempts, labels, holdout_start)
    dumping = build_dumping_scorecard(labels, capacity, fades, fills)

    save(labels, out_dir, "wf16_provider_type_labels")
    save(transitions, out_dir, "wf16_holdout_transitions")
    save(quality, out_dir, "wf16_qos_panel")
    save(pass_through, out_dir, "wf16_author_pass_through")
    save(capacity, out_dir, "wf16_capacity_panel")
    save(fills, out_dir, "wf16_paid_fill_panel")
    save(response, out_dir, "wf16_active_response")
    save(fades, out_dir, "wf16_quote_fades")
    save(dumping, out_dir, "wf16_dumping_candidates")
    _render_figure(out_dir, transitions, quality, response, dumping)

    evaluated = transitions[transitions["holdout_type"] != "insufficient_holdout"]
    persisted = int(evaluated["type_persisted"].sum())
    response_stats = {}
    for arm, group in response.groupby("arm") if not response.empty else []:
        successes = int(group["responded"].sum())
        response_stats[str(arm)] = {
            "events": int(len(group)),
            "response_rate": round(successes / len(group), 4),
            "response_rate_95ci": _wilson(successes, len(group)),
            "same_direction_rate": round(float(group["same_direction"].mean()), 4),
        }
    pass_stats = {}
    for kind, group in pass_through.groupby("provider_type") if not pass_through.empty else []:
        successes = int(group["matched_new_anchor"].sum())
        pass_stats[str(kind)] = {
            "provider_events": int(len(group)),
            "match_rate": round(successes / len(group), 4),
            "match_rate_95ci": _wilson(successes, len(group)),
            "median_lag_hours": (
                round(float(group["match_lag_hours"].median()), 2)
                if group["match_lag_hours"].notna().any()
                else None
            ),
        }
    type_counts = labels["provider_type"].value_counts().reindex(TYPE_ORDER, fill_value=0)
    targeted_fills = fills[fills["probe_mode"] == "provider_targeted_admission"]
    delegated_fills = fills[fills["probe_mode"] == "delegated_routing_selection"]
    persistence_by_type = {}
    for kind, group in evaluated.groupby("provider_type"):
        successes = int(group["type_persisted"].sum())
        persistence_by_type[str(kind)] = {
            "pairs": int(len(group)),
            "persisted": successes,
            "rate": round(successes / len(group), 4),
            "rate_95ci": _wilson(successes, len(group)),
        }
    transition_counts = (
        pd.crosstab(evaluated["provider_type"], evaluated["holdout_type"])
        .reindex(index=TYPE_ORDER, columns=TYPE_ORDER, fill_value=0)
        .to_dict("index")
    )
    targeted_by_type = {}
    for kind, group in targeted_fills.groupby("provider_type"):
        total = int(group["attempts"].sum())
        successes = int(group["successes"].sum())
        targeted_by_type[str(kind)] = {
            "attempts": total,
            "admissions": successes,
            "admission_rate": round(successes / total, 4) if total else None,
            "admission_rate_95ci": _wilson(successes, total),
        }
    delegated_counts = delegated_fills.groupby("provider_type")["selected_count"].sum()
    delegated_total = int(delegated_counts.sum())
    delegated_by_type = {
        str(kind): {
            "selections": int(count),
            "raw_selection_share": round(float(count / delegated_total), 4)
            if delegated_total
            else None,
        }
        for kind, count in delegated_counts.items()
    }
    summary = {
        "study_id": protocol["study"]["id"],
        "evidence_status": "out_of_sample_descriptive",
        "source": source,
        "protocol_sha256": protocol_sha,
        "date_range": [all_dates[0], all_dates[-1]],
        "holdout_start": holdout_start.strftime("%Y-%m-%d"),
        "n_training_pairs": int(len(labels)),
        "type_counts": {str(k): int(v) for k, v in type_counts.items()},
        "capital_tier_by_type": labels.groupby("provider_type")["capital_tier"]
        .value_counts()
        .unstack(fill_value=0)
        .to_dict("index"),
        "name_tags_by_type": labels.groupby("provider_type")[[
            "china_linked_name_tag",
            "web3_name_tag",
        ]]
        .mean()
        .round(4)
        .to_dict("index"),
        "holdout_evaluable_pairs": int(len(evaluated)),
        "overall_type_persistence": round(persisted / len(evaluated), 4)
        if len(evaluated)
        else None,
        "overall_type_persistence_95ci": _wilson(persisted, len(evaluated)),
        "persistence_by_type": persistence_by_type,
        "holdout_transition_counts": transition_counts,
        "holdout_wedge_by_frozen_type": _group_summary(
            transitions, "provider_type", "holdout_median_log_wedge"
        ),
        "qos_by_frozen_type": {
            "throughput_advantage": _group_summary(
                quality, "provider_type", "throughput_advantage"
            ),
            "latency_penalty": _group_summary(quality, "provider_type", "latency_penalty"),
        },
        "premium_qos_test": qos_inference(quality),
        "capacity_by_frozen_type": {
            "utilization": _group_summary(capacity, "provider_type", "utilization"),
            "below_cost_bound_share": _group_summary(
                capacity, "provider_type", "below_cost_bound_share"
            ),
        },
        "capacity_utilization_support": {
            "provider_model_pairs_with_measure": int(capacity["utilization"].notna().sum())
            if not capacity.empty
            else 0,
            "status": "measured"
            if not capacity.empty and capacity["utilization"].notna().any()
            else "power_gated_missing_capacity_ceiling_or_load",
        },
        "author_pass_through": pass_stats
        if pass_stats
        else {"evidence_status": "power_gated", "gate": "no evaluable author move"},
        "active_response_vs_shifted_placebo": response_stats,
        "active_response_paired_inference": response_inference(response),
        "paid_targeted_attempts_matched": int(targeted_fills["attempts"].sum())
        if not targeted_fills.empty
        else 0,
        "paid_targeted_admissions_matched": int(targeted_fills["successes"].sum())
        if not targeted_fills.empty
        else 0,
        "paid_delegated_attempts_matched": int(delegated_fills["attempts"].sum())
        if not delegated_fills.empty
        else 0,
        "paid_delegated_selections_matched": int(delegated_fills["selected_count"].sum())
        if not delegated_fills.empty
        else 0,
        "targeted_admission_by_type": targeted_by_type,
        "delegated_selection_by_type": delegated_by_type,
        "delegated_selection_boundary": (
            "Raw selection shares are from the owned default-probe model mix and are not "
            "market-wide flow shares or a randomized comparison across provider types."
        ),
        "strict_dumping_candidates": int(dumping["dumping_candidate"].sum()),
        "dumping_supported": False,
        "claim_boundary": (
            "The four labels are frozen provider-model-period regimes, not immutable provider "
            "types. They describe training-period quotes and cadence. "
            "Holdout persistence, QoS, capacity, pass-through, response timing, and owned "
            "price-response fills are separate evidence legs. Rival-move timing is not causal "
            "proof of observation or front-running. The GPU cost bound depends on a stated "
            "hardware and batching scenario. Marginal cost, private rebates, subsidies, intent, "
            "and recoupment are unobserved, so no provider is identified as predatory dumping."
        ),
    }
    save_json(summary, out_dir, "wf16_summary")
    (out_dir / "source-revision.txt").write_text(
        str(source.get("revision") or "local") + "\n", encoding="utf-8"
    )
    log.info("WF16: %s", json.dumps(summary, default=str))
    return summary


if __name__ == "__main__":
    run()
