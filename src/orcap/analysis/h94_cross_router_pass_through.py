"""H94 — prospective cross-router posted-price pass-through.

The design is frozen in ``config/h94_cross_router_pass_through.toml``.  It
separates three objects that are easy to conflate: a provider/model price
transition, cross-router propagation of the same new component-price vector,
and a simulated cheapest-provider switch.  None is market-wide realized flow.
"""

from __future__ import annotations

import base64
import hashlib
import html as html_lib
import itertools
import math
import tomllib
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest
from statsmodels.stats.multitest import multipletests

from .common import DEFAULT_OUT, save, save_json
from .h93_cross_router_price_policy import (
    _load_latest_openrouter_models,
    _load_public_quotes,
    prepare_public_quotes,
    simulated_cheapest_routes,
    simulated_route_switches,
)

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config/h94_cross_router_pass_through.toml"
PREREGISTRATION = "docs/h94-cross-router-pass-through-preregistration-2026-07-17.md"
UNOBSERVED_CONTRACT_TERMS = (
    "region,sla,rate_limit,capacity,fallback_policy,billing_semantics,"
    "cache_terms,provider_priority"
)
CONTRACT_FIELDS = [
    "context_length",
    "max_output_tokens",
    "supports_caching",
    "supports_vision",
    "supports_tools",
    "supports_reasoning",
    "supports_structured_output",
    "mode",
    "status",
]


def _configuration() -> tuple[dict[str, Any], str | None]:
    if not CONFIG_PATH.exists():
        return {}, None
    payload = CONFIG_PATH.read_bytes()
    return tomllib.loads(payload.decode("utf-8")), hashlib.sha256(payload).hexdigest()


def _settings() -> dict[str, Any]:
    config, _ = _configuration()
    population = config.get("population", {})
    event = config.get("event", {})
    promotion = config.get("promotion", {})
    inference = config.get("inference", {})
    allocation = config.get("allocation_consequence", {})
    return {
        "eligible_after_utc": population.get("eligible_after_utc"),
        "max_gap_hours": float(event.get("maximum_adjacent_capture_gap_hours", 2.5)),
        "atol": float(event.get("exact_component_price_atol", 1e-12)),
        "rtol": float(event.get("exact_component_price_rtol", 1e-12)),
        "shock_window_minutes": float(event.get("common_shock_window_minutes", 90.0)),
        "tie_window_minutes": float(event.get("simultaneous_tie_window_minutes", 1.0)),
        "material_wedge_percent": float(event.get("material_wedge_percent", 1.0)),
        "allocation_window_minutes": float(allocation.get("window_minutes", 90.0)),
        "placebo_minimum_snapshots": int(inference.get("placebo_minimum_snapshots", 8)),
        "bootstrap_draws": int(inference.get("bootstrap_draws", 5000)),
        "seed": int(inference.get("seed", 20260717)),
        "requirements": {
            "elapsed_days": float(promotion.get("minimum_elapsed_days", 7.0)),
            "minimum_snapshots_per_router": int(
                promotion.get("minimum_snapshots_per_router", 48)
            ),
            "price_transitions": int(promotion.get("minimum_price_transitions", 30)),
            "matched_common_shocks": int(
                promotion.get("minimum_matched_common_shocks", 15)
            ),
            "independent_provider_models": int(
                promotion.get("minimum_independent_provider_models", 10)
            ),
        },
        "allocation_requirement": int(
            allocation.get("minimum_linked_simulated_route_switches", 15)
        ),
    }


def _state(input_price: Any, output_price: Any) -> str:
    return f"{float(input_price):.12g}|{float(output_price):.12g}"


def primary_quote_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Return fail-closed, open-model, multi-router commodity observations."""
    if panel.empty:
        return panel.copy()
    required = {
        "router",
        "run_ts",
        "ts",
        "openrouter_model_id",
        "openrouter_hugging_face_id",
        "model_match_status",
        "provider_key",
        "price_input_usd_per_mtok",
        "price_output_usd_per_mtok",
    }
    if missing := required.difference(panel.columns):
        raise ValueError(f"H94 panel missing columns: {sorted(missing)}")

    settings = _settings()
    source = panel.copy()
    source["ts"] = pd.to_datetime(source["ts"], errors="coerce", utc=True)
    eligible_after = settings.get("eligible_after_utc")
    if eligible_after:
        cutoff = pd.to_datetime(eligible_after, errors="raise", utc=True)
        source = source.loc[source["ts"].ge(cutoff)].copy()
    frame = source.copy()
    for column in ["price_input_usd_per_mtok", "price_output_usd_per_mtok"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.loc[
        frame["model_match_status"].eq("exact_unique_official_suffix")
        & frame["openrouter_hugging_face_id"].notna()
        & frame["openrouter_model_id"].notna()
        & frame["provider_key"].ne("")
        & frame["ts"].notna()
        & frame["price_input_usd_per_mtok"].notna()
        & frame["price_output_usd_per_mtok"].notna()
    ].copy()
    if frame.empty:
        return frame

    frame["price_state"] = [
        _state(left, right)
        for left, right in zip(
            frame["price_input_usd_per_mtok"],
            frame["price_output_usd_per_mtok"],
            strict=True,
        )
    ]
    quote_key = ["router", "ts", "openrouter_model_id", "provider_key"]
    state_counts = frame.groupby(quote_key, dropna=False)["price_state"].transform("nunique")
    frame = frame.loc[state_counts.eq(1)].sort_values("run_ts").drop_duplicates(
        quote_key, keep="last"
    )

    commodity = ["openrouter_model_id", "provider_key"]
    router_counts = frame.groupby(commodity, dropna=False)["router"].transform("nunique")
    frame = frame.loc[router_counts.ge(2)].copy()

    # Adjacency is defined against every successful router capture, not merely
    # the previous appearance of this product. This excludes disappearance and
    # re-entry from the transition estimand.
    snapshots = (
        source.loc[source["ts"].notna(), ["router", "ts"]]
        .drop_duplicates()
        .sort_values(["router", "ts"])
    )
    snapshots["capture_ordinal"] = snapshots.groupby("router").cumcount()
    frame = frame.merge(snapshots, on=["router", "ts"], how="left", validate="many_to_one")
    return frame.sort_values(["router", "openrouter_model_id", "provider_key", "ts"]).reset_index(
        drop=True
    )


def exact_price_transitions(primary: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "event_id",
        "router",
        "openrouter_model_id",
        "provider_key",
        "previous_ts",
        "ts",
        "elapsed_hours",
        "previous_input_price",
        "new_input_price",
        "previous_output_price",
        "new_output_price",
        "previous_price_state",
        "new_price_state",
        "log_scenario_price_change",
    ]
    if primary.empty:
        return pd.DataFrame(columns=columns)
    settings = _settings()
    frame = primary.sort_values(
        ["router", "openrouter_model_id", "provider_key", "ts"]
    ).copy()
    group = ["router", "openrouter_model_id", "provider_key"]
    grouped = frame.groupby(group, dropna=False, sort=False)
    frame["previous_ts"] = grouped["ts"].shift()
    frame["previous_capture_ordinal"] = grouped["capture_ordinal"].shift()
    frame["previous_input_price"] = grouped["price_input_usd_per_mtok"].shift()
    frame["previous_output_price"] = grouped["price_output_usd_per_mtok"].shift()
    frame["previous_price_state"] = grouped["price_state"].shift()
    frame["elapsed_hours"] = (
        frame["ts"] - frame["previous_ts"]
    ).dt.total_seconds() / 3600
    adjacent = (
        frame["capture_ordinal"].sub(frame["previous_capture_ordinal"]).eq(1)
        & frame["elapsed_hours"].gt(0)
        & frame["elapsed_hours"].le(settings["max_gap_hours"])
    )
    input_changed = ~np.isclose(
        frame["price_input_usd_per_mtok"],
        frame["previous_input_price"],
        atol=settings["atol"],
        rtol=settings["rtol"],
        equal_nan=False,
    )
    output_changed = ~np.isclose(
        frame["price_output_usd_per_mtok"],
        frame["previous_output_price"],
        atol=settings["atol"],
        rtol=settings["rtol"],
        equal_nan=False,
    )
    events = frame.loc[adjacent & (input_changed | output_changed)].copy()
    if events.empty:
        return pd.DataFrame(columns=columns)
    old_cost = (
        events["previous_input_price"] * 1000
        + events["previous_output_price"] * 500
    ) / 1_000_000
    new_cost = (
        events["price_input_usd_per_mtok"] * 1000
        + events["price_output_usd_per_mtok"] * 500
    ) / 1_000_000
    events["log_scenario_price_change"] = np.log(new_cost / old_cost)
    events["new_input_price"] = events["price_input_usd_per_mtok"]
    events["new_output_price"] = events["price_output_usd_per_mtok"]
    events["new_price_state"] = events["price_state"]
    events["event_id"] = (
        events["router"].astype(str)
        + "|"
        + events["openrouter_model_id"].astype(str)
        + "|"
        + events["provider_key"].astype(str)
        + "|"
        + events["ts"].astype(str)
    )
    return events.loc[:, columns].reset_index(drop=True)


def _greedy_matches(
    events: pd.DataFrame,
    *,
    key_fields: list[str],
    maximum_minutes: float,
    mismatch_field: str | None = None,
    tie_minutes: float = 1.0,
) -> pd.DataFrame:
    columns = [
        "router_a",
        "router_b",
        "event_id_a",
        "event_id_b",
        "openrouter_model_id_a",
        "openrouter_model_id_b",
        "provider_key_a",
        "provider_key_b",
        "ts_a",
        "ts_b",
        "signed_minutes_b_minus_a",
        "absolute_lag_minutes",
        "observed_leader",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)
    records: list[dict[str, Any]] = []
    for router_a, router_b in itertools.combinations(sorted(events["router"].unique()), 2):
        left_all = events.loc[events["router"].eq(router_a)]
        right_all = events.loc[events["router"].eq(router_b)]
        if left_all.empty or right_all.empty:
            continue
        for keys, left in left_all.groupby(key_fields, dropna=False, sort=False):
            key_tuple = keys if isinstance(keys, tuple) else (keys,)
            mask = pd.Series(True, index=right_all.index)
            for field, value in zip(key_fields, key_tuple, strict=True):
                mask &= right_all[field].eq(value)
            right = right_all.loc[mask]
            if right.empty:
                continue
            candidates: list[tuple[float, Any, Any]] = []
            for a in left.itertuples(index=False):
                for b in right.itertuples(index=False):
                    if mismatch_field and getattr(a, mismatch_field) == getattr(b, mismatch_field):
                        continue
                    lag = abs((b.ts - a.ts).total_seconds()) / 60
                    if lag <= maximum_minutes:
                        candidates.append((lag, a, b))
            used_a: set[str] = set()
            used_b: set[str] = set()
            for lag, a, b in sorted(candidates, key=lambda item: item[0]):
                if a.event_id in used_a or b.event_id in used_b:
                    continue
                used_a.add(a.event_id)
                used_b.add(b.event_id)
                signed = (b.ts - a.ts).total_seconds() / 60
                leader = (
                    "simultaneous"
                    if abs(signed) <= tie_minutes
                    else router_a
                    if signed > 0
                    else router_b
                )
                records.append(
                    {
                        "router_a": router_a,
                        "router_b": router_b,
                        "event_id_a": a.event_id,
                        "event_id_b": b.event_id,
                        "openrouter_model_id_a": a.openrouter_model_id,
                        "openrouter_model_id_b": b.openrouter_model_id,
                        "provider_key_a": a.provider_key,
                        "provider_key_b": b.provider_key,
                        "ts_a": a.ts,
                        "ts_b": b.ts,
                        "signed_minutes_b_minus_a": float(signed),
                        "absolute_lag_minutes": float(lag),
                        "observed_leader": leader,
                    }
                )
    return pd.DataFrame.from_records(records, columns=columns)


def common_shock_matches(events: pd.DataFrame) -> pd.DataFrame:
    settings = _settings()
    return _greedy_matches(
        events,
        key_fields=["openrouter_model_id", "provider_key", "new_price_state"],
        maximum_minutes=settings["shock_window_minutes"],
        tie_minutes=settings["tie_window_minutes"],
    )


def negative_control_matches(events: pd.DataFrame) -> pd.DataFrame:
    settings = _settings()
    provider_decoy = _greedy_matches(
        events,
        key_fields=["openrouter_model_id", "new_price_state"],
        maximum_minutes=settings["shock_window_minutes"],
        mismatch_field="provider_key",
        tie_minutes=settings["tie_window_minutes"],
    )
    provider_decoy["control_family"] = "same_model_different_provider"
    model_decoy = _greedy_matches(
        events,
        key_fields=["provider_key", "new_price_state"],
        maximum_minutes=settings["shock_window_minutes"],
        mismatch_field="openrouter_model_id",
        tie_minutes=settings["tie_window_minutes"],
    )
    model_decoy["control_family"] = "same_provider_different_model"
    return pd.concat([provider_decoy, model_decoy], ignore_index=True)


def _contract_agreement(left: Any, right: Any) -> tuple[int, int, str]:
    compared = 0
    conflicts: list[str] = []
    for field in CONTRACT_FIELDS:
        a, b = getattr(left, field, None), getattr(right, field, None)
        if pd.isna(a) or pd.isna(b):
            continue
        compared += 1
        if isinstance(a, (float, int, np.number)) and isinstance(
            b, (float, int, np.number)
        ):
            equal = bool(np.isclose(float(a), float(b), rtol=1e-12, atol=1e-12))
        else:
            equal = str(a).strip().lower() == str(b).strip().lower()
        if not equal:
            conflicts.append(field)
    return compared, len(conflicts), ",".join(conflicts)


def synchronous_pair_panel(primary: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "ts",
        "openrouter_model_id",
        "provider_key",
        "router_a",
        "router_b",
        "scenario_cost_usd_a",
        "scenario_cost_usd_b",
        "absolute_percent_wedge",
        "exact_component_price_match",
        "observed_contract_terms_compared",
        "observed_contract_term_conflicts",
        "conflicting_observed_terms",
        "observed_terms_match",
        "contract_equivalence_identified",
        "unobserved_contract_terms",
    ]
    if primary.empty:
        return pd.DataFrame(columns=columns)
    records: list[dict[str, Any]] = []
    keys = ["ts", "openrouter_model_id", "provider_key"]
    for (ts, model, provider), group in primary.groupby(keys, dropna=False, sort=True):
        for left, right in itertools.combinations(
            list(group.sort_values("router").itertuples(index=False)), 2
        ):
            if left.router == right.router:
                continue
            left_cost = (
                left.price_input_usd_per_mtok * 1000
                + left.price_output_usd_per_mtok * 500
            ) / 1_000_000
            right_cost = (
                right.price_input_usd_per_mtok * 1000
                + right.price_output_usd_per_mtok * 500
            ) / 1_000_000
            compared, conflicts, conflict_fields = _contract_agreement(left, right)
            exact = left.price_state == right.price_state
            records.append(
                {
                    "ts": ts,
                    "openrouter_model_id": model,
                    "provider_key": provider,
                    "router_a": left.router,
                    "router_b": right.router,
                    "scenario_cost_usd_a": left_cost,
                    "scenario_cost_usd_b": right_cost,
                    "absolute_percent_wedge": 100
                    * (math.exp(abs(math.log(left_cost / right_cost))) - 1),
                    "exact_component_price_match": exact,
                    "observed_contract_terms_compared": compared,
                    "observed_contract_term_conflicts": conflicts,
                    "conflicting_observed_terms": conflict_fields,
                    "observed_terms_match": bool(compared > 0 and conflicts == 0),
                    "contract_equivalence_identified": False,
                    "unobserved_contract_terms": UNOBSERVED_CONTRACT_TERMS,
                }
            )
    return pd.DataFrame.from_records(records, columns=columns)


def material_wedge_spells(pair_panel: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "spell_id",
        "openrouter_model_id",
        "provider_key",
        "router_a",
        "router_b",
        "spell_start_ts",
        "last_divergent_ts",
        "first_converged_ts",
        "duration_lower_hours",
        "duration_upper_hours",
        "left_censored",
        "right_censored",
        "maximum_wedge_percent",
    ]
    if pair_panel.empty:
        return pd.DataFrame(columns=columns)
    settings = _settings()
    records: list[dict[str, Any]] = []
    keys = ["openrouter_model_id", "provider_key", "router_a", "router_b"]
    for key, group in pair_panel.groupby(keys, dropna=False, sort=True):
        group = group.sort_values("ts").reset_index(drop=True)
        active: dict[str, Any] | None = None
        previous_ts: pd.Timestamp | None = None
        for index, row in group.iterrows():
            contiguous = (
                previous_ts is not None
                and 0 < (row["ts"] - previous_ts).total_seconds() / 3600
                <= settings["max_gap_hours"]
            )
            material = row["absolute_percent_wedge"] > settings["material_wedge_percent"]
            if active is not None and (not contiguous or not material):
                resolved = bool(contiguous and not material)
                start = active["start"]
                last = active["last"]
                records.append(
                    {
                        "spell_id": f"{'|'.join(map(str, key))}|{start}",
                        "openrouter_model_id": key[0],
                        "provider_key": key[1],
                        "router_a": key[2],
                        "router_b": key[3],
                        "spell_start_ts": start,
                        "last_divergent_ts": last,
                        "first_converged_ts": row["ts"] if resolved else pd.NaT,
                        "duration_lower_hours": (last - start).total_seconds() / 3600,
                        "duration_upper_hours": (
                            (row["ts"] - start).total_seconds() / 3600
                            if resolved
                            else np.nan
                        ),
                        "left_censored": active["left_censored"],
                        "right_censored": not resolved,
                        "maximum_wedge_percent": active["maximum"],
                    }
                )
                active = None
            if material:
                if active is None:
                    active = {
                        "start": row["ts"],
                        "last": row["ts"],
                        "maximum": float(row["absolute_percent_wedge"]),
                        "left_censored": bool(index == 0),
                    }
                else:
                    active["last"] = row["ts"]
                    active["maximum"] = max(
                        active["maximum"], float(row["absolute_percent_wedge"])
                    )
            previous_ts = row["ts"]
        if active is not None:
            start, last = active["start"], active["last"]
            records.append(
                {
                    "spell_id": f"{'|'.join(map(str, key))}|{start}",
                    "openrouter_model_id": key[0],
                    "provider_key": key[1],
                    "router_a": key[2],
                    "router_b": key[3],
                    "spell_start_ts": start,
                    "last_divergent_ts": last,
                    "first_converged_ts": pd.NaT,
                    "duration_lower_hours": (last - start).total_seconds() / 3600,
                    "duration_upper_hours": np.nan,
                    "left_censored": active["left_censored"],
                    "right_censored": True,
                    "maximum_wedge_percent": active["maximum"],
                }
            )
    return pd.DataFrame.from_records(records, columns=columns)


def link_simulated_switches(events: pd.DataFrame, switches: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "event_id",
        "router",
        "openrouter_model_id",
        "provider_key",
        "event_ts",
        "switch_ts",
        "minutes_to_switch",
        "previous_winner_provider_set",
        "winner_provider_set",
    ]
    if events.empty or switches.empty:
        return pd.DataFrame(columns=columns)
    window = _settings()["allocation_window_minutes"]
    records: list[dict[str, Any]] = []
    for event in events.itertuples(index=False):
        candidates = switches.loc[
            switches["router"].eq(event.router)
            & switches["openrouter_model_id"].eq(event.openrouter_model_id)
            & switches["ts"].ge(event.ts)
        ].copy()
        if candidates.empty:
            continue
        candidates["minutes"] = (candidates["ts"] - event.ts).dt.total_seconds() / 60
        candidates = candidates.loc[candidates["minutes"].le(window)].sort_values("minutes")
        if candidates.empty:
            continue
        switch = candidates.iloc[0]
        records.append(
            {
                "event_id": event.event_id,
                "router": event.router,
                "openrouter_model_id": event.openrouter_model_id,
                "provider_key": event.provider_key,
                "event_ts": event.ts,
                "switch_ts": switch["ts"],
                "minutes_to_switch": float(switch["minutes"]),
                "previous_winner_provider_set": switch["previous_winner_provider_set"],
                "winner_provider_set": switch["winner_provider_set"],
            }
        )
    return pd.DataFrame.from_records(records, columns=columns)


def lead_lag_inference(matches: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "router_a",
        "router_b",
        "matched_shocks",
        "simultaneous_shocks",
        "router_a_leads",
        "router_b_leads",
        "median_absolute_lag_minutes",
        "two_sided_equal_leader_p",
        "holm_equal_leader_p",
    ]
    if matches.empty:
        return pd.DataFrame(columns=columns)
    records = []
    for (a, b), group in matches.groupby(["router_a", "router_b"], sort=True):
        a_leads = int(group["observed_leader"].eq(a).sum())
        b_leads = int(group["observed_leader"].eq(b).sum())
        n = a_leads + b_leads
        p = float(binomtest(a_leads, n, 0.5).pvalue) if n else np.nan
        records.append(
            {
                "router_a": a,
                "router_b": b,
                "matched_shocks": len(group),
                "simultaneous_shocks": int(group["observed_leader"].eq("simultaneous").sum()),
                "router_a_leads": a_leads,
                "router_b_leads": b_leads,
                "median_absolute_lag_minutes": float(group["absolute_lag_minutes"].median()),
                "two_sided_equal_leader_p": p,
            }
        )
    out = pd.DataFrame.from_records(records)
    out["holm_equal_leader_p"] = np.nan
    mask = out["two_sided_equal_leader_p"].notna()
    if mask.any():
        out.loc[mask, "holm_equal_leader_p"] = multipletests(
            out.loc[mask, "two_sided_equal_leader_p"], method="holm"
        )[1]
    return out.loc[:, columns]


def transition_coverage_interval(
    events: pd.DataFrame,
    matches: pd.DataFrame,
    *,
    draws: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    if events.empty:
        return {
            "eligible_events": 0,
            "covered_events": 0,
            "coverage_share": None,
            "provider_model_cluster_bootstrap_ci95": None,
        }
    covered_ids = set(matches.get("event_id_a", [])) | set(matches.get("event_id_b", []))
    frame = events[["event_id", "openrouter_model_id", "provider_key"]].copy()
    frame["covered"] = frame["event_id"].isin(covered_ids).astype(float)
    frame["cluster"] = frame["openrouter_model_id"] + "|" + frame["provider_key"]
    cluster_values = [group["covered"].to_numpy() for _, group in frame.groupby("cluster")]
    settings = _settings()
    draws = settings["bootstrap_draws"] if draws is None else int(draws)
    rng = np.random.default_rng(settings["seed"] if seed is None else seed)
    bootstrap: list[float] = []
    if cluster_values and draws > 0:
        for indices in rng.integers(0, len(cluster_values), size=(draws, len(cluster_values))):
            values = np.concatenate([cluster_values[index] for index in indices])
            bootstrap.append(float(values.mean()))
    return {
        "eligible_events": len(frame),
        "covered_events": int(frame["covered"].sum()),
        "coverage_share": float(frame["covered"].mean()),
        "provider_model_clusters": len(cluster_values),
        "provider_model_cluster_bootstrap_ci95": (
            [float(value) for value in np.percentile(bootstrap, [2.5, 97.5])]
            if bootstrap
            else None
        ),
        "bootstrap_draws": draws,
    }


def circular_shift_placebo(
    events: pd.DataFrame, primary: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    placebo_columns = [
        "router_a",
        "router_b",
        "shift",
        "snapshot_count",
        "observed_matches",
        "placebo_matches",
    ]
    inference_columns = [
        "router_a",
        "router_b",
        "snapshot_count",
        "observed_matches",
        "maximum_placebo_matches",
        "circular_shift_p_greater_equal",
        "holm_circular_shift_p",
    ]
    if events.empty or primary.empty:
        return pd.DataFrame(columns=placebo_columns), pd.DataFrame(columns=inference_columns)
    settings = _settings()
    records: list[dict[str, Any]] = []
    for router_a, router_b in itertools.combinations(sorted(events["router"].unique()), 2):
        a = events.loc[events["router"].eq(router_a)].copy()
        b = events.loc[events["router"].eq(router_b)].copy()
        if a.empty or b.empty:
            continue
        grids = []
        for router in [router_a, router_b]:
            grids.append(set(primary.loc[primary["router"].eq(router), "ts"].dropna()))
        grid = sorted(grids[0].intersection(grids[1]))
        if len(grid) < settings["placebo_minimum_snapshots"]:
            continue
        grid_index = {value: index for index, value in enumerate(grid)}
        b = b.loc[b["ts"].isin(grid_index)].copy()
        a = a.loc[a["ts"].isin(grid_index)].copy()
        if a.empty or b.empty:
            continue
        pair_events = pd.concat([a, b], ignore_index=True)
        observed = len(common_shock_matches(pair_events))
        for shift in range(1, len(grid)):
            shifted = b.copy()
            shifted["ts"] = shifted["ts"].map(
                lambda value, grid=grid, grid_index=grid_index, shift=shift: grid[
                    (grid_index[value] + shift) % len(grid)
                ]
            )
            shifted["event_id"] = shifted["event_id"] + f"|shift={shift}"
            placebo_count = len(common_shock_matches(pd.concat([a, shifted], ignore_index=True)))
            records.append(
                {
                    "router_a": router_a,
                    "router_b": router_b,
                    "shift": shift,
                    "snapshot_count": len(grid),
                    "observed_matches": observed,
                    "placebo_matches": placebo_count,
                }
            )
    placebo = pd.DataFrame.from_records(records, columns=placebo_columns)
    if placebo.empty:
        return placebo, pd.DataFrame(columns=inference_columns)
    inference_records = []
    for (a, b), group in placebo.groupby(["router_a", "router_b"], sort=True):
        observed = int(group["observed_matches"].iloc[0])
        p = (1 + int(group["placebo_matches"].ge(observed).sum())) / (1 + len(group))
        inference_records.append(
            {
                "router_a": a,
                "router_b": b,
                "snapshot_count": int(group["snapshot_count"].iloc[0]),
                "observed_matches": observed,
                "maximum_placebo_matches": int(group["placebo_matches"].max()),
                "circular_shift_p_greater_equal": float(p),
            }
        )
    inference = pd.DataFrame.from_records(inference_records)
    inference["holm_circular_shift_p"] = multipletests(
        inference["circular_shift_p_greater_equal"], method="holm"
    )[1]
    return placebo, inference.loc[:, inference_columns]


def evidence_summary(
    panel: pd.DataFrame, *, bootstrap_draws: int | None = None
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    settings = _settings()
    primary = primary_quote_panel(panel)
    events = exact_price_transitions(primary)
    matches = common_shock_matches(events)
    controls = negative_control_matches(events)
    pair_panel = synchronous_pair_panel(primary)
    spells = material_wedge_spells(pair_panel)
    routes = simulated_cheapest_routes(panel)
    switches = simulated_route_switches(routes)
    linked = link_simulated_switches(events, switches)
    lead_lag = lead_lag_inference(matches)
    placebo, placebo_inference = circular_shift_placebo(events, primary)
    coverage = transition_coverage_interval(events, matches, draws=bootstrap_draws)

    timestamps = panel["ts"].dropna() if "ts" in panel else pd.Series(dtype="datetime64[ns, UTC]")
    elapsed = (
        float((timestamps.max() - timestamps.min()).total_seconds() / 86400)
        if len(timestamps) >= 2
        else 0.0
    )
    snapshots = (
        panel.groupby("router")["run_ts"].nunique()
        if not panel.empty
        else pd.Series(dtype=int)
    )
    independent = (
        events[["openrouter_model_id", "provider_key"]].drop_duplicates().shape[0]
        if not events.empty
        else 0
    )
    observed = {
        "elapsed_days": elapsed,
        "minimum_snapshots_per_router": int(snapshots.min()) if len(snapshots) else 0,
        "price_transitions": len(events),
        "matched_common_shocks": len(matches),
        "independent_provider_models": independent,
    }
    requirements = settings["requirements"]
    gates = {name: observed[name] >= value for name, value in requirements.items()}
    linked_switches = int(linked["switch_ts"].nunique()) if not linked.empty else 0
    config, config_sha = _configuration()
    summary = {
        "hypothesis": "H94 prospective cross-router posted-price pass-through",
        "evidence_status": (
            "primary_dynamic_gate_open" if all(gates.values()) else "prospective_gate_closed"
        ),
        "preregistration": PREREGISTRATION,
        "configuration_sha256": config_sha,
        "configuration": config,
        "observed": observed,
        "requirements": requirements,
        "gates": gates,
        "transition_coverage": coverage,
        "material_wedge_spells": {
            "episodes": len(spells),
            "resolved": int((~spells["right_censored"]).sum()) if not spells.empty else 0,
            "right_censored": int(spells["right_censored"].sum()) if not spells.empty else 0,
        },
        "allocation_consequence": {
            "linked_simulated_route_switches": linked_switches,
            "requirement": settings["allocation_requirement"],
            "gate": linked_switches >= settings["allocation_requirement"],
            "claim": "simulated cheapest-provider response only, not realized routing",
        },
        "negative_controls": (
            controls["control_family"].value_counts().sort_index().to_dict()
            if not controls.empty
            else {}
        ),
        "contract_audit": {
            "simultaneous_pairs": len(pair_panel),
            "pairs_with_observed_term_conflicts": int(
                pair_panel["observed_contract_term_conflicts"].gt(0).sum()
            )
            if not pair_panel.empty
            else 0,
            "contract_equivalence_identified": False,
            "unobserved_terms": UNOBSERVED_CONTRACT_TERMS.split(","),
        },
        "claim_boundary": (
            "H94 measures synchronization of public posted menus and simulated cheapest-provider "
            "consequences. It does not identify identical contracts, executable firmness, private "
            "eligibility, market-wide flow, provider profit, user welfare, or literal "
            "front-running."
        ),
    }
    return summary, {
        "primary_quotes": primary,
        "price_transitions": events,
        "common_shock_matches": matches,
        "negative_control_matches": controls,
        "synchronous_pairs": pair_panel,
        "material_wedge_spells": spells,
        "simulated_switch_links": linked,
        "lead_lag_inference": lead_lag,
        "circular_shift_placebo": placebo,
        "circular_shift_inference": placebo_inference,
    }


def render_panel(
    summary: dict[str, Any], frames: dict[str, pd.DataFrame], out_dir: Path
) -> tuple[Path, Path]:
    transitions = frames["price_transitions"]
    matches = frames["common_shock_matches"]
    pairs = frames["synchronous_pairs"]
    spells = frames["material_wedge_spells"]
    observed, requirements = summary["observed"], summary["requirements"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)

    ax = axes[0, 0]
    if transitions.empty:
        ax.text(0.5, 0.5, "No adjacent price transition yet", ha="center", va="center")
    else:
        counts = transitions.groupby("router").size().sort_index()
        ax.bar(counts.index, counts.values, color="#2563eb")
        ax.set_ylabel("adjacent component-price transitions")
    ax.set_title("A. Price transitions", loc="left", fontweight="bold")

    ax = axes[0, 1]
    if matches.empty:
        ax.text(0.5, 0.5, "No matched common shock yet", ha="center", va="center")
    else:
        for pair, group in matches.groupby(["router_a", "router_b"]):
            label = f"{pair[0]}–{pair[1]}"
            ax.scatter(
                np.arange(len(group)),
                group["signed_minutes_b_minus_a"],
                label=label,
                alpha=0.8,
            )
        ax.axhline(0, color="#64748b", linewidth=1)
        ax.set_ylabel("minutes: router B minus router A")
        ax.legend(frameon=False)
    ax.set_title("B. Matched-shock lead–lag", loc="left", fontweight="bold")

    ax = axes[1, 0]
    if pairs.empty:
        ax.text(0.5, 0.5, "No simultaneous pair panel", ha="center", va="center")
    else:
        wedge = pairs.groupby("ts")["absolute_percent_wedge"].max().sort_index()
        ax.plot(wedge.index, wedge.values, color="#dc2626", marker="o", markersize=3)
        ax.axhline(_settings()["material_wedge_percent"], color="#64748b", linestyle="--")
        ax.set_yscale("symlog", linthresh=0.1)
        ax.set_ylabel("maximum same-commodity wedge (%)")
        ax.tick_params(axis="x", rotation=25)
        ax.text(
            0.02,
            0.95,
            f"material spells: {len(spells)}",
            transform=ax.transAxes,
            va="top",
        )
    ax.set_title("C. Temporary posted-price wedges", loc="left", fontweight="bold")

    ax = axes[1, 1]
    keys = list(requirements)
    progress = [min(1.0, observed[key] / requirements[key]) for key in keys]
    labels = ["days", "snapshots", "transitions", "matched shocks", "commodities"]
    y = np.arange(len(keys))
    ax.barh(y, progress, color=["#16a34a" if value >= 1 else "#cbd5e1" for value in progress])
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 1)
    ax.invert_yaxis()
    for index, key in enumerate(keys):
        ax.text(
            min(0.96, progress[index] + 0.02),
            index,
            f"{observed[key]:g}/{requirements[key]:g}",
            va="center",
            fontsize=8,
        )
    ax.set_title("D. Prospective promotion gate", loc="left", fontweight="bold")
    fig.suptitle("H94 cross-router posted-price pass-through", fontsize=14, fontweight="bold")
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / "h94_cross_router_pass_through_panel.png"
    pdf = out_dir / "h94_cross_router_pass_through_panel.pdf"
    fig.savefig(png, dpi=180)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def render_html(
    summary: dict[str, Any], frames: dict[str, pd.DataFrame], png: Path, out_dir: Path
) -> Path:
    observed = summary.get("observed", {})
    coverage = summary.get("transition_coverage", {})
    cards = [
        ("Elapsed days", f"{observed.get('elapsed_days', 0):.2f}"),
        ("Price transitions", str(observed.get("price_transitions", 0))),
        ("Matched shocks", str(observed.get("matched_common_shocks", 0))),
        ("Independent commodities", str(observed.get("independent_provider_models", 0))),
        (
            "Transition coverage",
            "--"
            if coverage.get("coverage_share") is None
            else f"{100 * coverage['coverage_share']:.1f}%",
        ),
        (
            "Linked simulated switches",
            str(
                summary.get("allocation_consequence", {}).get(
                    "linked_simulated_route_switches", 0
                )
            ),
        ),
    ]
    card_html = "".join(
        f'<div class="card"><div class="label">{html_lib.escape(label)}</div>'
        f'<div class="metric">{html_lib.escape(value)}</div></div>'
        for label, value in cards
    )
    image = base64.b64encode(png.read_bytes()).decode("ascii")
    document = f"""<!doctype html><html><head><meta charset="utf-8">
<title>H94 cross-router pass-through</title><style>
body{{font-family:Inter,system-ui,sans-serif;margin:0;background:#f8fafc;color:#0f172a}}
main{{max-width:1180px;margin:auto;padding:28px}} .cards{{display:grid;grid-template-columns:
repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:20px 0}} .card,section{{background:white;
border:1px solid #e2e8f0;border-radius:10px;padding:14px}} .label{{font-size:12px;color:#64748b}}
.metric{{font-size:24px;font-weight:700;margin-top:5px}} img{{width:100%;height:auto}}
.boundary{{border-left:4px solid #f59e0b}} code{{font-size:12px}}
</style></head><body><main><h1>H94: cross-router posted-price pass-through</h1>
<p>{html_lib.escape(summary.get('evidence_status', ''))}</p><div class="cards">{card_html}</div>
<section><img alt="H94 experiment panel" src="data:image/png;base64,{image}"></section>
<section><h2>Frozen design</h2><p><code>
{html_lib.escape(summary.get('configuration_sha256') or '--')}</code></p>
<p>{html_lib.escape(summary.get('preregistration', ''))}</p></section>
<section class="boundary"><h2>Claim boundary</h2><p>
{html_lib.escape(summary.get('claim_boundary', ''))}</p></section>
</main></body></html>"""
    path = out_dir / "h94_cross_router_pass_through_panel.html"
    path.write_text(document)
    return path


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    try:
        quotes = _load_public_quotes()
        models = _load_latest_openrouter_models()
        panel = prepare_public_quotes(quotes, models)
        summary, frames = evidence_summary(panel)
    except Exception as exc:
        config, config_sha = _configuration()
        summary = {
            "hypothesis": "H94 prospective cross-router posted-price pass-through",
            "evidence_status": "public_router_catalog_panel_unavailable",
            "error": str(exc),
            "preregistration": PREREGISTRATION,
            "configuration_sha256": config_sha,
            "configuration": config,
            "claim_boundary": "No H94 empirical claim is available without the public panel.",
        }
        frames = {}
    for name, frame in frames.items():
        save(frame, out_dir, f"h94_{name}")
    if frames:
        png, _ = render_panel(summary, frames, out_dir)
        render_html(summary, frames, png, out_dir)
    save_json(summary, out_dir, "h94_summary")
    return summary
