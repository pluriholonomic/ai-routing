"""WF-19: incidence of active-undercutter price cuts under shadow routing.

The public leg is an accounting experiment.  It freezes WF-16 provider-model
regimes, isolates later unilateral active-undercutter cuts, and decomposes the
inverse-square shadow-share and fixed-demand quote-revenue changes borne by
nonmoving provider types.  The paid leg summarizes owned default-route probes
around registered price events when those redacted tables are available.

Neither leg observes market-wide routed flow, provider marginal cost, profit,
private health state, or intent.  In particular, quote-revenue loss is not a
profit loss and the public shadow allocation is not a realized selection.
"""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from huggingface_hub import hf_hub_download

from ..config import DATA_DIR, HF_DATASET_REPO
from . import data
from .common import DEFAULT_OUT, save, save_json
from .wf16_provider_type_validation import TYPE_ORDER

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "undercutting_incidence_v1.toml"
WF16_BUNDLE = Path("analysis/provider-type-validation-v1")
UNCLASSIFIED = "unclassified"
REPORT_TYPES = tuple(TYPE_ORDER) + (UNCLASSIFIED,)


def load_protocol(path: Path = DEFAULT_CONFIG) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    return tomllib.loads(payload.decode("utf-8")), hashlib.sha256(payload).hexdigest()


def _artifact_path(out_dir: Path, name: str, *, revision: str) -> Path:
    """Resolve a local or revision-pinned published WF-16 artifact."""
    local_candidates = (
        out_dir / name,
        Path(DATA_DIR) / WF16_BUNDLE / name,
        ROOT / "data" / WF16_BUNDLE / name,
    )
    for candidate in local_candidates:
        if candidate.is_file():
            return candidate
    if os.environ.get("ORCAP_ANALYSIS_SOURCE", "hf") == "local":
        raise FileNotFoundError(f"required frozen WF16 artifact is absent: {name}")
    return Path(
        hf_hub_download(
            HF_DATASET_REPO,
            filename=str(WF16_BUNDLE / name),
            repo_type="dataset",
            revision=revision,
            token=os.environ.get("HF_TOKEN"),
        )
    )


def load_frozen_labels(
    out_dir: Path, protocol: dict[str, Any]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    study = protocol["study"]
    revision = str(study["frozen_label_artifact_revision"])
    labels_path = _artifact_path(
        out_dir, "wf16_provider_type_labels.parquet", revision=revision
    )
    summary_path = _artifact_path(out_dir, "wf16_summary.json", revision=revision)
    expected_hashes = {
        labels_path: str(study["frozen_labels_sha256"]),
        summary_path: str(study["frozen_summary_sha256"]),
    }
    for path, expected in expected_hashes.items():
        observed = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != expected:
            raise RuntimeError(
                f"frozen WF16 artifact hash mismatch for {path.name}: {observed}"
            )
    labels = pd.read_parquet(labels_path)
    summary = json.loads(summary_path.read_text())
    observed_source = str(summary.get("source", {}).get("revision") or "")
    if observed_source != str(study["frozen_label_source_revision"]):
        raise RuntimeError("frozen WF16 source revision does not match the protocol")
    required = {"model_id", "provider_name", "provider_type"}
    missing = required - set(labels.columns)
    if missing:
        raise ValueError(f"WF16 labels lack required columns: {sorted(missing)}")
    return labels, summary


def load_simulations() -> pd.DataFrame:
    rows = data.q(
        f"""
        select distinct run_ts, dt, panel_id, model_id, scenario, provider_name,
               expected_quote_usd, simulated_route_share, public_status,
               uptime_last_5m, uptime_last_30m
        from read_parquet(
          '{data.table_glob("routing_simulation")}', union_by_name=true
        )
        """
    ).df()
    if rows.empty:
        return rows
    rows["ts"] = pd.to_datetime(rows["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    for column in (
        "expected_quote_usd",
        "simulated_route_share",
        "uptime_last_5m",
        "uptime_last_30m",
    ):
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
    return rows.dropna(
        subset=["ts", "model_id", "scenario", "provider_name", "expected_quote_usd"]
    ).copy()


def _public_health_transition(before: pd.DataFrame, after: pd.DataFrame) -> bool:
    before_status = before["public_status"].fillna("__missing__").astype(str)
    after_status = after["public_status"].fillna("__missing__").astype(str)
    if not before_status.equals(after_status):
        return True
    for column in ("uptime_last_5m", "uptime_last_30m"):
        before_known = before[column].notna()
        after_known = after[column].notna()
        known = before_known & after_known
        if known.any():
            before_healthy = before.loc[known, column] >= 0.99
            after_healthy = after.loc[known, column] >= 0.99
            if not before_healthy.equals(after_healthy):
                return True
    return False


def build_provider_incidence(
    simulations: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    start: pd.Timestamp | None,
    max_gap_minutes: float,
    price_rtol: float,
    moving_type: str = "active_undercutter",
    direction: str = "cut",
    exclude_public_health_transitions: bool = True,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Construct one row per provider in each qualifying scenario transition."""
    counters = {
        "candidate_transitions": 0,
        "after_primary_start": 0,
        "contiguous": 0,
        "unchanged_provider_set": 0,
        "unchanged_public_health": 0,
        "unilateral_quote_move": 0,
        "frozen_active_mover": 0,
        "qualifying_direction": 0,
    }
    if simulations.empty or labels.empty:
        return pd.DataFrame(), counters
    frame = simulations.copy()
    if "ts" not in frame:
        frame["ts"] = pd.to_datetime(frame["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    label_map = labels.set_index(["model_id", "provider_name"])["provider_type"].to_dict()
    records: list[dict[str, Any]] = []
    group_cols = ["panel_id", "model_id", "scenario"]
    for (panel_id, model_id, scenario), group in frame.groupby(
        group_cols, dropna=False, sort=False
    ):
        snapshots = {
            timestamp: snapshot.set_index("provider_name").sort_index()
            for timestamp, snapshot in group.groupby("ts", sort=True)
        }
        ordered = sorted(snapshots)
        for before_ts, after_ts in zip(ordered, ordered[1:], strict=False):
            counters["candidate_transitions"] += 1
            if start is not None and after_ts < start:
                continue
            counters["after_primary_start"] += 1
            elapsed = (after_ts - before_ts).total_seconds() / 60
            if elapsed > max_gap_minutes:
                continue
            counters["contiguous"] += 1
            before, after = snapshots[before_ts], snapshots[after_ts]
            if set(before.index) != set(after.index):
                continue
            counters["unchanged_provider_set"] += 1
            if exclude_public_health_transitions and _public_health_transition(before, after):
                continue
            counters["unchanged_public_health"] += 1
            old_quote = before["expected_quote_usd"].astype(float)
            new_quote = after["expected_quote_usd"].astype(float)
            changed = ~np.isclose(old_quote, new_quote, rtol=price_rtol, atol=0.0)
            movers = list(old_quote.index[changed])
            if len(movers) != 1:
                continue
            counters["unilateral_quote_move"] += 1
            mover = str(movers[0])
            if label_map.get((str(model_id), mover)) != moving_type:
                continue
            counters["frozen_active_mover"] += 1
            mover_ratio = float(new_quote[mover] / old_quote[mover] - 1.0)
            if direction == "cut" and mover_ratio >= 0:
                continue
            if direction == "raise" and mover_ratio <= 0:
                continue
            counters["qualifying_direction"] += 1
            shock_id = "|".join(
                (
                    str(panel_id),
                    str(model_id),
                    before_ts.strftime("%Y%m%dT%H%M%SZ"),
                    after_ts.strftime("%Y%m%dT%H%M%SZ"),
                    mover,
                )
            )
            scenario_event_id = f"{shock_id}|{scenario}"
            before_share = before["simulated_route_share"].astype(float)
            after_share = after["simulated_route_share"].astype(float)
            nonmovers = [provider for provider in before.index if str(provider) != mover]
            total_share_loss = float((before_share[nonmovers] - after_share[nonmovers]).sum())
            total_revenue_loss = float(
                (
                    old_quote[nonmovers] * before_share[nonmovers]
                    - new_quote[nonmovers] * after_share[nonmovers]
                ).sum()
            )
            for provider in before.index:
                provider = str(provider)
                is_mover = provider == mover
                provider_type = label_map.get((str(model_id), provider), UNCLASSIFIED)
                share_before = float(before_share[provider])
                share_after = float(after_share[provider])
                share_loss = share_before - share_after
                revenue_before = float(old_quote[provider] * share_before)
                revenue_after = float(new_quote[provider] * share_after)
                revenue_loss = revenue_before - revenue_after
                records.append(
                    {
                        "shock_id": shock_id,
                        "scenario_event_id": scenario_event_id,
                        "panel_id": panel_id,
                        "model_id": model_id,
                        "scenario": scenario,
                        "previous_run_ts": before_ts.strftime("%Y%m%dT%H%M%SZ"),
                        "run_ts": after_ts.strftime("%Y%m%dT%H%M%SZ"),
                        "elapsed_minutes": elapsed,
                        "mover_provider": mover,
                        "provider_name": provider,
                        "provider_type": provider_type,
                        "is_mover": is_mover,
                        "price_before": float(old_quote[provider]),
                        "price_after": float(new_quote[provider]),
                        "price_change_fraction": float(
                            new_quote[provider] / old_quote[provider] - 1.0
                        ),
                        "share_before": share_before,
                        "share_after": share_after,
                        "share_change": share_after - share_before,
                        "share_loss": share_loss,
                        "relative_share_loss": (
                            share_loss / share_before if share_before > 0 else np.nan
                        ),
                        "quote_revenue_before": revenue_before,
                        "quote_revenue_after": revenue_after,
                        "quote_revenue_change": revenue_after - revenue_before,
                        "quote_revenue_loss": revenue_loss,
                        "share_loss_burden": (
                            share_loss / total_share_loss
                            if not is_mover and total_share_loss > 0
                            else np.nan
                        ),
                        "quote_revenue_loss_burden": (
                            revenue_loss / total_revenue_loss
                            if not is_mover and total_revenue_loss > 0
                            else np.nan
                        ),
                    }
                )
    return pd.DataFrame(records), counters


def aggregate_incidence(
    provider_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate providers to type-scenario rows, then equally weighted shocks."""
    if provider_panel.empty:
        return pd.DataFrame(), pd.DataFrame()
    nonmovers = provider_panel[~provider_panel["is_mover"]].copy()
    group_keys = [
        "shock_id",
        "scenario_event_id",
        "model_id",
        "scenario",
        "previous_run_ts",
        "run_ts",
        "mover_provider",
        "provider_type",
    ]
    grouped = (
        nonmovers.groupby(group_keys, as_index=False)
        .agg(
            providers=("provider_name", "nunique"),
            share_before=("share_before", "sum"),
            share_loss=("share_loss", "sum"),
            quote_revenue_before=("quote_revenue_before", "sum"),
            quote_revenue_loss=("quote_revenue_loss", "sum"),
        )
    )
    scenario_keys = group_keys[:-1]
    full_index = pd.MultiIndex.from_product(
        [
            provider_panel["scenario_event_id"].drop_duplicates(),
            REPORT_TYPES,
        ],
        names=["scenario_event_id", "provider_type"],
    )
    event_meta = (
        provider_panel.drop_duplicates("scenario_event_id")
        .set_index("scenario_event_id")[scenario_keys[0:1] + scenario_keys[2:]]
    )
    filled = (
        grouped.set_index(["scenario_event_id", "provider_type"])
        .reindex(full_index)
        .reset_index()
    )
    filled = filled.join(event_meta, on="scenario_event_id", rsuffix="_meta")
    for column in (
        "providers",
        "share_before",
        "share_loss",
        "quote_revenue_before",
        "quote_revenue_loss",
    ):
        filled[column] = filled[column].fillna(0.0)
    totals = filled.groupby("scenario_event_id").agg(
        total_nonmover_share=("share_before", "sum"),
        total_share_loss=("share_loss", "sum"),
        total_quote_revenue_loss=("quote_revenue_loss", "sum"),
    )
    filled = filled.join(totals, on="scenario_event_id")
    filled["normalized_pre_nonmover_share"] = np.where(
        filled["total_nonmover_share"] > 0,
        filled["share_before"] / filled["total_nonmover_share"],
        np.nan,
    )
    filled["share_loss_burden"] = np.where(
        filled["total_share_loss"] > 0,
        filled["share_loss"] / filled["total_share_loss"],
        np.nan,
    )
    filled["quote_revenue_loss_burden"] = np.where(
        filled["total_quote_revenue_loss"] > 0,
        filled["quote_revenue_loss"] / filled["total_quote_revenue_loss"],
        np.nan,
    )
    filled["relative_share_loss"] = np.where(
        filled["share_before"] > 0,
        filled["share_loss"] / filled["share_before"],
        np.nan,
    )
    movers = provider_panel[provider_panel["is_mover"]].copy()
    mover_summary = movers.groupby("shock_id", as_index=False).agg(
        mover_price_change_fraction=("price_change_fraction", "mean"),
        mover_share_before=("share_before", "mean"),
        mover_share_change=("share_change", "mean"),
        mover_quote_revenue_change=("quote_revenue_change", "mean"),
        scenario_count=("scenario", "nunique"),
    )
    shock_types = (
        filled.groupby(
            [
                "shock_id",
                "model_id",
                "previous_run_ts",
                "run_ts",
                "mover_provider",
                "provider_type",
            ],
            as_index=False,
        )
        .agg(
            providers=("providers", "mean"),
            share_before=("share_before", "mean"),
            share_loss=("share_loss", "mean"),
            normalized_pre_nonmover_share=("normalized_pre_nonmover_share", "mean"),
            share_loss_burden=("share_loss_burden", "mean"),
            relative_share_loss=("relative_share_loss", "mean"),
            quote_revenue_before=("quote_revenue_before", "mean"),
            quote_revenue_loss=("quote_revenue_loss", "mean"),
            quote_revenue_loss_burden=("quote_revenue_loss_burden", "mean"),
        )
        .merge(mover_summary, on="shock_id", how="left")
    )
    return filled, shock_types


def _bootstrap_type_means(
    shock_types: pd.DataFrame,
    *,
    metric: str,
    draws: int,
    seed: int,
) -> dict[str, list[float] | None]:
    if shock_types.empty:
        return {kind: None for kind in REPORT_TYPES}
    frame = shock_types.copy()
    frame["cluster_id"] = frame["model_id"].astype(str) + "|" + frame[
        "mover_provider"
    ].astype(str)
    clusters = sorted(frame["cluster_id"].unique())
    if len(clusters) < 2:
        return {kind: None for kind in REPORT_TYPES}
    by_cluster = {key: frame[frame["cluster_id"] == key] for key in clusters}
    rng = np.random.default_rng(seed)
    samples = {kind: [] for kind in REPORT_TYPES}
    for _ in range(draws):
        chosen = rng.choice(clusters, size=len(clusters), replace=True)
        draw = pd.concat([by_cluster[str(cluster)] for cluster in chosen], ignore_index=True)
        means = draw.groupby("provider_type")[metric].mean()
        for kind in REPORT_TYPES:
            samples[kind].append(float(means.get(kind, 0.0)))
    return {
        kind: [
            float(np.quantile(values, 0.025)),
            float(np.quantile(values, 0.975)),
        ]
        for kind, values in samples.items()
    }


def summarize_shadow(
    provider_panel: pd.DataFrame,
    shock_types: pd.DataFrame,
    counters: dict[str, int],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    if shock_types.empty:
        return {
            "evidence_status": "power_gated_no_qualifying_active_cuts",
            "transition_ledger": counters,
            "n_shocks": 0,
            "support_gate": {"passed": False},
        }
    inference = protocol["inference"]
    shocks = shock_types.drop_duplicates("shock_id")
    cluster_counts = (
        shocks.groupby(["model_id", "mover_provider"]).size().sort_values(ascending=False)
    )
    n_shocks = int(shock_types["shock_id"].nunique())
    n_models = int(shock_types["model_id"].nunique())
    n_movers = int(shock_types["mover_provider"].nunique())
    n_clusters = int(len(cluster_counts))
    maximum_cluster_share = float(cluster_counts.iloc[0] / n_shocks)
    support_gate = {
        "minimum_models": int(inference["minimum_models"]),
        "minimum_movers": int(inference["minimum_movers"]),
        "minimum_model_mover_clusters": int(inference["minimum_model_mover_clusters"]),
        "maximum_cluster_share_allowed": float(inference["maximum_cluster_share"]),
        "observed_models": n_models,
        "observed_movers": n_movers,
        "observed_model_mover_clusters": n_clusters,
        "observed_maximum_cluster_share": maximum_cluster_share,
    }
    support_gate["passed"] = bool(
        n_models >= support_gate["minimum_models"]
        and n_movers >= support_gate["minimum_movers"]
        and n_clusters >= support_gate["minimum_model_mover_clusters"]
        and maximum_cluster_share <= support_gate["maximum_cluster_share_allowed"]
    )
    ci_available = bool(
        n_clusters >= support_gate["minimum_model_mover_clusters"]
        and maximum_cluster_share <= support_gate["maximum_cluster_share_allowed"]
    )
    share_ci = (
        _bootstrap_type_means(
            shock_types,
            metric="share_loss_burden",
            draws=int(inference["bootstrap_draws"]),
            seed=int(inference["seed"]),
        )
        if ci_available
        else {kind: None for kind in REPORT_TYPES}
    )
    revenue_ci = (
        _bootstrap_type_means(
            shock_types,
            metric="quote_revenue_loss_burden",
            draws=int(inference["bootstrap_draws"]),
            seed=int(inference["seed"]) + 1,
        )
        if ci_available
        else {kind: None for kind in REPORT_TYPES}
    )
    by_type: dict[str, Any] = {}
    for kind in REPORT_TYPES:
        group = shock_types[shock_types["provider_type"] == kind]
        by_type[kind] = {
            "mean_pre_event_shadow_share": float(group["share_before"].mean()),
            "mean_shadow_share_loss": float(group["share_loss"].mean()),
            "mean_relative_share_loss_when_present": (
                float(group.loc[group["share_before"] > 0, "relative_share_loss"].mean())
                if (group["share_before"] > 0).any()
                else None
            ),
            "mean_share_loss_burden": float(group["share_loss_burden"].mean()),
            "share_loss_burden_cluster_bootstrap_95ci": share_ci[kind],
            "mean_quote_revenue_loss": float(group["quote_revenue_loss"].mean()),
            "mean_quote_revenue_loss_burden": float(
                group["quote_revenue_loss_burden"].mean()
            ),
            "quote_revenue_loss_burden_cluster_bootstrap_95ci": revenue_ci[kind],
        }
    largest_share = (
        shock_types.loc[
            shock_types.groupby("shock_id")["share_loss_burden"].idxmax(),
            ["shock_id", "provider_type"],
        ]["provider_type"].value_counts()
    )
    largest_revenue = (
        shock_types.loc[
            shock_types.groupby("shock_id")["quote_revenue_loss_burden"].idxmax(),
            ["shock_id", "provider_type"],
        ]["provider_type"].value_counts()
    )
    nonmovers = provider_panel[~provider_panel["is_mover"] & (provider_panel["share_before"] > 0)]
    spread = nonmovers.groupby("scenario_event_id")["relative_share_loss"].agg(
        lambda values: float(values.max() - values.min())
    )
    movers = provider_panel[provider_panel["is_mover"]].groupby("shock_id").agg(
        price_cut=("price_change_fraction", "mean"),
        share_before=("share_before", "mean"),
        share_change=("share_change", "mean"),
        revenue_change=("quote_revenue_change", "mean"),
    )
    return {
        "evidence_status": (
            "prospective_shadow_accounting_supported"
            if support_gate["passed"]
            else "prospective_shadow_accounting_type_inference_power_gated"
        ),
        "transition_ledger": counters,
        "n_shocks": n_shocks,
        "n_scenario_events": int(provider_panel["scenario_event_id"].nunique()),
        "n_models": n_models,
        "n_movers": n_movers,
        "n_model_mover_clusters": n_clusters,
        "date_range": [
            str(shock_types["run_ts"].min()),
            str(shock_types["run_ts"].max()),
        ],
        "median_mover_price_change_fraction": float(movers["price_cut"].median()),
        "mean_mover_share_before": float(movers["share_before"].mean()),
        "mean_mover_share_gain": float(movers["share_change"].mean()),
        "mover_quote_revenue_index_gain_rate": float((movers["revenue_change"] > 0).mean()),
        "maximum_within_scenario_relative_nonmover_loss_spread": float(spread.max()),
        "support_gate": support_gate,
        "type_confidence_intervals_available": ci_available,
        "confidence_interval_gate_note": (
            "Cluster-bootstrap confidence intervals are withheld until the frozen cluster "
            "count and concentration gates pass."
            if not ci_available
            else "Intervals resample model-mover clusters."
        ),
        "by_nonmoving_type": by_type,
        "largest_share_loss_type_counts": {
            str(key): int(value) for key, value in largest_share.items()
        },
        "largest_quote_revenue_loss_type_counts": {
            str(key): int(value) for key, value in largest_revenue.items()
        },
        "anchor_has_largest_mean_share_loss_burden": bool(
            by_type["anchor_adopter"]["mean_share_loss_burden"]
            == max(row["mean_share_loss_burden"] for row in by_type.values())
        ),
        "anchor_has_largest_mean_quote_revenue_loss_burden": bool(
            by_type["anchor_adopter"]["mean_quote_revenue_loss_burden"]
            == max(row["mean_quote_revenue_loss_burden"] for row in by_type.values())
        ),
    }


def _load_optional_table(name: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select * from read_parquet('{data.table_glob(name)}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def paid_event_validation(
    labels: pd.DataFrame, protocol: dict[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Summarize owned default-route selections around registered price events."""
    events = _load_optional_table("price_event_registry")
    attempts = _load_optional_table("router_route_attempts")
    candidates = _load_optional_table("price_event_candidates")
    if events.empty or attempts.empty:
        return pd.DataFrame(), pd.DataFrame(), {
            "evidence_status": "power_gated_missing_paid_event_tables",
            "default_attempts": 0,
            "events": 0,
        }
    def parse_metadata(value: Any) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    metadata = attempts.get("metadata_json", pd.Series("{}", index=attempts.index)).map(
        parse_metadata
    )
    attempts = attempts.copy()
    deduplication_keys = [
        column for column in ("source", "event_id") if column in attempts.columns
    ]
    if deduplication_keys:
        attempts = attempts.drop_duplicates(deduplication_keys)
    attempts["registered_event_id"] = metadata.map(lambda value: value.get("event_id"))
    attempts["wave_id"] = metadata.map(lambda value: value.get("wave_id"))
    attempts["block_id"] = metadata.map(lambda value: value.get("block_id"))
    settings = protocol["paid_validation"]
    owned = attempts[
        (attempts["study_id"] == settings["study_id"])
        & (attempts["policy"] == settings["default_policy"])
        & attempts["registered_event_id"].notna()
    ].copy()
    if owned.empty:
        return pd.DataFrame(), pd.DataFrame(), {
            "evidence_status": "power_gated_no_default_event_attempts",
            "default_attempts": 0,
            "events": 0,
        }
    registry = events.drop_duplicates("event_id").rename(
        columns={"event_id": "registered_event_id", "provider_name": "moving_provider"}
    )
    owned = owned.merge(
        registry[
            [
                "registered_event_id",
                "detected_at",
                "model_id",
                "moving_provider",
                "event_type",
                "relative_change",
            ]
        ],
        on=["registered_event_id", "model_id"],
        how="inner",
    )
    label_map = labels.set_index(["model_id", "provider_name"])["provider_type"].to_dict()
    owned["moving_provider_type"] = [
        label_map.get((model, provider), UNCLASSIFIED)
        for model, provider in zip(owned["model_id"], owned["moving_provider"], strict=True)
    ]
    owned["selected_provider_type"] = [
        label_map.get((model, provider), UNCLASSIFIED)
        for model, provider in zip(owned["model_id"], owned["selected_provider"], strict=True)
    ]
    owned["selected_mover"] = owned["selected_provider"].str.casefold() == owned[
        "moving_provider"
    ].str.casefold()
    active = owned[
        (owned["moving_provider_type"] == "active_undercutter")
        # A sub-threshold cut that crosses ranks is registered as a
        # ``rank_crossing`` by the generic event study.  Economic direction,
        # not that registry label, defines the WF-19 treatment.
        & (owned["relative_change"] < 0)
    ].copy()
    active_events = registry[
        registry.apply(
            lambda row: label_map.get((row["model_id"], row["moving_provider"]))
            == "active_undercutter"
            and float(row["relative_change"]) < 0,
            axis=1,
        )
    ].copy()
    event_count = int(active["registered_event_id"].nunique())
    attempt_count = int(len(active))
    passed = bool(
        attempt_count >= int(settings["minimum_default_attempts"])
        and event_count >= int(settings["minimum_events"])
    )
    actual = (
        active.groupby(
            [
                "registered_event_id",
                "wave_id",
                "block_id",
                "selected_provider_type",
            ],
            as_index=False,
        ).agg(selections=("event_id", "size"))
        if not active.empty
        else pd.DataFrame()
    )
    if not actual.empty:
        actual["requests"] = actual.groupby("block_id")["selections"].transform("sum")
        actual["realized_selection_share"] = actual["selections"] / actual["requests"]

    predicted = pd.DataFrame()
    if not candidates.empty and not active.empty:
        active_blocks = active[
            ["registered_event_id", "wave_id", "block_id", "model_id"]
        ].drop_duplicates()
        menu = candidates.merge(active_blocks, on=["block_id", "model_id"], how="inner")
        if "compatible" in menu:
            menu = menu[menu["compatible"].fillna(False)]
        menu["expected_quote_usd"] = pd.to_numeric(
            menu["expected_quote_usd"], errors="coerce"
        )
        menu = menu[menu["expected_quote_usd"] > 0]
        menu = (
            menu.sort_values("expected_quote_usd")
            .drop_duplicates(["block_id", "provider_name"])
            .copy()
        )
        menu["selected_provider_type"] = [
            label_map.get((model, provider), UNCLASSIFIED)
            for model, provider in zip(menu["model_id"], menu["provider_name"], strict=True)
        ]
        menu["inverse_square_weight"] = menu["expected_quote_usd"].pow(-2)
        menu["predicted_shadow_share"] = menu["inverse_square_weight"] / menu.groupby(
            "block_id"
        )["inverse_square_weight"].transform("sum")
        predicted = menu.groupby(
            [
                "registered_event_id",
                "wave_id",
                "block_id",
                "selected_provider_type",
            ],
            as_index=False,
        )["predicted_shadow_share"].sum()

    merge_keys = [
        "registered_event_id",
        "wave_id",
        "block_id",
        "selected_provider_type",
    ]
    if predicted.empty:
        event_panel = actual.copy()
        event_panel["predicted_shadow_share"] = np.nan
    else:
        event_panel = actual.merge(predicted, on=merge_keys, how="outer")
    if not event_panel.empty:
        for column in ("selections", "realized_selection_share"):
            event_panel[column] = event_panel[column].fillna(0.0)
        if not predicted.empty:
            event_panel["predicted_shadow_share"] = event_panel[
                "predicted_shadow_share"
            ].fillna(0.0)
        request_map = active.groupby("block_id").size()
        event_panel["requests"] = event_panel["block_id"].map(request_map).fillna(0).astype(int)
        event_panel["calibration_residual"] = (
            event_panel["realized_selection_share"]
            - event_panel["predicted_shadow_share"]
        )
    by_wave_type = (
        event_panel.groupby(["wave_id", "selected_provider_type"], as_index=False)
        .agg(
            selections=("selections", "sum"),
            event_waves=("block_id", "nunique"),
            mean_realized_selection_share=("realized_selection_share", "mean"),
            mean_predicted_shadow_share=("predicted_shadow_share", "mean"),
            mean_calibration_residual=("calibration_residual", "mean"),
        )
        if not event_panel.empty
        else pd.DataFrame()
    )
    baseline_panel = build_continuous_paid_event_panel(
        active_events,
        attempts,
        labels,
        protocol,
    )
    baseline_eligible = baseline_panel[baseline_panel["support_eligible"]]
    baseline_events = (
        int(baseline_eligible["registered_event_id"].nunique())
        if not baseline_eligible.empty
        else 0
    )
    baseline_by_type = (
        baseline_eligible.groupby("selected_provider_type", as_index=False).agg(
            events=("registered_event_id", "nunique"),
            mean_pre_selection_share=("pre_selection_share", "mean"),
            mean_post_selection_share=("post_selection_share", "mean"),
            mean_post_minus_pre=("post_minus_pre", "mean"),
        )
        if not baseline_eligible.empty
        else pd.DataFrame()
    )
    return event_panel, baseline_panel, {
        "evidence_status": (
            "owned_default_event_validation_descriptive"
            if passed
            else "power_gated_owned_default_event_validation"
        ),
        "default_attempts": attempt_count,
        "events": event_count,
        "models": int(active["model_id"].nunique()) if not active.empty else 0,
        "movers": int(active["moving_provider"].nunique()) if not active.empty else 0,
        "moving_provider_selection_rate": (
            float(active["selected_mover"].mean()) if not active.empty else None
        ),
        "event_waves_with_contemporaneous_menu": int(predicted["block_id"].nunique())
        if not predicted.empty
        else 0,
        "mean_absolute_type_calibration_error": (
            float(event_panel["calibration_residual"].abs().mean())
            if not event_panel.empty and not predicted.empty
            else None
        ),
        "selection_by_wave_and_type": by_wave_type.to_dict("records"),
        "continuous_default_pre_post": {
            "study_id": settings["baseline_study_id"],
            "policy": settings["baseline_policy"],
            "window_minutes_each_side": int(settings["baseline_window_minutes"]),
            "minimum_requests_per_side": int(
                settings["minimum_baseline_requests_per_side"]
            ),
            "eligible_events": baseline_events,
            "by_selected_provider_type": baseline_by_type.to_dict("records"),
            "boundary": (
                "Same-model owned default requests before and after the public cut are a "
                "descriptive event window. Time-varying eligibility and common demand shocks "
                "are not randomized away."
            ),
        },
        "support_gate_passed": passed,
        "boundary": (
            "Owned default-route selections validate realized routing only for sampled requests. "
            "They do not identify market-wide provider flow or profit."
        ),
    }


def build_continuous_paid_event_panel(
    active_events: pd.DataFrame,
    attempts: pd.DataFrame,
    labels: pd.DataFrame,
    protocol: dict[str, Any],
) -> pd.DataFrame:
    columns = [
        "registered_event_id",
        "detected_at",
        "model_id",
        "moving_provider",
        "selected_provider_type",
        "pre_selections",
        "post_selections",
        "pre_requests",
        "post_requests",
        "pre_selection_share",
        "post_selection_share",
        "post_minus_pre",
        "support_eligible",
    ]
    if active_events.empty or attempts.empty:
        return pd.DataFrame(columns=columns)
    settings = protocol["paid_validation"]
    baseline = attempts[
        (attempts["study_id"] == settings["baseline_study_id"])
        & (attempts["policy"] == settings["baseline_policy"])
        & (attempts["outcome"] == "succeeded")
        & attempts["selected_provider"].notna()
    ].copy()
    if baseline.empty:
        return pd.DataFrame(columns=columns)
    baseline["observed_ts"] = pd.to_datetime(
        baseline["observed_at"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    baseline = baseline.dropna(subset=["observed_ts"])
    label_map = labels.set_index(["model_id", "provider_name"])["provider_type"].to_dict()
    baseline["selected_provider_type"] = [
        label_map.get((model, provider), UNCLASSIFIED)
        for model, provider in zip(
            baseline["model_id"], baseline["selected_provider"], strict=True
        )
    ]
    window = pd.Timedelta(int(settings["baseline_window_minutes"]), unit="min")
    minimum = int(settings["minimum_baseline_requests_per_side"])
    rows: list[dict[str, Any]] = []
    for _, event in active_events.iterrows():
        detected = pd.to_datetime(event["detected_at"], utc=True)
        model_rows = baseline[baseline["model_id"] == event["model_id"]]
        pre = model_rows[
            (model_rows["observed_ts"] >= detected - window)
            & (model_rows["observed_ts"] < detected)
        ]
        post = model_rows[
            (model_rows["observed_ts"] >= detected)
            & (model_rows["observed_ts"] <= detected + window)
        ]
        pre_counts = pre["selected_provider_type"].value_counts()
        post_counts = post["selected_provider_type"].value_counts()
        pre_total, post_total = int(len(pre)), int(len(post))
        eligible = pre_total >= minimum and post_total >= minimum
        for kind in REPORT_TYPES:
            pre_count = int(pre_counts.get(kind, 0))
            post_count = int(post_counts.get(kind, 0))
            pre_share = pre_count / pre_total if pre_total else np.nan
            post_share = post_count / post_total if post_total else np.nan
            rows.append(
                {
                    "registered_event_id": event["registered_event_id"],
                    "detected_at": event["detected_at"],
                    "model_id": event["model_id"],
                    "moving_provider": event["moving_provider"],
                    "selected_provider_type": kind,
                    "pre_selections": pre_count,
                    "post_selections": post_count,
                    "pre_requests": pre_total,
                    "post_requests": post_total,
                    "pre_selection_share": pre_share,
                    "post_selection_share": post_share,
                    "post_minus_pre": post_share - pre_share,
                    "support_eligible": eligible,
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _render_figure(out_dir: Path, shock_types: pd.DataFrame, summary: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(13.0, 8.5), constrained_layout=True)
    colors = {
        "active_undercutter": "#D55E00",
        "anchor_adopter": "#0072B2",
        "static_discounter": "#009E73",
        "premium_differentiated": "#CC79A7",
        UNCLASSIFIED: "#8A8A8A",
    }
    by_type = summary.get("by_nonmoving_type", {})
    labels = [kind for kind in REPORT_TYPES if kind in by_type]
    display = [kind.replace("_", "\n") for kind in labels]
    share_values = [100 * by_type[kind]["mean_share_loss_burden"] for kind in labels]
    revenue_values = [
        100 * by_type[kind]["mean_quote_revenue_loss_burden"] for kind in labels
    ]
    axes[0, 0].bar(display, share_values, color=[colors[kind] for kind in labels])
    axes[0, 0].set_title("A. Who absorbs displaced shadow share?")
    axes[0, 0].set_ylabel("Mean burden per cut (%)")
    axes[0, 1].bar(display, revenue_values, color=[colors[kind] for kind in labels])
    axes[0, 1].set_title("B. Who absorbs fixed-demand quote revenue loss?")
    axes[0, 1].set_ylabel("Mean burden per cut (%)")
    for axis in axes[0]:
        axis.tick_params(axis="x", labelsize=8)
        axis.grid(axis="y", alpha=0.2)

    events = shock_types.pivot(
        index="shock_id", columns="provider_type", values="share_loss_burden"
    ).fillna(0.0)
    event_order = (
        shock_types.drop_duplicates("shock_id").sort_values("run_ts")["shock_id"].tolist()
    )
    events = events.reindex(event_order)
    bottom = np.zeros(len(events))
    x = np.arange(len(events))
    for kind in REPORT_TYPES:
        values = events.get(kind, pd.Series(0.0, index=events.index)).to_numpy(float)
        axes[1, 0].bar(
            x,
            100 * values,
            bottom=100 * bottom,
            width=1.0,
            color=colors[kind],
            label=kind.replace("_", " "),
        )
        bottom += values
    axes[1, 0].set_title("C. Share-loss incidence for each unilateral cut")
    axes[1, 0].set_xlabel("Cuts ordered by time")
    axes[1, 0].set_ylabel("Burden (%)")
    axes[1, 0].set_ylim(0, 100)
    axes[1, 0].legend(fontsize=7, ncol=2, loc="lower right")

    mover = shock_types.drop_duplicates("shock_id")
    axes[1, 1].scatter(
        -100 * mover["mover_price_change_fraction"],
        100 * mover["mover_share_change"],
        alpha=0.55,
        s=22,
        color="#D55E00",
        edgecolor="none",
    )
    axes[1, 1].set_title("D. Larger cuts mechanically gain more shadow share")
    axes[1, 1].set_xlabel("Price cut (%)")
    axes[1, 1].set_ylabel("Mover share gain (percentage points)")
    axes[1, 1].grid(alpha=0.2)
    fig.suptitle(
        "Active-undercutter incidence under inverse-square shadow routing\n"
        "Public quote accounting; not realized flow or provider profit",
        fontsize=14,
    )
    for extension in ("png", "pdf"):
        fig.savefig(out_dir / f"wf19_undercutting_incidence.{extension}", dpi=200)
    plt.close(fig)


def _render_power_gated_figure(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    axis.axis("off")
    axis.text(
        0.5,
        0.58,
        "No qualifying prospective unilateral active-undercutter cuts",
        ha="center",
        va="center",
        fontsize=15,
    )
    axis.text(
        0.5,
        0.42,
        "WF-19 remains power-gated; no zero-effect estimate is imputed.",
        ha="center",
        va="center",
        fontsize=11,
        color="#555555",
    )
    for extension in ("png", "pdf"):
        fig.savefig(out_dir / f"wf19_undercutting_incidence.{extension}", dpi=200)
    plt.close(fig)


def run(
    out_dir: Path = DEFAULT_OUT,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    protocol, protocol_sha = load_protocol(config_path)
    labels, wf16_summary = load_frozen_labels(out_dir, protocol)
    holdout_start = pd.Timestamp(wf16_summary["holdout_start"], tz="UTC")
    settings = protocol["transitions"]
    with data.pinned_analysis_source() as source:
        simulations = load_simulations()
        provider_panel, counters = build_provider_incidence(
            simulations,
            labels,
            start=holdout_start,
            max_gap_minutes=float(settings["max_gap_minutes"]),
            price_rtol=float(settings["price_relative_tolerance"]),
            moving_type=str(settings["moving_type"]),
            direction=str(settings["direction"]),
            exclude_public_health_transitions=bool(
                settings["exclude_public_health_transitions"]
            ),
        )
        scenario_types, shock_types = aggregate_incidence(provider_panel)
        shadow = summarize_shadow(provider_panel, shock_types, counters, protocol)
        paid_rows, paid_baseline, paid = paid_event_validation(labels, protocol)

    save(provider_panel, out_dir, "wf19_provider_incidence")
    save(scenario_types, out_dir, "wf19_scenario_type_incidence")
    save(shock_types, out_dir, "wf19_shock_type_incidence")
    save(paid_rows, out_dir, "wf19_owned_default_event_panel")
    save(paid_baseline, out_dir, "wf19_continuous_default_event_panel")
    if not shock_types.empty:
        _render_figure(out_dir, shock_types, shadow)
    else:
        _render_power_gated_figure(out_dir)
    result = {
        "study_id": protocol["study"]["id"],
        "protocol_sha256": protocol_sha,
        "analysis_source": source,
        "frozen_label_source_revision": wf16_summary.get("source", {}).get("revision"),
        "frozen_label_holdout_start": str(wf16_summary["holdout_start"]),
        "shadow": shadow,
        "paid_validation": paid,
        "claim_boundary": (
            "WF19 measures inverse-square shadow-share and fixed-demand quote-revenue "
            "incidence after unilateral public quote cuts. Shadow share is not realized flow; "
            "quote revenue is not profit. Owned default probes cover only our sampled requests. "
            "Private health, capacity, rebates, marginal cost, demand expansion, intent, and "
            "market-wide provider token flow remain unobserved."
        ),
    }
    save_json(result, out_dir, "wf19_summary")
    return result
