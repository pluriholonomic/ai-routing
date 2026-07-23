"""H42 — auditable tests for MEV-like routing-volume capture.

The public data cannot observe a request mempool, customer intent, or provider
costs.  H42 therefore tests the observable precursor: a quote or competitor
shock changes a provider's relative price/rank, then its routing-flow proxy.
It labels all results descriptive until the event and power gates in
``docs/routing-mev-research-plan.md`` are met.

Outputs:
  h42_routing_event_panel      one price event x provider quote, before/after
  h42_routing_event_intraday   event-time 30-minute rolling flow proxies
  h42_routing_event_quality    explicit inclusion/exclusion ledger
  h42_event_effects            per-event pre/post flow and quality changes
  h42_summary                  R1-R4 coverage and power-gated diagnostics
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

INTRADAY_PRE_MINUTES = 60
INTRADAY_POST_MINUTES = 180
MIN_INTRADAY_EVENTS = 20


def _ts(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce")


def _sum_observed(values: pd.Series) -> float:
    """Preserve a missing source field as missing rather than manufacturing zero flow."""
    total = values.sum(min_count=1)
    return float(total) if pd.notna(total) else np.nan


def _mean_observed(values: pd.Series) -> float:
    """Keep an all-missing nullable aggregate as NaN rather than raising."""
    mean = values.mean()
    return float(mean) if pd.notna(mean) else np.nan


def _empty_panel() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "event_id",
            "event_ts",
            "run_ts",
            "model_id",
            "model_permaslug",
            "provider_name",
            "target_provider",
            "is_focal",
            "is_stale_beneficiary",
            "price_before",
            "price_after",
            "rank_before",
            "rank_after",
            "relative_price_before",
            "relative_price_after",
            "best_other_before",
            "best_other_after",
            "n_providers",
            "is_cut",
            "is_raise",
            "rank_improved",
            "newly_best",
            "provider_wave",
            "competitor_event_prior_48h",
            "simultaneous_price_events",
            "focal_snapshot_matched",
            "eligible_quote",
        ]
    )


def _empty_intraday() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "event_id",
            "event_ts",
            "model_id",
            "model_permaslug",
            "provider_name",
            "run_ts",
            "relative_minutes",
            "is_focal",
            "is_stale_beneficiary",
            "n_quote_providers",
            "request_count_30m",
            "success_30m",
            "rate_limited_30m",
            "derankable_error_30m",
            "reject_rate_30m",
            "request_share_30m",
            "capacity_ceiling_rpm",
            "recent_peak_rpm",
            "p90_latency_ms",
            "n_flow_providers",
        ]
    )


def load_price_events() -> pd.DataFrame:
    """Load only completion-price changes; additions/removals are separate events."""
    rows = data.q(
        f"""
        select changed_at_run_ts, model_id, provider_name, tag, endpoint_fingerprint,
               old_value, new_value
        from read_parquet('{data.table_glob("pricing_changes", "derived")}')
        where field = 'price_completion'
          and old_value is not null and new_value is not null
        """
    ).df()
    if rows.empty:
        return rows
    for col in ("tag", "endpoint_fingerprint"):
        rows[col] = rows[col].fillna("").astype(str)
    rows["old_price"] = pd.to_numeric(rows["old_value"], errors="coerce")
    rows["new_price"] = pd.to_numeric(rows["new_value"], errors="coerce")
    rows["event_ts"] = _ts(rows["changed_at_run_ts"])
    rows = rows.dropna(subset=["event_ts", "model_id", "provider_name", "old_price", "new_price"])
    rows = rows[(rows["old_price"] > 0) & (rows["new_price"] > 0)].copy()
    rows["event_id"] = (
        rows["changed_at_run_ts"].astype(str)
        + "|"
        + rows["model_id"].astype(str)
        + "|"
        + rows["provider_name"].astype(str)
        + "|"
        + rows["tag"]
        + "|"
        + rows["endpoint_fingerprint"]
    )
    return annotate_event_context(rows)


def annotate_event_context(events: pd.DataFrame) -> pd.DataFrame:
    """Add pre-specified exclusion flags without guessing at event causality."""
    if events.empty:
        return events.copy()
    out = events.sort_values("event_ts").copy()
    waves, competitors = [], []
    for row in out.itertuples(index=False):
        provider_peers = out[
            (out["provider_name"] == row.provider_name)
            & (out["model_id"] != row.model_id)
            & ((out["event_ts"] - row.event_ts).abs() <= pd.Timedelta("12h"))
        ]
        prior_competitors = out[
            (out["model_id"] == row.model_id)
            & (out["provider_name"] != row.provider_name)
            & (out["event_ts"] < row.event_ts)
            & (row.event_ts - out["event_ts"] <= pd.Timedelta("48h"))
        ]
        waves.append(bool(len(provider_peers)))
        competitors.append(bool(len(prior_competitors)))
    out["provider_wave"] = waves
    out["competitor_event_prior_48h"] = competitors
    out["simultaneous_price_events"] = out.groupby(["changed_at_run_ts", "model_id"])[
        "event_id"
    ].transform("size")
    return out


def load_snapshots_for_events() -> pd.DataFrame:
    """Read only quote snapshots needed to reconstruct each price-event market."""
    return data.q(
        f"""
        with events as (
          select distinct changed_at_run_ts, model_id
          from read_parquet('{data.table_glob("pricing_changes", "derived")}')
          where field = 'price_completion'
            and old_value is not null and new_value is not null
        )
        select s.run_ts, s.model_id, s.provider_name, s.tag, s.endpoint_fingerprint,
               s.price_completion, s.status, s.uptime_last_5m,
               s.latency_last_30m, s.throughput_last_30m
        from read_parquet('{data.table_glob("endpoints_snapshots")}') s
        inner join events e
          on s.run_ts = e.changed_at_run_ts and s.model_id = e.model_id
        where s.price_completion > 0 and s.provider_name is not null
        """
    ).df()


def event_model_slugs(events: pd.DataFrame) -> pd.DataFrame:
    """Map stable event ids to the versioned frontend congestion permaslugs.

    The endpoint quote API exposes stable model ids (for example
    ``z-ai/glm-5.2``), whereas the frontend stats API records versioned
    canonical slugs.  Taking the latest observed mapping is safe for the
    short live panel and is strictly better than silently dropping every
    stable-id event from the congestion join.
    """
    base = events.loc[:, ["model_id"]].drop_duplicates().copy()
    if base.empty:
        return base.assign(model_permaslug=pd.Series(dtype="object"))
    quoted = ", ".join(
        "'" + str(x).replace("'", "''") + "'" for x in sorted(base["model_id"])
    )
    try:
        mapping = data.q(
            f"""
            select id as model_id, canonical_slug as model_permaslug
            from (
              select id, canonical_slug, run_ts,
                     row_number() over (partition by id order by run_ts desc) as rn
              from {data.models_snapshots()}
              where id in ({quoted}) and canonical_slug is not null
            ) where rn = 1
            """
        ).df()
    except Exception as exc:
        log.info("H42 canonical model mapping unavailable: %s", exc)
        mapping = pd.DataFrame(columns=["model_id", "model_permaslug"])
    return base.merge(mapping, on="model_id", how="left").assign(
        model_permaslug=lambda d: d["model_permaslug"].fillna(d["model_id"])
    )


def _sql_string(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def load_congestion(
    events: pd.DataFrame, model_slugs: pd.DataFrame
) -> pd.DataFrame:
    """Load only flow-proxy rows for models with price events.

    Congestion counts are 30-minute rolling statistics.  The resulting panel
    is intentionally named ``request_share_30m`` rather than minute fills.
    Event windows are joined in DuckDB before materialization. This is
    algebraically identical to the later event-time filter, but avoids a
    model-wide event-by-tick Cartesian product in pandas.
    """
    if events.empty or model_slugs.empty:
        return pd.DataFrame()
    windows = (
        events.loc[:, ["event_id", "event_ts", "model_id"]]
        .merge(model_slugs, on="model_id", how="left")
        .dropna(subset=["event_id", "event_ts", "model_permaslug"])
        .drop_duplicates("event_id")
    )
    if windows.empty:
        return pd.DataFrame()
    values = []
    for row in windows.itertuples(index=False):
        start = (row.event_ts - pd.Timedelta(minutes=INTRADAY_PRE_MINUTES)).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        end = (row.event_ts + pd.Timedelta(minutes=INTRADAY_POST_MINUTES)).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        values.append(
            "("
            + ", ".join(
                (
                    _sql_string(row.event_id),
                    _sql_string(row.model_permaslug),
                    _sql_string(start),
                    _sql_string(end),
                )
            )
            + ")"
        )
    event_values = ",\n".join(values)
    frames = []
    for table in ("congestion_intraday", "event_bursts_congestion"):
        try:
            frame = data.q(
                f"""
                with event_windows(
                  event_id, model_permaslug, window_start, window_end
                ) as (
                  values {event_values}
                )
                select e.event_id, f.run_ts, f.model_permaslug, f.provider_name,
                       f.endpoint_uuid, f.request_count_30m, f.success_30m,
                       f.rate_limited_30m, f.derankable_error_30m,
                       f.capacity_ceiling_rpm, f.recent_peak_rpm,
                       f.p90_latency_ms, f.is_deranked
                from read_parquet('{data.table_glob(table)}') f
                inner join event_windows e
                  on f.model_permaslug = e.model_permaslug
                 and f.run_ts between e.window_start and e.window_end
                """
            ).df()
            if not frame.empty:
                frame["flow_source"] = table
                frames.append(frame)
        except Exception as exc:
            log.info("H42 %s unavailable: %s", table, exc)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # Prefer the targeted event-burst sample when both collectors observed the
    # same endpoint at the same timestamp; otherwise counts would be doubled.
    out["source_priority"] = (out["flow_source"] == "event_bursts_congestion").astype(int)
    return (
        out.sort_values("source_priority")
        .drop_duplicates(
            [
                "event_id",
                "run_ts",
                "model_permaslug",
                "provider_name",
                "endpoint_uuid",
            ],
            keep="last",
        )
        .drop(columns="source_priority")
    )


def _provider_prices(market: pd.DataFrame) -> pd.Series:
    return market.groupby("provider_name", sort=False)["price"].min().sort_index()


def _rank_and_relative(prices: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ranks = prices.rank(method="min", ascending=True).astype(int)
    best_other, relative = {}, {}
    for provider, price in prices.items():
        others = prices.drop(index=provider)
        other = float(others.min()) if len(others) else np.nan
        best_other[provider] = other
        relative[provider] = float(np.log(price / other)) if other > 0 else np.nan
    return ranks, pd.Series(best_other), pd.Series(relative)


def build_event_panel(
    events: pd.DataFrame, snapshots: pd.DataFrame, model_slugs: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Reconstruct provider quote ranks immediately before and after each event.

    The change ledger supplies the focal endpoint's old price; the matching
    endpoint snapshot supplies the post-event market.  Events sharing a model
    and timestamp are retained but explicitly flagged as simultaneous, so no
    analysis silently assumes all competitors stood still.
    """
    if events.empty or snapshots.empty:
        return _empty_panel()
    ev = events.copy()
    if "provider_wave" not in ev:
        ev = annotate_event_context(ev)
    snap = snapshots.copy()
    for col in ("tag", "endpoint_fingerprint"):
        snap[col] = snap[col].fillna("").astype(str)
        ev[col] = ev[col].fillna("").astype(str)
    snap["price_completion"] = pd.to_numeric(snap["price_completion"], errors="coerce")
    snap = snap[(snap["price_completion"] > 0) & snap["provider_name"].notna()].copy()
    if snap.empty:
        return _empty_panel()
    slug_map: dict[str, str] = {}
    if model_slugs is not None and not model_slugs.empty:
        slug_map = dict(
            model_slugs.dropna(subset=["model_id", "model_permaslug"])
            .drop_duplicates("model_id")
            .loc[:, ["model_id", "model_permaslug"]]
            .itertuples(index=False, name=None)
        )

    records: list[dict] = []
    for event in ev.itertuples(index=False):
        market = snap[
            (snap["run_ts"] == event.changed_at_run_ts) & (snap["model_id"] == event.model_id)
        ].copy()
        if market.empty:
            continue
        target = (
            (market["provider_name"] == event.provider_name)
            & (market["tag"] == event.tag)
            & (market["endpoint_fingerprint"] == event.endpoint_fingerprint)
        )
        focal_snapshot_matched = bool(target.any())
        market["price"] = market["price_completion"]
        before_market = market.copy()
        if focal_snapshot_matched:
            before_market.loc[target, "price"] = float(event.old_price)

        before = _provider_prices(before_market)
        after = _provider_prices(market)
        providers = before.index.union(after.index)
        if len(providers) < 2:
            continue
        before = before.reindex(providers)
        after = after.reindex(providers)
        rank_before, best_before, rel_before = _rank_and_relative(before)
        rank_after, best_after, rel_after = _rank_and_relative(after)
        focal_before = before.get(event.provider_name, np.nan)
        focal_after = after.get(event.provider_name, np.nan)
        is_cut = bool(focal_snapshot_matched and focal_after < focal_before)
        is_raise = bool(focal_snapshot_matched and focal_after > focal_before)
        eligible_quote = bool(
            focal_snapshot_matched
            and len(providers) >= 2
            and int(event.simultaneous_price_events) == 1
            and focal_before > 0
            and focal_after > 0
        )
        for provider in providers:
            is_focal = provider == event.provider_name
            unchanged = bool(np.isclose(before[provider], after[provider]))
            stale_beneficiary = bool(
                not is_focal
                and unchanged
                and rank_before[provider] > 1
                and rank_after[provider] == 1
            )
            records.append(
                {
                    "event_id": event.event_id,
                    "event_ts": event.event_ts,
                    "run_ts": event.changed_at_run_ts,
                    "model_id": event.model_id,
                    "model_permaslug": slug_map.get(event.model_id, event.model_id),
                    "provider_name": provider,
                    "target_provider": event.provider_name,
                    "target_tag": event.tag,
                    "target_endpoint_fingerprint": event.endpoint_fingerprint,
                    "is_focal": is_focal,
                    "is_stale_beneficiary": stale_beneficiary,
                    "n_quote_providers": int(len(providers)),
                    "price_before": float(before[provider]),
                    "price_after": float(after[provider]),
                    "rank_before": int(rank_before[provider]),
                    "rank_after": int(rank_after[provider]),
                    "best_other_before": float(best_before[provider])
                    if pd.notna(best_before[provider])
                    else np.nan,
                    "best_other_after": float(best_after[provider])
                    if pd.notna(best_after[provider])
                    else np.nan,
                    "relative_price_before": float(rel_before[provider])
                    if pd.notna(rel_before[provider])
                    else np.nan,
                    "relative_price_after": float(rel_after[provider])
                    if pd.notna(rel_after[provider])
                    else np.nan,
                    "n_providers": int(len(providers)),
                    "is_cut": is_cut if is_focal else False,
                    "is_raise": is_raise if is_focal else False,
                    "rank_improved": bool(rank_after[provider] < rank_before[provider]),
                    "newly_best": bool(rank_before[provider] > 1 and rank_after[provider] == 1),
                    "provider_wave": bool(event.provider_wave),
                    "competitor_event_prior_48h": bool(event.competitor_event_prior_48h),
                    "simultaneous_price_events": int(event.simultaneous_price_events),
                    "focal_snapshot_matched": focal_snapshot_matched,
                    "eligible_quote": eligible_quote,
                }
            )
    return pd.DataFrame(records) if records else _empty_panel()


def attach_intraday(panel: pd.DataFrame, congestion: pd.DataFrame) -> pd.DataFrame:
    """Attach per-provider rolling request statistics to event-time quote rows."""
    if panel.empty or congestion.empty:
        return _empty_intraday()
    p = panel[
        [
            "event_id",
            "event_ts",
            "model_id",
            "model_permaslug",
            "provider_name",
            "is_focal",
            "is_stale_beneficiary",
            "n_quote_providers",
        ]
    ].drop_duplicates()
    c = congestion.copy()
    required = [
        "run_ts",
        "model_permaslug",
        "provider_name",
        "request_count_30m",
        "success_30m",
        "rate_limited_30m",
        "derankable_error_30m",
        "capacity_ceiling_rpm",
        "recent_peak_rpm",
        "p90_latency_ms",
    ]
    for col in required:
        if col not in c:
            c[col] = np.nan
    merge_keys = ["model_permaslug", "provider_name"]
    congestion_columns = required
    if "event_id" in c:
        # Current loaders pre-link rows to exact event windows in DuckDB. The
        # fallback keeps this pure function compatible with historical fixtures.
        merge_keys = ["event_id", *merge_keys]
        congestion_columns = ["event_id", *required]
    merged = p.merge(c[congestion_columns], on=merge_keys, how="inner")
    if merged.empty:
        return _empty_intraday()
    merged["tick_ts"] = _ts(merged["run_ts"])
    merged["relative_minutes"] = (merged["tick_ts"] - merged["event_ts"]).dt.total_seconds() / 60
    merged = merged[
        merged["relative_minutes"].between(-INTRADAY_PRE_MINUTES, INTRADAY_POST_MINUTES)
    ].copy()
    if merged.empty:
        return _empty_intraday()
    numeric = [
        "request_count_30m",
        "success_30m",
        "rate_limited_30m",
        "derankable_error_30m",
        "capacity_ceiling_rpm",
        "recent_peak_rpm",
        "p90_latency_ms",
    ]
    for col in numeric:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    keys = [
        "event_id",
        "event_ts",
        "model_id",
        "model_permaslug",
        "provider_name",
        "run_ts",
        "relative_minutes",
        "is_focal",
        "is_stale_beneficiary",
        "n_quote_providers",
    ]
    out = (
        merged.groupby(keys, as_index=False)
        .agg(
            request_count_30m=("request_count_30m", _sum_observed),
            success_30m=("success_30m", _sum_observed),
            rate_limited_30m=("rate_limited_30m", _sum_observed),
            derankable_error_30m=("derankable_error_30m", _sum_observed),
            capacity_ceiling_rpm=("capacity_ceiling_rpm", "max"),
            recent_peak_rpm=("recent_peak_rpm", "max"),
            p90_latency_ms=("p90_latency_ms", "median"),
        )
        .sort_values(["event_id", "relative_minutes", "provider_name"])
    )
    total = out.groupby(["event_id", "run_ts"])["request_count_30m"].transform(_sum_observed)
    out["request_share_30m"] = out["request_count_30m"] / total.replace(0, np.nan)
    status_total = out["success_30m"] + out["rate_limited_30m"] + out["derankable_error_30m"]
    out["reject_rate_30m"] = (
        out["rate_limited_30m"] + out["derankable_error_30m"]
    ) / status_total.replace(0, np.nan)
    out["n_flow_providers"] = out.groupby(["event_id", "run_ts"])["request_count_30m"].transform(
        lambda x: int(x.notna().sum())
    )
    return out[_empty_intraday().columns]


def event_quality(panel: pd.DataFrame, intraday: pd.DataFrame) -> pd.DataFrame:
    """Make every inclusion decision inspectable at the event level."""
    if panel.empty:
        return pd.DataFrame()
    focal = panel[panel["is_focal"]].copy()
    rows = []
    for event in focal.itertuples(index=False):
        flow = intraday[
            (intraday["event_id"] == event.event_id)
            & (intraday["provider_name"] == event.provider_name)
        ]
        pre_ticks = int((flow["relative_minutes"] < 0).sum())
        post_ticks = int((flow["relative_minutes"] > 0).sum())
        pre_counts = flow.loc[flow["relative_minutes"] < 0, "n_flow_providers"].dropna()
        post_counts = flow.loc[flow["relative_minutes"] > 0, "n_flow_providers"].dropna()
        pre_flow_providers = int(pre_counts.max()) if len(pre_counts) else 0
        post_flow_providers = int(post_counts.max()) if len(post_counts) else 0
        intraday_ok = bool(
            event.eligible_quote
            and pre_ticks >= 1
            and post_ticks >= 1
            and pre_flow_providers >= 2
            and post_flow_providers >= 2
        )
        if not event.focal_snapshot_matched:
            reason = "missing_focal_snapshot"
        elif event.n_providers < 2:
            reason = "fewer_than_two_providers"
        elif event.simultaneous_price_events != 1:
            reason = "simultaneous_model_price_events"
        elif pre_flow_providers < 2 or post_flow_providers < 2:
            reason = "fewer_than_two_observed_flow_providers"
        elif not intraday_ok:
            reason = "insufficient_intraday_pre_or_post_coverage"
        else:
            reason = "eligible"
        rows.append(
            {
                "event_id": event.event_id,
                "event_ts": event.event_ts,
                "model_id": event.model_id,
                "target_provider": event.target_provider,
                "is_cut": event.is_cut,
                "is_raise": event.is_raise,
                "rank_improved": event.rank_improved,
                "newly_best": event.newly_best,
                "provider_wave": event.provider_wave,
                "competitor_event_prior_48h": event.competitor_event_prior_48h,
                "eligible_quote": event.eligible_quote,
                "pre_flow_ticks": pre_ticks,
                "post_flow_ticks": post_ticks,
                "pre_flow_providers": pre_flow_providers,
                "post_flow_providers": post_flow_providers,
                "eligible_intraday": intraday_ok,
                "eligibility_reason": reason,
            }
        )
    return pd.DataFrame(rows)


def threshold_summary(panel: pd.DataFrame) -> dict:
    """R1 diagnostic: density around becoming cheaper than the best rival."""
    focal = panel[(panel["is_focal"]) & (panel["eligible_quote"])].copy()
    x = focal["relative_price_after"].dropna()
    near = x[x.abs() <= 0.01]
    below = int((near < 0).sum())
    above = int((near > 0).sum())
    result = {
        "n_eligible_events": int(len(focal)),
        "n_rank_crossing_cuts": int((focal["is_cut"] & focal["newly_best"]).sum()),
        "near_best_band_log_width": 0.01,
        "n_near_best": int(len(near)),
        "n_just_below_best": below,
        "n_just_above_best": above,
        "power_gate": "needs >=150 rank-crossing events across >=40 markets",
    }
    if below + above >= 40:
        result["below_vs_above_binomial_pvalue"] = float(binomtest(below, below + above).pvalue)
    else:
        result["gated"] = (
            f"near-threshold density test needs >=40 observations (have {below + above})"
        )
    return result


def event_effects(panel: pd.DataFrame, intraday: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Compute transparent per-event rolling-flow changes, not a causal verdict."""
    if panel.empty or intraday.empty:
        return pd.DataFrame()
    if kind == "undercut":
        eligible = panel[
            panel["is_focal"]
            & panel["eligible_quote"]
            & panel["is_cut"]
            & panel["rank_improved"]
            & ~panel["provider_wave"]
            & ~panel["competitor_event_prior_48h"]
        ]
    elif kind == "stale_quote":
        eligible = panel[panel["is_stale_beneficiary"] & panel["eligible_quote"]]
    else:
        raise ValueError(f"unknown event kind: {kind}")
    rows = []
    for event in eligible.itertuples(index=False):
        flow = intraday[
            (intraday["event_id"] == event.event_id)
            & (intraday["provider_name"] == event.provider_name)
        ]
        pre = flow[flow["relative_minutes"].between(-60, -5)]
        post = flow[flow["relative_minutes"].between(5, 60)]
        if pre.empty or post.empty:
            continue
        row = {
            "event_id": event.event_id,
            "event_kind": kind,
            "model_id": event.model_id,
            "provider_name": event.provider_name,
            "pre_request_share_30m": _mean_observed(pre["request_share_30m"]),
            "post_request_share_30m": _mean_observed(post["request_share_30m"]),
            "pre_reject_rate_30m": _mean_observed(pre["reject_rate_30m"]),
            "post_reject_rate_30m": _mean_observed(post["reject_rate_30m"]),
            "pre_capacity_ceiling_rpm": _mean_observed(pre["capacity_ceiling_rpm"]),
            "post_capacity_ceiling_rpm": _mean_observed(post["capacity_ceiling_rpm"]),
            "pre_ticks": int(len(pre)),
            "post_ticks": int(len(post)),
        }
        row["delta_request_share_30m"] = (
            row["post_request_share_30m"] - row["pre_request_share_30m"]
        )
        row["delta_reject_rate_30m"] = row["post_reject_rate_30m"] - row["pre_reject_rate_30m"]
        row["delta_capacity_ceiling_rpm"] = (
            row["post_capacity_ceiling_rpm"] - row["pre_capacity_ceiling_rpm"]
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _effect_summary(effects: pd.DataFrame, kind: str) -> dict:
    d = effects[effects["event_kind"] == kind] if not effects.empty else pd.DataFrame()
    result = {
        "n_events_with_balanced_intraday_window": int(len(d)),
        "power_gate": f"needs >= {MIN_INTRADAY_EVENTS} clean events with pre/post coverage",
        "claim_boundary": (
            "descriptive until stacked event study, pre-trends, and placebo tests pass"
        ),
    }
    if len(d) < MIN_INTRADAY_EVENTS:
        result["gated"] = f"have {len(d)}/{MIN_INTRADAY_EVENTS} events"
        return result
    result.update(
        {
            "mean_delta_request_share_30m": _mean_observed(d["delta_request_share_30m"]),
            "median_delta_request_share_30m": float(d["delta_request_share_30m"].median()),
            "mean_delta_reject_rate_30m": _mean_observed(d["delta_reject_rate_30m"]),
            "mean_delta_capacity_ceiling_rpm": _mean_observed(d["delta_capacity_ceiling_rpm"]),
        }
    )
    return result


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    events = load_price_events()
    if events.empty:
        results = {
            "gated": "no completion-price events available",
            "claim_boundary": "no event means no routing-volume-capture inference",
        }
        save_json(results, out_dir, "h42_summary")
        return results
    snapshots = load_snapshots_for_events()
    model_slugs = event_model_slugs(events)
    panel = build_event_panel(events, snapshots, model_slugs)
    save(panel, out_dir, "h42_routing_event_panel")

    congestion = load_congestion(events, model_slugs)
    intraday = attach_intraday(panel, congestion)
    if not intraday.empty:
        save(intraday, out_dir, "h42_routing_event_intraday")
    quality = event_quality(panel, intraday)
    save(quality, out_dir, "h42_routing_event_quality")

    effects = pd.concat(
        [event_effects(panel, intraday, "undercut"), event_effects(panel, intraday, "stale_quote")],
        ignore_index=True,
    )
    if not effects.empty:
        save(effects, out_dir, "h42_event_effects")
    focal = panel[panel["is_focal"]] if not panel.empty else panel
    results = {
        "claim_boundary": (
            "public data can measure quote/rank changes and rolling flow proxies; "
            "it cannot identify literal front-running, provider profit, or private order flow"
        ),
        "data": {
            "price_events": int(len(events)),
            "event_quote_rows": int(len(panel)),
            "focal_events_with_snapshot": int(focal["focal_snapshot_matched"].sum())
            if not focal.empty
            else 0,
            "intraday_rows": int(len(intraday)),
            "events_eligible_quote": int(quality["eligible_quote"].sum())
            if not quality.empty
            else 0,
            "events_eligible_intraday": int(quality["eligible_intraday"].sum())
            if not quality.empty
            else 0,
        },
        "r1_router_rule_threshold": threshold_summary(panel),
        "r2_undercut_capture": _effect_summary(effects, "undercut"),
        "r3_stale_quote_capture": _effect_summary(effects, "stale_quote"),
        "r4_quote_and_ration": {
            "status": "uses the R2 event cohort once it clears the R2 power gate",
            "required_signature": (
                "post-cut flow gain plus worse rejection/capacity/price-reversal outcome"
            ),
            "current_h10_boundary": "cross-sectional cheap-quote rejection is not significant",
        },
    }
    save_json(results, out_dir, "h42_summary")
    log.info("H42: %s", results["data"])
    return results
