"""Pure design and estimation primitives for information-congestion v1.

The module contains no network I/O.  It classifies provider roles from a
strictly pre-outcome public panel and turns a frozen live candidate menu into
deterministic randomized ``(n, k, overlap, rule)`` assignments.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from .price_experiments import (
    PRICE_RESPONSE_ASSIGNMENT_SCHEMA,
    PRICE_RESPONSE_CANDIDATE_SCHEMA,
    collapse_provider_candidates,
    provider_key,
    sha256_json,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "information_congestion_v1.toml"

IC_CANDIDATE_SCHEMA = PRICE_RESPONSE_CANDIDATE_SCHEMA
IC_ASSIGNMENT_SCHEMA = (
    PRICE_RESPONSE_ASSIGNMENT_SCHEMA.append(pa.field("market_epoch_id", pa.string()))
    .append(pa.field("target_n", pa.int32()))
    .append(pa.field("target_k", pa.int32()))
    .append(pa.field("overlap_arm", pa.string()))
    .append(pa.field("router_rule", pa.string()))
    .append(pa.field("selected_provider_keys", pa.list_(pa.string())))
    .append(pa.field("responsive_provider_keys", pa.list_(pa.string())))
    .append(pa.field("pair_abs_correlation", pa.float64()))
    .append(pa.field("protocol_sha256", pa.string()))
)
IC_MARKET_EPOCH_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("run_id", pa.string()),
        ("market_epoch_id", pa.string()),
        ("observed_at", pa.string()),
        ("model_id", pa.string()),
        ("eligible_n", pa.int32()),
        ("responsive_n", pa.int32()),
        ("menu_sha256", pa.string()),
        ("protocol_sha256", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)
IC_PROVIDER_ROLE_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("run_id", pa.string()),
        ("market_epoch_id", pa.string()),
        ("model_id", pa.string()),
        ("provider_name", pa.string()),
        ("provider_key", pa.string()),
        ("responsive", pa.bool_()),
        ("price_change_count", pa.int32()),
        ("snapshot_coverage", pa.float64()),
        ("median_relative_to_author", pa.float64()),
        ("mean_abs_correlation", pa.float64()),
        ("classification_cutoff", pa.string()),
        ("protocol_sha256", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)
IC_RUN_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("run_id", pa.string()),
        ("created_at", pa.string()),
        ("protocol_sha256", pa.string()),
        ("source_healthy", pa.bool_()),
        ("models_requested", pa.int32()),
        ("models_healthy", pa.int32()),
        ("market_epochs", pa.int32()),
        ("planned_tasks", pa.int32()),
        ("planned_quote_cap_usd", pa.float64()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)
IC_COMMON_SHOCK_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("event_id", pa.string()),
        ("event_type", pa.string()),
        ("event_ts", pa.string()),
        ("model_id", pa.string()),
        ("provider_key", pa.string()),
        ("provider_count", pa.int32()),
        ("affected_provider_keys", pa.list_(pa.string())),
        ("eligible_n", pa.int32()),
        ("pre_run_ts", pa.string()),
        ("post_run_ts", pa.string()),
        ("elapsed_minutes", pa.float64()),
        ("log_price_change", pa.float64()),
        ("previous_value", pa.float64()),
        ("new_value", pa.float64()),
        ("placebo", pa.bool_()),
        ("contaminated", pa.bool_()),
        ("protocol_sha256", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)


def load_protocol(path: Path = DEFAULT_CONFIG) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    protocol = tomllib.loads(payload.decode("utf-8"))
    required = {
        "study",
        "design",
        "shocks",
        "rank",
        "outcomes",
        "support",
        "budget",
        "claims",
    }
    missing = required - set(protocol)
    if missing:
        raise ValueError(f"information-congestion protocol missing sections: {sorted(missing)}")
    return protocol, hashlib.sha256(payload).hexdigest()


def _time_series(
    snapshots: pd.DataFrame,
    model_id: str,
    *,
    input_tokens: int = 96,
    output_tokens: int = 8,
) -> pd.DataFrame:
    required = {"run_ts", "model_id", "provider_name", "price_prompt", "price_completion"}
    if snapshots.empty or not required.issubset(snapshots):
        return pd.DataFrame()
    frame = snapshots[snapshots["model_id"].astype(str).eq(model_id)].copy()
    if frame.empty:
        return frame
    frame["ts"] = pd.to_datetime(
        frame["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    for column in ("price_prompt", "price_completion", "price_request"):
        if column not in frame:
            frame[column] = 0.0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    frame["quote_usd"] = (
        input_tokens * frame["price_prompt"]
        + output_tokens * frame["price_completion"]
        + frame["price_request"]
    )
    frame["provider_key"] = frame["provider_name"].map(provider_key)
    frame = frame.dropna(subset=["ts"])
    frame = frame[frame["quote_usd"].gt(0) & frame["provider_key"].ne("")]
    return (
        frame.sort_values(["ts", "provider_key", "quote_usd"], kind="stable")
        .drop_duplicates(["ts", "provider_key"], keep="first")
        .reset_index(drop=True)
    )


def classify_provider_roles(
    snapshots: pd.DataFrame,
    model_id: str,
    *,
    cutoff: pd.Timestamp,
    minimum_price_changes: int,
    minimum_history_snapshots: int,
    minimum_provider_coverage: float,
    author_keys: set[str] | None = None,
    innovation_horizon_hours: int = 1,
) -> tuple[pd.DataFrame, dict[tuple[str, str], float]]:
    """Classify providers using public data strictly before ``cutoff``.

    Responsiveness is an ex-ante sampling stratum: adequate coverage and at
    least the frozen number of positive-price changes.  Correlations use hourly
    log-quote innovations and are returned separately for high/low-overlap
    sampling.
    """

    frame = _time_series(snapshots, model_id)
    if frame.empty:
        return pd.DataFrame(), {}
    cutoff = pd.Timestamp(cutoff)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    frame = frame[frame["ts"].lt(cutoff)].copy()
    if frame.empty:
        return pd.DataFrame(), {}
    times = sorted(frame["ts"].unique())
    total = len(times)
    authors = {provider_key(item) for item in (author_keys or set())}
    author_by_time = (
        frame[frame["provider_key"].isin(authors)]
        .groupby("ts")["quote_usd"]
        .median()
        .to_dict()
    )

    pivot = frame.pivot(index="ts", columns="provider_key", values="quote_usd").sort_index()
    hourly = pivot.resample("1h").last().ffill(limit=1)
    innovations = np.log(hourly).diff(periods=max(1, int(innovation_horizon_hours)))
    correlations = innovations.corr(min_periods=8)
    pair_correlations: dict[tuple[str, str], float] = {}
    for left, right in itertools.combinations(sorted(correlations.columns), 2):
        value = correlations.loc[left, right]
        if pd.notna(value) and math.isfinite(float(value)):
            pair_correlations[(left, right)] = float(value)

    rows: list[dict[str, Any]] = []
    for key, group in frame.groupby("provider_key", sort=True):
        group = group.sort_values("ts")
        unique_quotes = group["quote_usd"].to_numpy(dtype=float)
        changes = int(np.count_nonzero(np.abs(np.diff(unique_quotes)) > 1e-15))
        coverage = len(group["ts"].unique()) / total if total else 0.0
        relative = []
        for row in group.itertuples(index=False):
            author_quote = author_by_time.get(row.ts)
            if author_quote is not None and float(author_quote) > 0:
                relative.append(float(row.quote_usd) / float(author_quote))
        corr_values = [
            abs(value)
            for pair, value in pair_correlations.items()
            if key in pair and math.isfinite(value)
        ]
        adequate = total >= minimum_history_snapshots and coverage >= minimum_provider_coverage
        rows.append(
            {
                "model_id": model_id,
                "provider_name": str(group["provider_name"].iloc[-1]),
                "provider_key": str(key),
                "responsive": bool(adequate and changes >= minimum_price_changes),
                "price_change_count": changes,
                "snapshot_coverage": float(coverage),
                "median_relative_to_author": (
                    float(np.median(relative)) if relative else None
                ),
                "mean_abs_correlation": (
                    float(np.mean(corr_values)) if corr_values else None
                ),
                "classification_cutoff": cutoff.isoformat(),
                "payload_retained": False,
            }
        )
    return pd.DataFrame(rows), pair_correlations


def subset_overlap(
    providers: Sequence[str], pair_correlations: Mapping[tuple[str, str], float]
) -> float | None:
    if len(providers) < 2:
        return None
    values = []
    for left, right in itertools.combinations(sorted(providers), 2):
        value = pair_correlations.get((left, right))
        if value is None:
            value = pair_correlations.get((right, left))
        if value is not None and math.isfinite(float(value)):
            values.append(abs(float(value)))
    return float(np.mean(values)) if values else None


def select_responsive_subset(
    providers: Sequence[str],
    k: int,
    overlap_arm: str,
    pair_correlations: Mapping[tuple[str, str], float],
    *,
    seed: int,
) -> tuple[list[str], float | None]:
    pool = sorted(set(providers))
    if k < 0 or k > len(pool):
        raise ValueError("responsive subset size is infeasible")
    if k == 0:
        return [], None
    rng = random.Random(seed)
    if k == 1:
        return [rng.choice(pool)], None
    if overlap_arm not in {"high", "low"}:
        raise ValueError("overlap arm must be high or low when k >= 2")
    # Keep exact search bounded without making the choice outcome-dependent.
    candidate_pool = pool if len(pool) <= 14 else rng.sample(pool, 14)
    scored = []
    for subset in itertools.combinations(candidate_pool, k):
        score = subset_overlap(subset, pair_correlations)
        if score is not None:
            scored.append((score, subset))
    if not scored:
        chosen = sorted(rng.sample(pool, k))
        return chosen, None
    scored.sort(key=lambda item: (item[0], item[1]))
    score, subset = scored[-1] if overlap_arm == "high" else scored[0]
    return list(subset), float(score)


def _cap(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    if not rows:
        raise ValueError("an information-congestion menu cannot be empty")
    return {
        "prompt_per_mtok": 1.01
        * max(float(row["prompt_price_per_token"]) for row in rows)
        * 1_000_000,
        "completion_per_mtok": 1.01
        * max(float(row["completion_price_per_token"]) for row in rows)
        * 1_000_000,
    }


def _task_cap(cap: Mapping[str, float], *, input_tokens: int, output_tokens: int) -> float:
    return (
        float(cap["prompt_per_mtok"]) * input_tokens / 1_000_000
        + float(cap["completion_per_mtok"]) * output_tokens / 1_000_000
    )


def market_epoch(
    candidates: Sequence[Mapping[str, Any]],
    *,
    study_id: str,
    plan_version: str,
    run_id: str,
    model_id: str,
    responsive_keys: set[str],
    protocol_sha256: str,
) -> dict[str, Any]:
    collapsed = collapse_provider_candidates(candidates)
    material = [
        {
            "provider_key": row["provider_key"],
            "prompt": row["prompt_price_per_token"],
            "completion": row["completion_price_per_token"],
            "endpoint_tag": row.get("endpoint_tag"),
        }
        for row in collapsed
    ]
    observed = str(collapsed[0].get("observed_at") or "") if collapsed else ""
    menu_hash = sha256_json(material)
    return {
        "study_id": study_id,
        "plan_version": plan_version,
        "run_id": run_id,
        "market_epoch_id": f"ic-{hashlib.sha256((model_id + menu_hash).encode()).hexdigest()[:20]}",
        "observed_at": observed,
        "model_id": model_id,
        "eligible_n": len(collapsed),
        "responsive_n": sum(str(row["provider_key"]) in responsive_keys for row in collapsed),
        "menu_sha256": menu_hash,
        "protocol_sha256": protocol_sha256,
        "payload_retained": False,
    }


def build_factorial_assignments(
    candidate_rows: Sequence[Mapping[str, Any]],
    role_rows: Sequence[Mapping[str, Any]],
    epochs: Sequence[Mapping[str, Any]],
    pair_correlations: Mapping[str, Mapping[tuple[str, str], float]],
    *,
    protocol: Mapping[str, Any],
    protocol_sha256: str,
    run_id: str,
    seed: int,
    prior_assignments: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build a deterministic, balance-seeking randomized factorial plan."""

    study = protocol["study"]
    design = protocol["design"]
    study_id = str(study["study_id"])
    plan_version = str(study["plan_version"])
    roles_by_model: dict[str, dict[str, bool]] = {}
    for row in role_rows:
        roles_by_model.setdefault(str(row["model_id"]), {})[str(row["provider_key"])] = bool(
            row["responsive"]
        )
    epoch_by_model = {str(row["model_id"]): dict(row) for row in epochs}
    candidates_by_model: dict[str, list[dict[str, Any]]] = {}
    for row in candidate_rows:
        candidates_by_model.setdefault(str(row["model_id"]), []).append(dict(row))

    prior_counts: dict[str, int] = {}
    for row in prior_assignments:
        key = "|".join(
            str(row.get(field) or "")
            for field in ("model_id", "target_n", "target_k", "overlap_arm", "router_rule")
        )
        prior_counts[key] = prior_counts.get(key, 0) + 1

    rng = random.Random(seed)
    feasible: list[tuple[int, str, int, int, str, str]] = []
    for model_id, raw_rows in candidates_by_model.items():
        collapsed = collapse_provider_candidates(raw_rows)
        role_map = roles_by_model.get(model_id, {})
        responsive = [
            str(row["provider_key"])
            for row in collapsed
            if role_map.get(str(row["provider_key"]))
        ]
        anchors = [
            str(row["provider_key"])
            for row in collapsed
            if not role_map.get(str(row["provider_key"]))
        ]
        for n in design["menu_sizes"]:
            n = int(n)
            if n > len(collapsed):
                continue
            for k in design["responsive_counts"]:
                k = int(k)
                if k > n or k > len(responsive) or n - k > len(anchors):
                    continue
                overlap_arms = ["none"] if k < 2 else list(design["overlap_arms"])
                for overlap in overlap_arms:
                    for rule in design["router_rules"]:
                        cell = f"{model_id}|{n}|{k}|{overlap}|{rule}"
                        feasible.append(
                            (prior_counts.get(cell, 0), model_id, n, k, overlap, str(rule))
                        )
    rng.shuffle(feasible)
    feasible.sort(key=lambda row: row[0])

    replicates = int(design["replicates_per_cell"])
    max_tasks = int(design["maximum_tasks_per_run"])
    maximum_cells = max_tasks // replicates
    selected_cells = feasible[:maximum_cells]
    assignments: list[dict[str, Any]] = []
    selected_summary = []
    for cell_position, (_, model_id, n, k, overlap, rule) in enumerate(selected_cells):
        collapsed = collapse_provider_candidates(candidates_by_model[model_id])
        by_key = {str(row["provider_key"]): row for row in collapsed}
        role_map = roles_by_model[model_id]
        responsive_pool = sorted(key for key in by_key if role_map.get(key))
        anchor_pool = sorted(key for key in by_key if not role_map.get(key))
        seed_material = f"{seed}|{model_id}|{n}|{k}|{overlap}|{rule}"
        cell_seed = int(hashlib.sha256(seed_material.encode()).hexdigest()[:16], 16)
        selected_responsive, overlap_score = select_responsive_subset(
            responsive_pool,
            k,
            overlap,
            pair_correlations.get(model_id, {}),
            seed=cell_seed,
        )
        cell_rng = random.Random(cell_seed)
        selected_anchors = sorted(cell_rng.sample(anchor_pool, n - k))
        selected_keys = sorted(selected_responsive + selected_anchors)
        menu = [by_key[key] for key in selected_keys]
        tags = [str(row.get("endpoint_tag") or "") for row in menu]
        if any(not tag for tag in tags):
            raise ValueError("selected provider is missing a live endpoint tag")
        cap = _cap(menu)
        input_tokens = max(int(row.get("conservative_input_tokens") or 96) for row in menu)
        output_tokens = max(int(row.get("max_output_tokens") or 8) for row in menu)
        epoch = epoch_by_model[model_id]
        block_id = (
            f"{study_id}|{run_id}|{epoch['market_epoch_id']}|n{n}|k{k}|{overlap}|{rule}|"
            f"{cell_position}"
        )
        for replicate in range(replicates):
            task_id = f"{block_id}|r{replicate}"
            assignments.append(
                {
                    "study_id": study_id,
                    "plan_version": plan_version,
                    "run_id": run_id,
                    "block_id": block_id,
                    "task_id": task_id,
                    "model_id": model_id,
                    "shape_id": "short_chat",
                    "policy": f"ic_n{n}_k{k}_{overlap}_{rule}",
                    "replicate_index": replicate,
                    "requested_provider": None,
                    "requested_endpoint_tag": None,
                    "provider_order_tags": None,
                    "provider_only_tags": tags,
                    "provider_sort": "price" if rule == "price" else None,
                    "allow_fallbacks": True,
                    "max_price_prompt_per_mtok": cap["prompt_per_mtok"],
                    "max_price_completion_per_mtok": cap["completion_per_mtok"],
                    "task_quote_cap_usd": _task_cap(
                        cap, input_tokens=input_tokens, output_tokens=output_tokens
                    ),
                    "conservative_input_tokens": input_tokens,
                    "max_output_tokens": output_tokens,
                    "session_group": f"fresh|{task_id}",
                    "assignment_seed": str(cell_seed),
                    "payload_retained": False,
                    "market_epoch_id": str(epoch["market_epoch_id"]),
                    "target_n": n,
                    "target_k": k,
                    "overlap_arm": overlap,
                    "router_rule": rule,
                    "selected_provider_keys": selected_keys,
                    "responsive_provider_keys": sorted(selected_responsive),
                    "pair_abs_correlation": overlap_score,
                    "protocol_sha256": protocol_sha256,
                }
            )
        selected_summary.append(
            {
                "model_id": model_id,
                "target_n": n,
                "target_k": k,
                "overlap_arm": overlap,
                "router_rule": rule,
                "selected_provider_keys": selected_keys,
                "responsive_provider_keys": sorted(selected_responsive),
                "pair_abs_correlation": overlap_score,
            }
        )
    rng.shuffle(assignments)
    for position, assignment in enumerate(assignments):
        assignment["policy_order"] = position
    validate_factorial_assignments(assignments)
    return assignments, {
        "feasible_cells": len(feasible),
        "selected_cells": len(selected_cells),
        "planned_tasks": len(assignments),
        "selected_cell_details": selected_summary,
    }


def validate_factorial_assignments(assignments: Sequence[Mapping[str, Any]]) -> None:
    task_ids = [str(row.get("task_id") or "") for row in assignments]
    if any(not item for item in task_ids) or len(task_ids) != len(set(task_ids)):
        raise ValueError("information-congestion task IDs must be nonempty and unique")
    forbidden = {"selected_provider", "outcome", "latency_ms", "cost_usd"}
    for row in assignments:
        if forbidden & set(row):
            raise ValueError("outcome field leaked into assignment-only plan")
        selected = _assignment_list(row.get("selected_provider_keys"))
        responsive = _assignment_list(row.get("responsive_provider_keys"))
        tags = _assignment_list(row.get("provider_only_tags"))
        if len(selected) != int(row["target_n"]) or len(tags) != int(row["target_n"]):
            raise ValueError("planned menu does not match target_n")
        if len(responsive) != int(row["target_k"]):
            raise ValueError("responsive set does not match target_k")
        if not set(responsive).issubset(selected):
            raise ValueError("responsive providers must be contained in selected menu")


def _assignment_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        raise ValueError("assignment menu fields must be lists")
    try:
        return list(value)
    except TypeError as exc:
        raise ValueError("assignment menu fields must be lists") from exc


def protocol_claim_boundary(protocol: Mapping[str, Any]) -> None:
    if any(bool(value) for value in protocol["claims"].values()):
        raise ValueError("prospective information-congestion claims must start false")


def canonical_bundle_hash(bundle: Mapping[str, Any]) -> str:
    reduced = {
        "candidates": bundle.get("candidates", []),
        "assignments": bundle.get("assignments", []),
        "market_epochs": bundle.get("market_epochs", []),
        "provider_roles": bundle.get("provider_roles", []),
        "summary": bundle.get("summary", {}),
    }
    return sha256_json(json.loads(json.dumps(reduced, sort_keys=True, default=str)))
