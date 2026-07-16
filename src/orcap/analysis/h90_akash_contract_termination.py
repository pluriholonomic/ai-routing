"""H90 — transparent Akash contract choice and termination comparator.

The pre-cutoff tape is explicitly exploratory. The prospective cohort releases
no close-reason aggregate before the fixed calendar cutoff in the frozen H90
preregistration.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportion_confint

from . import data
from .common import DEFAULT_OUT, save, save_json

STUDY_ID = "akash-contract-termination-v1"
PREREG_CUTOFF = pd.Timestamp("2026-07-16T01:15:00Z")
RELEASE_CUTOFF = pd.Timestamp("2026-08-15T01:15:00Z")
FOLLOWUP_BLOCKS = 300
MIN_RELEASE_LEASES = 500
MIN_RELEASE_PROVIDERS = 20
MIN_EVENT_COUNT_PER_ARM = 10
PERMUTATIONS = 5_000
BOOTSTRAPS = 2_000


def _load(name: str) -> pd.DataFrame:
    try:
        glob = data.table_glob(name)
        return data.q(
            f"select * from read_parquet('{glob}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def _number(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[name], errors="coerce")


def _time(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    return pd.to_datetime(frame[name], utc=True, errors="coerce")


def _record_field(value: Any, *path: str) -> Any:
    if not isinstance(value, str):
        return None
    try:
        current: Any = json.loads(value)
    except json.JSONDecodeError:
        return None
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def snapshot_map(choice_bids: pd.DataFrame) -> pd.DataFrame:
    """Recover same-run Akash observation heights for legacy lease rows."""
    required = {"run_ts", "snapshot_height"}
    if choice_bids.empty or not required.issubset(choice_bids.columns):
        return pd.DataFrame(columns=["run_ts", "fallback_snapshot_height"])
    frame = choice_bids.loc[:, ["run_ts", "snapshot_height"]].copy()
    frame["fallback_snapshot_height"] = _number(frame, "snapshot_height")
    frame = frame.dropna(subset=["run_ts", "fallback_snapshot_height"])
    return (
        frame.groupby("run_ts", as_index=False)["fallback_snapshot_height"]
        .max()
        .sort_values("run_ts")
    )


def successful_snapshot_panel(source_runs: pd.DataFrame) -> pd.DataFrame:
    """Return source-ledger-verified successful Akash choice-set captures.

    Confirmatory inception is defined against successful captures, not merely
    against lease rows that happened to be returned.  The immutable source-run
    ledger is therefore the authority for both the ordinal and the preceding
    snapshot height.  Legacy rows without this ledger may remain exploratory,
    but can never enter the prospective cohort.
    """
    columns = [
        "run_ts",
        "verified_snapshot_at",
        "verified_snapshot_height",
        "post_cutoff_capture_ordinal",
        "preceding_successful_snapshot_height",
        "snapshot_source_verified",
    ]
    required = {"run_ts", "source", "status", "watermark"}
    if source_runs.empty or not required.issubset(source_runs.columns):
        return pd.DataFrame(columns=columns)
    frame = source_runs.loc[
        source_runs["source"].eq("akash_choice_sets")
        & source_runs["status"].eq("success")
    ].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["verified_snapshot_at"] = _time(frame, "run_ts")
    frame["verified_snapshot_height"] = _number(frame, "watermark")
    if "detail_json" in frame:
        missing = frame["verified_snapshot_height"].isna()
        if missing.any():
            frame.loc[missing, "verified_snapshot_height"] = frame.loc[
                missing, "detail_json"
            ].map(lambda value: _record_field(value, "snapshot_height"))
    frame["verified_snapshot_height"] = _number(frame, "verified_snapshot_height")
    frame = (
        frame.dropna(
            subset=["run_ts", "verified_snapshot_at", "verified_snapshot_height"]
        )
        .sort_values(["verified_snapshot_at", "run_ts"])
        .drop_duplicates("run_ts", keep="last")
    )
    frame = frame.loc[frame["verified_snapshot_at"].ge(PREREG_CUTOFF)].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    frame["post_cutoff_capture_ordinal"] = np.arange(1, len(frame) + 1)
    frame["preceding_successful_snapshot_height"] = frame[
        "verified_snapshot_height"
    ].shift(1)
    frame["snapshot_source_verified"] = True
    return frame.loc[:, columns].reset_index(drop=True)


def lifecycle_panel(
    leases: pd.DataFrame,
    close_events: pd.DataFrame,
    choice_bids: pd.DataFrame,
    source_runs: pd.DataFrame | None = None,
) -> pd.DataFrame:
    required = {"execution_id", "run_ts", "lease_state", "record_json"}
    if leases.empty or not required.issubset(leases.columns):
        return pd.DataFrame()
    sources = (
        leases["source"]
        if "source" in leases
        else pd.Series("akash", index=leases.index, dtype="object")
    )
    frame = leases.loc[sources.eq("akash")].copy()
    frame["observed_at"] = _time(frame, "run_ts")
    frame["snapshot_height_numeric"] = _number(frame, "snapshot_height")
    snapshots = snapshot_map(choice_bids)
    if not snapshots.empty:
        frame = frame.merge(snapshots, on="run_ts", how="left", validate="many_to_one")
        frame["snapshot_height_numeric"] = frame["snapshot_height_numeric"].fillna(
            frame["fallback_snapshot_height"]
        )
    frame["created_at_block_numeric"] = _number(frame, "created_at_block")
    frame["closed_on_block_numeric"] = _number(frame, "closed_on_block")
    missing_created = frame["created_at_block_numeric"].isna()
    missing_closed = frame["closed_on_block_numeric"].isna()
    if missing_created.any():
        frame.loc[missing_created, "created_at_block_numeric"] = frame.loc[
            missing_created, "record_json"
        ].map(lambda value: _record_field(value, "lease", "created_at"))
    if missing_closed.any():
        frame.loc[missing_closed, "closed_on_block_numeric"] = frame.loc[
            missing_closed, "record_json"
        ].map(lambda value: _record_field(value, "lease", "closed_on"))
    frame["created_at_block_numeric"] = _number(frame, "created_at_block_numeric")
    frame["closed_on_block_numeric"] = _number(frame, "closed_on_block_numeric")
    frame = frame.dropna(subset=["execution_id", "observed_at", "created_at_block_numeric"])
    if frame.empty:
        return pd.DataFrame()

    frame = frame.sort_values(["execution_id", "observed_at", "run_ts"])
    last = frame.drop_duplicates("execution_id", keep="last").set_index("execution_id")
    grouped = frame.groupby("execution_id", sort=True)
    panel = pd.DataFrame(
        {
            "first_seen_run_ts": grouped["run_ts"].first(),
            "last_seen_run_ts": grouped["run_ts"].last(),
            "first_seen_at": grouped["observed_at"].first(),
            "last_seen_at": grouped["observed_at"].last(),
            "first_snapshot_height": grouped["snapshot_height_numeric"].first(),
            "last_snapshot_height": grouped["snapshot_height_numeric"].last(),
            "created_at_block": grouped["created_at_block_numeric"].first(),
            "closed_on_block": grouped["closed_on_block_numeric"].max(),
            "lease_revisions": grouped.size(),
        }
    ).reset_index()
    for column in ("participant_id", "rate_denom", "rate_amount_native", "settled_amount_native"):
        panel[column] = panel["execution_id"].map(last[column]) if column in last else None
    panel["latest_lease_state"] = panel["execution_id"].map(last["lease_state"])
    panel["source_day"] = pd.to_datetime(panel["first_seen_at"], utc=True).dt.strftime(
        "%Y-%m-%d"
    )

    verified = successful_snapshot_panel(
        source_runs if source_runs is not None else pd.DataFrame()
    )
    if not verified.empty:
        panel = panel.merge(
            verified,
            left_on="first_seen_run_ts",
            right_on="run_ts",
            how="left",
            validate="many_to_one",
        ).drop(columns="run_ts")
    else:
        panel["verified_snapshot_at"] = pd.NaT
        panel["verified_snapshot_height"] = np.nan
        panel["post_cutoff_capture_ordinal"] = np.nan
        panel["preceding_successful_snapshot_height"] = np.nan
        panel["snapshot_source_verified"] = False
    panel["snapshot_source_verified"] = panel["snapshot_source_verified"].eq(True)
    panel["first_snapshot_height"] = panel["first_snapshot_height"].fillna(
        panel["verified_snapshot_height"]
    )
    panel["snapshot_height_matches_ledger"] = (
        panel["snapshot_source_verified"]
        & panel["first_snapshot_height"].eq(panel["verified_snapshot_height"])
    )
    panel["post_cutoff_first_seen"] = panel["first_seen_at"].ge(PREREG_CUTOFF)
    panel["prospective_inception_eligible"] = (
        panel["post_cutoff_first_seen"]
        & panel["snapshot_source_verified"]
        & panel["post_cutoff_capture_ordinal"].ge(2)
        & panel["snapshot_height_matches_ledger"]
        & panel["created_at_block"].gt(
            panel["preceding_successful_snapshot_height"]
        )
        & panel["created_at_block"].le(panel["first_snapshot_height"])
    )

    def exclusion_reason(row: pd.Series) -> str:
        if not row["post_cutoff_first_seen"]:
            return "pre_preregistration_exploratory"
        if row["first_seen_at"] > RELEASE_CUTOFF:
            return "after_fixed_calendar_cutoff"
        if not row["snapshot_source_verified"]:
            return "missing_successful_capture_ledger"
        if row["post_cutoff_capture_ordinal"] < 2:
            return "first_post_cutoff_successful_capture"
        if not row["snapshot_height_matches_ledger"]:
            return "snapshot_height_ledger_mismatch"
        if row["created_at_block"] <= row["preceding_successful_snapshot_height"]:
            return "not_created_after_preceding_snapshot"
        if row["created_at_block"] > row["first_snapshot_height"]:
            return "created_after_first_observed_snapshot"
        return "eligible"

    panel["inception_eligibility_reason"] = panel.apply(exclusion_reason, axis=1)

    if not close_events.empty and {
        "execution_id",
        "close_block_height",
        "close_reason",
        "close_actor_class",
    }.issubset(close_events.columns):
        closes = close_events.copy()
        closes["close_block_height"] = _number(closes, "close_block_height")
        closes = (
            closes.dropna(subset=["execution_id", "close_block_height", "close_reason"])
            .sort_values(["execution_id", "close_block_height", "run_ts"])
            .drop_duplicates(["execution_id", "close_block_height"], keep="first")
            .drop_duplicates("execution_id", keep="first")
        )
        if "event_scope" not in closes:
            closes["event_scope"] = None
        panel = panel.merge(
            closes.loc[
                :,
                [
                    "execution_id",
                    "close_block_height",
                    "close_reason",
                    "close_actor_class",
                    "event_scope",
                ],
            ],
            on="execution_id",
            how="left",
            validate="one_to_one",
        )
    else:
        panel["close_block_height"] = np.nan
        panel["close_reason"] = None
        panel["close_actor_class"] = None
        panel["event_scope"] = None

    panel["close_event_exact"] = (
        panel["close_block_height"].notna()
        & panel["closed_on_block"].notna()
        & panel["close_block_height"].eq(panel["closed_on_block"])
    )
    panel["duration_blocks"] = panel["close_block_height"] - panel["created_at_block"]
    panel["observed_followup_blocks"] = (
        panel["last_snapshot_height"] - panel["created_at_block"]
    )
    panel["followup_complete_300"] = (
        panel["close_event_exact"]
        | panel["duration_blocks"].ge(FOLLOWUP_BLOCKS)
        | panel["observed_followup_blocks"].ge(FOLLOWUP_BLOCKS)
    )
    return panel.sort_values(["first_seen_at", "execution_id"]).reset_index(drop=True)


def event_choice_panel(rows: pd.DataFrame) -> pd.DataFrame:
    required = {
        "order_id",
        "choice_set_id",
        "run_ts",
        "dt",
        "bid_id",
        "provider",
        "native_price_amount",
        "native_price_denom",
        "selected_contract",
        "event_window_complete",
    }
    if rows.empty or not required.issubset(rows.columns):
        return pd.DataFrame()
    frame = rows.loc[rows["event_window_complete"].astype(bool)].copy()
    frame["native_price_amount"] = _number(frame, "native_price_amount")
    frame["captured_at"] = _time(frame, "run_ts")
    frame = frame.dropna(
        subset=[
            "order_id",
            "choice_set_id",
            "captured_at",
            "bid_id",
            "provider",
            "native_price_amount",
            "native_price_denom",
        ]
    )
    frame = frame.loc[frame["native_price_amount"].ge(0)].drop_duplicates(
        ["choice_set_id", "bid_id"], keep="last"
    )
    output = []
    for choice_set_id, group in frame.groupby("choice_set_id", sort=True):
        selected = group.loc[group["selected_contract"].astype(bool)]
        denoms = group["native_price_denom"].unique()
        if len(selected) != 1 or len(denoms) != 1 or group["provider"].nunique() < 2:
            continue
        selected_row = selected.iloc[0]
        lowest = float(group["native_price_amount"].min())
        selected_price = float(selected_row["native_price_amount"])
        output.append(
            {
                "order_id": group["order_id"].iloc[0],
                "choice_set_id": choice_set_id,
                "run_ts": group["run_ts"].iloc[0],
                "source_day": str(group["dt"].iloc[0]),
                "selected_bid_id": selected_row["bid_id"],
                "selected_provider": selected_row["provider"],
                "native_price_denom": denoms[0],
                "retained_bids": int(group["bid_id"].nunique()),
                "retained_providers": int(group["provider"].nunique()),
                "selected_native_price": selected_price,
                "lowest_native_price": lowest,
                "selected_above_lowest": bool(selected_price > lowest),
                "selected_price_premium_to_lowest": (
                    selected_price / lowest - 1 if lowest > 0 else np.nan
                ),
            }
        )
    panel = pd.DataFrame(output)
    if panel.empty:
        return panel
    panel["captured_at"] = _time(panel, "run_ts")
    return (
        panel.sort_values(["captured_at", "choice_set_id"])
        .drop_duplicates("order_id", keep="first")
        .drop(columns="captured_at")
        .reset_index(drop=True)
    )


def linked_panel(lifecycle: pd.DataFrame, choices: pd.DataFrame) -> pd.DataFrame:
    if lifecycle.empty or choices.empty:
        return pd.DataFrame()
    panel = choices.merge(
        lifecycle,
        left_on="selected_bid_id",
        right_on="execution_id",
        how="inner",
        validate="one_to_one",
        suffixes=("_choice", "_lease"),
    )
    panel["provider_close_300"] = (
        panel["close_event_exact"]
        & panel["close_actor_class"].eq("provider")
        & panel["duration_blocks"].le(FOLLOWUP_BLOCKS)
    )
    panel["escrow_close_300"] = (
        panel["close_event_exact"]
        & panel["close_actor_class"].eq("escrow")
        & panel["duration_blocks"].le(FOLLOWUP_BLOCKS)
    )
    panel["nonowner_close_300"] = panel["provider_close_300"] | panel["escrow_close_300"]
    panel["owner_close_300"] = (
        panel["close_event_exact"]
        & panel["close_actor_class"].eq("owner")
        & panel["duration_blocks"].le(FOLLOWUP_BLOCKS)
    )
    panel["confirmatory"] = (
        panel["prospective_inception_eligible"].astype(bool)
        & panel["first_seen_at"].le(RELEASE_CUTOFF)
    )
    return panel.sort_values(["first_seen_at", "execution_id"]).reset_index(drop=True)


def _wilson(successes: int, total: int) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    low, high = proportion_confint(successes, total, method="wilson")
    return float(low), float(high)


def _risk_rows(panel: pd.DataFrame, outcome: str) -> list[dict[str, Any]]:
    rows = []
    for exposure in (False, True):
        group = panel.loc[panel["selected_above_lowest"].eq(exposure)]
        successes = int(group[outcome].sum())
        total = int(len(group))
        low, high = _wilson(successes, total)
        rows.append(
            {
                "outcome": outcome,
                "selected_above_lowest": exposure,
                "events": successes,
                "leases": total,
                "risk": successes / total if total else None,
                "wilson_low": low,
                "wilson_high": high,
            }
        )
    return rows


def _risk_difference(panel: pd.DataFrame, outcome: str, exposure: pd.Series | None = None) -> float:
    assigned = panel["selected_above_lowest"] if exposure is None else exposure
    low = panel.loc[~assigned.astype(bool), outcome]
    high = panel.loc[assigned.astype(bool), outcome]
    return float(high.mean() - low.mean()) if len(low) and len(high) else float("nan")


def _cluster_bootstrap_interval(
    panel: pd.DataFrame, outcome: str
) -> tuple[float | None, float | None]:
    providers = panel["selected_provider"].dropna().unique()
    if len(providers) < 2:
        return None, None
    rng = np.random.default_rng(90)
    estimates = []
    groups = {
        provider: panel.loc[panel["selected_provider"].eq(provider)]
        for provider in providers
    }
    for _ in range(BOOTSTRAPS):
        sampled = rng.choice(providers, size=len(providers), replace=True)
        draw = pd.concat([groups[provider] for provider in sampled], ignore_index=True)
        estimate = _risk_difference(draw, outcome)
        if np.isfinite(estimate):
            estimates.append(estimate)
    if not estimates:
        return None, None
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high)


def _permutation_p_value(panel: pd.DataFrame, outcome: str) -> float | None:
    observed = _risk_difference(panel, outcome)
    if not np.isfinite(observed):
        return None
    rng = np.random.default_rng(9001)
    strata = [
        group.index.to_numpy()
        for _, group in panel.groupby(["native_price_denom", "source_day_choice"])
    ]
    exposure = panel["selected_above_lowest"].to_numpy(dtype=bool)
    draws = []
    for _ in range(PERMUTATIONS):
        shuffled = exposure.copy()
        for indices in strata:
            shuffled[indices] = rng.permutation(shuffled[indices])
        draws.append(abs(_risk_difference(panel, outcome, pd.Series(shuffled, index=panel.index))))
    return float((1 + np.sum(np.asarray(draws) >= abs(observed))) / (1 + len(draws)))


def outcome_analysis(panel: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    panel = panel.reset_index(drop=True)
    outcomes = ["provider_close_300", "escrow_close_300", "nonowner_close_300"]
    risks = pd.DataFrame([row for outcome in outcomes for row in _risk_rows(panel, outcome)])
    contrasts = []
    raw_p_values = []
    for outcome in outcomes:
        estimate = _risk_difference(panel, outcome)
        low, high = _cluster_bootstrap_interval(panel, outcome)
        p_value = _permutation_p_value(panel, outcome)
        raw_p_values.append(p_value if p_value is not None else 1.0)
        contrasts.append(
            {
                "outcome": outcome,
                "risk_difference_above_minus_lowest": estimate if np.isfinite(estimate) else None,
                "cluster_bootstrap_low": low,
                "cluster_bootstrap_high": high,
                "permutation_p_value": p_value,
            }
        )
    adjusted = multipletests(raw_p_values, method="holm")[1]
    for row, value in zip(contrasts, adjusted, strict=True):
        row["holm_adjusted_p_value"] = float(value)
    return risks, contrasts


def _support(panel: pd.DataFrame) -> dict[str, Any]:
    if panel.empty:
        return {
            "linked_multi_provider_leases": 0,
            "complete_300_block_followup": 0,
            "selected_providers": 0,
            "source_days": 0,
            "above_lowest": 0,
            "selected_lowest": 0,
            "exact_close_event_replay_rate": None,
        }
    observed_closes = panel["closed_on_block"].notna()
    exact_rate = (
        float(panel.loc[observed_closes, "close_event_exact"].mean())
        if observed_closes.any()
        else None
    )
    return {
        "linked_multi_provider_leases": int(len(panel)),
        "complete_300_block_followup": int(panel["followup_complete_300"].sum()),
        "selected_providers": int(panel["selected_provider"].nunique()),
        "source_days": int(panel["source_day_choice"].nunique()),
        "above_lowest": int(panel["selected_above_lowest"].sum()),
        "selected_lowest": int((~panel["selected_above_lowest"]).sum()),
        "exact_close_event_replay_rate": exact_rate,
    }


def _released_power_assessment(panel: pd.DataFrame) -> dict[str, Any]:
    """Apply the frozen adequacy label without changing the release date."""
    support = _support(panel)
    total = len(panel)
    above_share = (
        float(panel["selected_above_lowest"].mean()) if total else None
    )
    event_counts = {
        "selected_lowest": int(
            panel.loc[
                panel["selected_above_lowest"].eq(False), "provider_close_300"
            ].sum()
        )
        if total
        else 0,
        "selected_above_lowest": int(
            panel.loc[
                panel["selected_above_lowest"].eq(True), "provider_close_300"
            ].sum()
        )
        if total
        else 0,
    }
    checks = {
        "minimum_leases": total >= MIN_RELEASE_LEASES,
        "minimum_selected_providers": (
            support["selected_providers"] >= MIN_RELEASE_PROVIDERS
        ),
        "exposure_share_between_10_and_90_percent": (
            above_share is not None and 0.10 <= above_share <= 0.90
        ),
        "minimum_exact_close_event_replay_rate": (
            support["exact_close_event_replay_rate"] is not None
            and support["exact_close_event_replay_rate"] >= 0.95
        ),
        "minimum_primary_events_each_arm": min(event_counts.values())
        >= MIN_EVENT_COUNT_PER_ARM,
    }
    return {
        "label": "adequately_powered" if all(checks.values()) else "underpowered",
        "checks": checks,
        "above_lowest_share": above_share,
        "primary_event_counts": event_counts,
    }


def analyze_frames(
    leases: pd.DataFrame,
    close_events: pd.DataFrame,
    bid_events: pd.DataFrame,
    choice_bids: pd.DataFrame,
    source_runs: pd.DataFrame | None = None,
    *,
    now: datetime | pd.Timestamp | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lifecycle = lifecycle_panel(leases, close_events, choice_bids, source_runs)
    choices = event_choice_panel(bid_events)
    linked = linked_panel(lifecycle, choices)
    if linked.empty:
        linked = pd.DataFrame(
            columns=[
                "confirmatory",
                "prospective_inception_eligible",
                "inception_eligibility_reason",
                "followup_complete_300",
                "first_seen_at",
                "selected_above_lowest",
                "selected_provider",
                "source_day_choice",
                "closed_on_block",
                "close_event_exact",
            ]
        )
    exploratory = linked.loc[
        linked["first_seen_at"].lt(PREREG_CUTOFF)
        & linked["followup_complete_300"].eq(True)
    ].copy()
    confirmatory = linked.loc[linked["confirmatory"].eq(True)].copy()
    post_cutoff_ineligible = linked.loc[
        linked["first_seen_at"].ge(PREREG_CUTOFF)
        & linked["confirmatory"].eq(False)
    ].copy()
    confirmatory_complete = confirmatory.loc[
        confirmatory["followup_complete_300"].eq(True)
    ].copy()
    current = pd.Timestamp(now if now is not None else datetime.now(UTC))
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    else:
        current = current.tz_convert("UTC")
    released = bool(current >= RELEASE_CUTOFF)

    exploratory_risks, exploratory_contrasts = (
        outcome_analysis(exploratory)
        if not exploratory.empty
        else (pd.DataFrame(), [])
    )
    confirmatory_risks = pd.DataFrame()
    confirmatory_contrasts: list[dict[str, Any]] = []
    if released and not confirmatory_complete.empty:
        confirmatory_risks, confirmatory_contrasts = outcome_analysis(confirmatory_complete)
    power_assessment = (
        _released_power_assessment(confirmatory_complete) if released else None
    )

    summary = {
        "study_id": STUDY_ID,
        "preregistration": "docs/h90-akash-contract-termination-preregistration.md",
        "preregistration_cutoff": PREREG_CUTOFF.isoformat(),
        "fixed_release_cutoff": RELEASE_CUTOFF.isoformat(),
        "outcomes_released": released,
        "exploratory_evidence_status": "exploratory_pre_preregistration",
        "exploratory_support": _support(exploratory),
        "exploratory_contrasts": exploratory_contrasts,
        "confirmatory_support": _support(confirmatory),
        "confirmatory_complete_followup": int(len(confirmatory_complete)),
        "confirmatory_contrasts": confirmatory_contrasts if released else None,
        "confirmatory_power_assessment": power_assessment,
        "post_cutoff_ineligible": int(len(post_cutoff_ineligible)),
        "inception_eligibility_reasons": {
            str(key): int(value)
            for key, value in linked["inception_eligibility_reason"].value_counts().items()
        },
        "release_requirements": {
            "fixed_calendar_cutoff": RELEASE_CUTOFF.isoformat(),
            "minimum_leases_for_adequate_power_label": MIN_RELEASE_LEASES,
            "minimum_selected_providers": MIN_RELEASE_PROVIDERS,
            "minimum_primary_events_per_exposure_arm": MIN_EVENT_COUNT_PER_ARM,
            "minimum_exact_close_event_replay_rate": 0.95,
        },
        "claim_boundary": (
            "H90 links public Akash bid price rank to an exact on-chain contract-termination "
            "path. It does not observe workload start, readiness, compute delivery, failure, "
            "default, provider cost or intent, buyer value, welfare, or a causal price effect."
        ),
        "protocol_hash": hashlib.sha256(
            b"h90-v1|300-block|provider-escrow-owner|fixed-2026-08-15T01:15Z"
        ).hexdigest(),
    }
    return summary, linked, exploratory_risks, confirmatory_risks


def _plot_support(linked: pd.DataFrame, out_dir: Path) -> None:
    if linked.empty:
        return
    confirm = linked.loc[linked["confirmatory"]]
    labels = ["lowest", "above lowest"]
    counts = [
        int((~confirm["selected_above_lowest"]).sum()),
        int(confirm["selected_above_lowest"].sum()),
    ]
    complete = [
        int((~confirm["selected_above_lowest"] & confirm["followup_complete_300"]).sum()),
        int((confirm["selected_above_lowest"] & confirm["followup_complete_300"]).sum()),
    ]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    x = np.arange(2)
    ax.bar(x, counts, color="#8da0cb", label="linked")
    ax.bar(x, complete, color="#66c2a5", label="300-block follow-up complete")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Leases")
    ax.set_title("H90 outcome-masked confirmatory support")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out_dir / "h90_akash_contract_support.pdf")
    fig.savefig(out_dir / "h90_akash_contract_support.png", dpi=180)
    plt.close(fig)


def _plot_exploratory(risks: pd.DataFrame, out_dir: Path) -> None:
    if risks.empty:
        return
    outcomes = ["provider_close_300", "escrow_close_300", "nonowner_close_300"]
    labels = ["provider", "escrow", "provider or escrow"]
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    width = 0.36
    x = np.arange(len(outcomes))
    for offset, exposure, label, color in [
        (-width / 2, False, "selected lowest", "#4c78a8"),
        (width / 2, True, "selected above lowest", "#f58518"),
    ]:
        subset = risks.loc[risks["selected_above_lowest"].eq(exposure)].set_index("outcome")
        values = np.array([subset.at[outcome, "risk"] for outcome in outcomes], dtype=float)
        lows = np.array([subset.at[outcome, "wilson_low"] for outcome in outcomes], dtype=float)
        highs = np.array([subset.at[outcome, "wilson_high"] for outcome in outcomes], dtype=float)
        ax.bar(x + offset, values, width, label=label, color=color)
        ax.errorbar(
            x + offset,
            values,
            yerr=np.vstack([values - lows, highs - values]),
            fmt="none",
            color="black",
            capsize=3,
            linewidth=1,
        )
    ax.set_xticks(x, labels)
    ax.set_ylabel("300-block cumulative incidence")
    ax.set_title("H90 exploratory pre-preregistration calibration")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(out_dir / "h90_akash_contract_exploratory.pdf")
    fig.savefig(out_dir / "h90_akash_contract_exploratory.png", dpi=180)
    plt.close(fig)


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    leases = _load("market_executions")
    closes = _load("akash_market_lease_close_events")
    bid_events = _load("akash_market_bid_events")
    choice_bids = _load("akash_market_choice_bids")
    source_runs = _load("source_runs")
    summary, linked, exploratory_risks, confirmatory_risks = analyze_frames(
        leases, closes, bid_events, choice_bids, source_runs
    )
    safe_support_columns = [
        "execution_id",
        "order_id",
        "choice_set_id",
        "first_seen_run_ts",
        "first_seen_at",
        "selected_provider",
        "native_price_denom",
        "retained_bids",
        "retained_providers",
        "selected_above_lowest",
        "selected_price_premium_to_lowest",
        "first_snapshot_height",
        "preceding_successful_snapshot_height",
        "post_cutoff_capture_ordinal",
        "snapshot_source_verified",
        "snapshot_height_matches_ledger",
        "prospective_inception_eligible",
        "inception_eligibility_reason",
        "confirmatory",
        "followup_complete_300",
        "close_event_exact",
    ]
    if not linked.empty:
        save(linked.loc[:, safe_support_columns], out_dir, "h90_akash_contract_support")
    if not exploratory_risks.empty:
        save(exploratory_risks, out_dir, "h90_akash_contract_exploratory_risks")
    if summary["outcomes_released"] and not confirmatory_risks.empty:
        save(confirmatory_risks, out_dir, "h90_akash_contract_confirmatory_risks")
    save_json(summary, out_dir, "h90_summary")
    _plot_support(linked, out_dir)
    _plot_exploratory(exploratory_risks, out_dir)
    return summary
