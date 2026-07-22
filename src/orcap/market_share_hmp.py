"""Pure event, assignment, and elasticity logic for the GLM-5.2 HMP study."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from .price_experiments import collapse_provider_candidates, provider_key, sha256_json

STUDY_ID = "openrouter-glm52-market-share-hmp-v1"
PLAN_VERSION = "glm52-market-share-hmp-plan-v1"
MODEL_ID = "z-ai/glm-5.2"
INPUT_TOKENS = 96
OUTPUT_TOKENS = 1

EVENT_SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("detected_at", pa.string()),
        ("finalized_at", pa.string()),
        ("event_status", pa.string()),
        ("preliminary_eligible", pa.bool_()),
        ("contamination_window_complete", pa.bool_()),
        ("model_id", pa.string()),
        ("focal_provider", pa.string()),
        ("focal_provider_key", pa.string()),
        ("old_quote_usd", pa.float64()),
        ("new_quote_usd", pa.float64()),
        ("relative_change", pa.float64()),
        ("log_price_change", pa.float64()),
        ("multiplicity", pa.string()),
        ("co_cutter_count", pa.int32()),
        ("co_cutters", pa.list_(pa.string())),
        ("co_cutter_share_mass", pa.float64()),
        ("co_cutter_exposure", pa.float64()),
        ("pre_focal_share", pa.float64()),
        ("pre_active_share", pa.float64()),
        ("clean_event", pa.bool_()),
        ("exclusion_reason", pa.string()),
        ("source_start_run", pa.string()),
        ("source_end_run", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)

WAVE_SCHEMA = pa.schema(
    [
        ("event_id", pa.string()),
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("wave_id", pa.string()),
        ("target_at", pa.string()),
        ("latest_at", pa.string()),
        ("model_id", pa.string()),
        ("focal_provider", pa.string()),
        ("multiplicity", pa.string()),
        ("co_cutters", pa.list_(pa.string())),
        ("assignment_seed", pa.string()),
        ("event_sha256", pa.string()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)


def parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value)
        if len(text) == 16 and text.endswith("Z") and "T" in text:
            result = datetime.strptime(text, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        else:
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def routing_shares(
    prices: Sequence[float], *, eta: float, scores: Sequence[float] | None = None
) -> np.ndarray:
    values = np.asarray(prices, dtype=float)
    if values.ndim != 1 or not len(values) or np.any(~np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("prices must be a non-empty positive finite vector")
    score = np.zeros(len(values)) if scores is None else np.asarray(scores, dtype=float)
    if score.shape != values.shape or np.any(~np.isfinite(score)):
        raise ValueError("scores must be finite and match prices")
    utility = -float(eta) * np.log(values) + score
    weights = np.exp(utility - utility.max())
    return weights / weights.sum()


def elasticity_identity(
    shares: Sequence[float],
    *,
    focal: int,
    cutters: Sequence[int],
    eta: float,
    score_slope: float = 0.0,
) -> dict[str, float]:
    share = np.asarray(shares, dtype=float)
    members = sorted(set(int(item) for item in cutters))
    if (
        focal not in members
        or min(members, default=-1) < 0
        or max(members, default=-1) >= len(share)
    ):
        raise ValueError("cutters must contain the valid focal index")
    if not np.isclose(share.sum(), 1.0) or np.any(share < 0):
        raise ValueError("shares must be probabilities")
    effective = float(eta) - float(score_slope)
    unilateral = (1.0 - share[focal]) * effective
    group_share = float(share[members].sum())
    path = (1.0 - group_share) * effective
    return {
        "unilateral_elasticity": float(unilateral),
        "path_elasticity": float(path),
        "path_wedge": float(unilateral - path),
        "group_share": group_share,
        "other_cutter_share": float(group_share - share[focal]),
    }


def finite_path_elasticity(
    prices: Sequence[float],
    *,
    focal: int,
    cutters: Sequence[int],
    cut_fraction: float,
    eta: float,
) -> dict[str, float]:
    if not 0 < cut_fraction < 1:
        raise ValueError("cut_fraction must lie in (0, 1)")
    before = routing_shares(prices, eta=eta)
    after_prices = np.asarray(prices, dtype=float).copy()
    after_prices[list(cutters)] *= 1.0 - cut_fraction
    after = routing_shares(after_prices, eta=eta)
    denominator = math.log(1.0 - cut_fraction)
    arc = -(math.log(after[focal]) - math.log(before[focal])) / denominator
    identity = elasticity_identity(before, focal=focal, cutters=cutters, eta=eta)
    return identity | {
        "finite_path_elasticity": float(arc),
        "before_focal_share": float(before[focal]),
        "after_focal_share": float(after[focal]),
        "active_group_share_change": float(
            after[list(cutters)].sum() - before[list(cutters)].sum()
        ),
    }


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _quote(row: Mapping[str, Any]) -> float | None:
    prompt = _number(row.get("price_prompt", row.get("prompt_price_per_token")))
    completion = _number(row.get("price_completion", row.get("completion_price_per_token")))
    request = _number(row.get("price_request")) or 0.0
    if prompt is None or completion is None or min(prompt, completion) <= 0 or request < 0:
        return None
    return prompt * INPUT_TOKENS + completion * OUTPUT_TOKENS + request


def _collapse_snapshot(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for raw in frame.to_dict("records"):
        quote = _quote(raw)
        provider = str(raw.get("provider_name") or "")
        if quote is None or not provider:
            continue
        rows.append(
            {
                "run_ts": str(raw.get("run_ts") or ""),
                "ts": parse_time(raw.get("run_ts")),
                "provider_name": provider,
                "provider_key": provider_key(provider),
                "quote_usd": quote,
                "public_status": str(raw.get("status") or ""),
                "uptime_last_5m": _number(raw.get("uptime_last_5m")),
                "endpoint_tag": str(raw.get("tag") or raw.get("endpoint_tag") or ""),
            }
        )
    if not rows:
        return pd.DataFrame()
    output = pd.DataFrame(rows).sort_values(
        ["run_ts", "provider_key", "quote_usd", "endpoint_tag"], kind="stable"
    )
    return output.drop_duplicates(["run_ts", "provider_key"], keep="first")


def _congestion_contamination(
    enforcement: pd.DataFrame | None,
    *,
    start: datetime,
    end: datetime,
    minimum_rate_limit_spike_count: int,
    maximum_rate_limit_incidence: float,
    minimum_derankable_error_count: int,
    maximum_capacity_ceiling_change_fraction: float,
) -> list[str]:
    """Return preregistered public enforcement/capacity exclusions."""
    if enforcement is None or enforcement.empty or "run_ts" not in enforcement:
        return []
    frame = enforcement.copy()
    model = frame.get("model_permaslug", pd.Series("", index=frame.index)).astype(str)
    frame = frame[model.str.contains("glm-5.2", case=False, na=False)].copy()
    if frame.empty:
        return []
    frame["ts"] = frame["run_ts"].map(parse_time)
    frame = frame[frame["ts"].between(start, end, inclusive="both")]
    if frame.empty:
        return []
    reasons: list[str] = []
    deranked = frame.get("is_deranked", pd.Series(False, index=frame.index)).fillna(False)
    if deranked.astype(bool).any():
        reasons.append("public_derank")
    limited = pd.to_numeric(
        frame.get("rate_limited_5m", pd.Series(0, index=frame.index)), errors="coerce"
    ).fillna(0)
    successes = pd.to_numeric(
        frame.get("success_5m", pd.Series(0, index=frame.index)), errors="coerce"
    ).fillna(0)
    incidence = limited / (limited + successes).clip(lower=1)
    rate_limit_spike = (limited >= minimum_rate_limit_spike_count) & (
        incidence >= maximum_rate_limit_incidence
    )
    if rate_limit_spike.any():
        reasons.append("rate_limit_spike")
    errors = pd.to_numeric(
        frame.get("derankable_error_30m", pd.Series(0, index=frame.index)), errors="coerce"
    ).fillna(0)
    if (errors >= minimum_derankable_error_count).any():
        reasons.append("derankable_error_spike")
    capacity = pd.to_numeric(
        frame.get("capacity_ceiling_rpm", pd.Series(np.nan, index=frame.index)), errors="coerce"
    )
    capacity_frame = frame.assign(capacity=capacity).dropna(subset=["capacity"])
    if not capacity_frame.empty and "provider_name" in capacity_frame:
        for _, group in capacity_frame.sort_values("ts").groupby("provider_name"):
            previous = group["capacity"].shift()
            relative = (group["capacity"] - previous).abs() / previous.replace(0, np.nan)
            if relative.gt(maximum_capacity_ceiling_change_fraction).any():
                reasons.append("capacity_ceiling_changed")
                break
    return reasons


def _health_changed(before: pd.DataFrame, after: pd.DataFrame) -> bool:
    joined = before[["provider_key", "public_status", "uptime_last_5m"]].merge(
        after[["provider_key", "public_status", "uptime_last_5m"]],
        on="provider_key",
        suffixes=("_before", "_after"),
    )
    if not joined["public_status_before"].equals(joined["public_status_after"]):
        return True
    known = joined["uptime_last_5m_before"].notna() & joined["uptime_last_5m_after"].notna()
    if known.any():
        old = joined.loc[known, "uptime_last_5m_before"] >= 0.99
        new = joined.loc[known, "uptime_last_5m_after"] >= 0.99
        return bool((old.to_numpy() != new.to_numpy()).any())
    return False


def detect_events(
    snapshots: pd.DataFrame,
    *,
    active_providers: Sequence[str],
    author_providers: Sequence[str],
    eta: float,
    minimum_cut_fraction: float,
    comove_window_minutes: int,
    maximum_snapshot_gap_minutes: int,
    minimum_post_captures: int,
    minimum_unchanged_pre_captures: int = 2,
    contamination_window_minutes: int = 60,
    enforcement: pd.DataFrame | None = None,
    minimum_rate_limit_spike_count: int = 3,
    maximum_rate_limit_incidence: float = 0.10,
    minimum_derankable_error_count: int = 3,
    maximum_capacity_ceiling_change_fraction: float = 0.20,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Register and outcome-free finalize active-provider cuts from public snapshots."""
    required = {"run_ts", "model_id", "provider_name"}
    if not required.issubset(snapshots.columns):
        return []
    frame = snapshots[snapshots["model_id"].astype(str).eq(MODEL_ID)].copy()
    collapsed = _collapse_snapshot(frame)
    if collapsed.empty:
        return []
    active = {provider_key(value) for value in active_providers}
    authors = {provider_key(value) for value in author_providers}
    runs = sorted(collapsed["run_ts"].unique(), key=parse_time)
    transitions: list[dict[str, Any]] = []
    for transition_index, (old_run, new_run) in enumerate(zip(runs[:-1], runs[1:], strict=True)):
        before = collapsed[collapsed["run_ts"].eq(old_run)].copy()
        after = collapsed[collapsed["run_ts"].eq(new_run)].copy()
        gap = (parse_time(new_run) - parse_time(old_run)).total_seconds() / 60.0
        same_set = set(before["provider_key"]) == set(after["provider_key"])
        health_change = _health_changed(before, after) if same_set else True
        joined = before.merge(after, on="provider_key", suffixes=("_old", "_new"))
        joined["relative_change"] = joined["quote_usd_new"] / joined["quote_usd_old"] - 1.0
        for row in joined.to_dict("records"):
            if abs(float(row["relative_change"])) <= 1e-12:
                continue
            prior_unchanged = False
            if transition_index >= minimum_unchanged_pre_captures - 1:
                prior_runs = runs[
                    transition_index - minimum_unchanged_pre_captures + 1 : transition_index + 1
                ]
                prior = collapsed[
                    collapsed["run_ts"].isin(prior_runs)
                    & collapsed["provider_key"].eq(row["provider_key"])
                ]
                prior_unchanged = bool(
                    len(prior) == minimum_unchanged_pre_captures
                    and np.allclose(prior["quote_usd"], float(row["quote_usd_old"]))
                )
            transitions.append(
                {
                    "provider_key": row["provider_key"],
                    "provider_name": row["provider_name_new"],
                    "old_quote": float(row["quote_usd_old"]),
                    "new_quote": float(row["quote_usd_new"]),
                    "relative_change": float(row["relative_change"]),
                    "log_change": float(math.log(row["quote_usd_new"] / row["quote_usd_old"])),
                    "material_cut": bool(row["relative_change"] <= -minimum_cut_fraction),
                    "prior_unchanged": prior_unchanged,
                    "detected_at": parse_time(new_run),
                    "source_start_run": old_run,
                    "source_end_run": new_run,
                    "same_provider_set": same_set,
                    "health_change": health_change,
                    "gap_minutes": gap,
                    "before": before,
                }
            )
    latest = max(parse_time(run) for run in runs)
    clock = (now or latest).astimezone(UTC)
    window = timedelta(minutes=int(comove_window_minutes))
    rows: list[dict[str, Any]] = []
    active_cuts = sorted(
        (
            item
            for item in transitions
            if item["provider_key"] in active
            and item["material_cut"]
            and item["prior_unchanged"]
        ),
        key=lambda item: (item["detected_at"], item["provider_key"]),
    )
    clustered: list[dict[str, Any]] = []
    cluster_end: datetime | None = None
    for item in active_cuts:
        if cluster_end is not None and item["detected_at"] <= cluster_end:
            continue
        clustered.append(item)
        cluster_end = item["detected_at"] + window
    for focal in clustered:
        end = focal["detected_at"] + window
        observed_through = min(latest, clock)
        multiplicity_complete = observed_through >= end
        post_runs = [run for run in runs if focal["detected_at"] < parse_time(run) <= end]
        enough_post = len(post_runs) >= minimum_post_captures
        co = [
            item
            for item in transitions
            if item["provider_key"] in active
            and item["material_cut"]
            and item["provider_key"] != focal["provider_key"]
            and focal["detected_at"] <= item["detected_at"] <= end
        ]
        before = focal["before"]
        prices = before["quote_usd"].astype(float).to_numpy()
        shares = routing_shares(prices, eta=eta)
        share_map = dict(zip(before["provider_key"], shares, strict=True))
        focal_share = float(share_map.get(focal["provider_key"], 0.0))
        active_share = float(sum(share_map.get(key, 0.0) for key in active))
        co_share = float(sum(share_map.get(item["provider_key"], 0.0) for item in co))
        depth = abs(float(focal["log_change"]))
        exposure = float(
            sum(
                share_map.get(item["provider_key"], 0.0) * abs(float(item["log_change"])) / depth
                for item in co
            )
        )
        contamination_end = focal["detected_at"] + timedelta(
            minutes=int(contamination_window_minutes)
        )
        contamination_observed_end = min(observed_through, contamination_end)
        contamination_complete = observed_through >= contamination_end
        window_transitions = [
            item
            for item in transitions
            if focal["detected_at"] <= item["detected_at"] <= contamination_observed_end
        ]
        author_change = any(item["provider_key"] in authors for item in window_transitions)
        reasons = []
        if any(not item["same_provider_set"] for item in window_transitions):
            reasons.append("provider_set_changed")
        if any(item["health_change"] for item in window_transitions):
            reasons.append("public_health_changed")
        if any(item["gap_minutes"] > maximum_snapshot_gap_minutes for item in window_transitions):
            reasons.append("snapshot_gap")
        if author_change:
            reasons.append("author_price_changed")
        reasons.extend(
            _congestion_contamination(
                enforcement,
                start=focal["detected_at"],
                end=contamination_observed_end,
                minimum_rate_limit_spike_count=minimum_rate_limit_spike_count,
                maximum_rate_limit_incidence=maximum_rate_limit_incidence,
                minimum_derankable_error_count=minimum_derankable_error_count,
                maximum_capacity_ceiling_change_fraction=maximum_capacity_ceiling_change_fraction,
            )
        )
        reasons = list(dict.fromkeys(reasons))
        count = len({item["provider_key"] for item in co})
        multiplicity = (
            "pending"
            if not multiplicity_complete or not enough_post
            else "singleton"
            if count == 0
            else "pair"
            if count == 1
            else "multiple"
        )
        event_status = (
            "provisional"
            if multiplicity == "pending"
            else "final"
            if contamination_complete
            else "multiplicity_finalized"
        )
        preliminary_eligible = not reasons
        identity = {
            "model_id": MODEL_ID,
            "provider_key": focal["provider_key"],
            "detected_at": iso(focal["detected_at"]),
            "old_quote": focal["old_quote"],
            "new_quote": focal["new_quote"],
        }
        event_id = "mshmp-" + hashlib.sha256(sha256_json(identity).encode()).hexdigest()[:20]
        rows.append(
            {
                "event_id": event_id,
                "study_id": STUDY_ID,
                "plan_version": PLAN_VERSION,
                "detected_at": iso(focal["detected_at"]),
                "finalized_at": iso(end) if multiplicity != "pending" else None,
                "event_status": event_status,
                "preliminary_eligible": preliminary_eligible,
                "contamination_window_complete": contamination_complete,
                "model_id": MODEL_ID,
                "focal_provider": focal["provider_name"],
                "focal_provider_key": focal["provider_key"],
                "old_quote_usd": focal["old_quote"],
                "new_quote_usd": focal["new_quote"],
                "relative_change": focal["relative_change"],
                "log_price_change": focal["log_change"],
                "multiplicity": multiplicity,
                "co_cutter_count": count,
                "co_cutters": sorted({item["provider_name"] for item in co}),
                "co_cutter_share_mass": co_share,
                "co_cutter_exposure": exposure,
                "pre_focal_share": focal_share,
                "pre_active_share": active_share,
                "clean_event": bool(preliminary_eligible and contamination_complete),
                "exclusion_reason": ",".join(reasons) if reasons else None,
                "source_start_run": focal["source_start_run"],
                "source_end_run": focal["source_end_run"],
                "payload_retained": False,
            }
        )
    unique = {row["event_id"]: row for row in rows}
    return sorted(unique.values(), key=lambda row: (row["detected_at"], row["event_id"]))


def build_wave_plans(
    events: Sequence[Mapping[str, Any]],
    *,
    offsets_minutes: Sequence[int],
    tolerances_minutes: Sequence[int],
    seed: int,
) -> list[dict[str, Any]]:
    if len(offsets_minutes) != len(tolerances_minutes):
        raise ValueError("wave offsets and tolerances must have equal length")
    rows = []
    for event in events:
        if not bool(event.get("preliminary_eligible", event.get("clean_event"))):
            continue
        detected = parse_time(event["detected_at"])
        event_hash = sha256_json(dict(event))
        for offset, tolerance in zip(offsets_minutes, tolerances_minutes, strict=True):
            if int(offset) > 0 and str(event.get("multiplicity")) == "pending":
                continue
            if int(offset) >= 60 and not bool(event.get("clean_event")):
                continue
            target = detected + timedelta(minutes=int(offset))
            rows.append(
                {
                    "event_id": str(event["event_id"]),
                    "study_id": STUDY_ID,
                    "plan_version": PLAN_VERSION,
                    "wave_id": f"m{int(offset)}",
                    "target_at": iso(target),
                    "latest_at": iso(target + timedelta(minutes=int(tolerance))),
                    "model_id": MODEL_ID,
                    "focal_provider": str(event["focal_provider"]),
                    "multiplicity": str(event["multiplicity"]),
                    "co_cutters": list(event.get("co_cutters") or []),
                    "assignment_seed": str(seed),
                    "event_sha256": event_hash,
                    "payload_retained": False,
                }
            )
    return rows


def wave_status(row: Mapping[str, Any], *, now: datetime) -> str:
    if now < parse_time(row["target_at"]):
        return "pending"
    if now <= parse_time(row["latest_at"]):
        return "due"
    return "missed"


def _cap(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    if not rows:
        raise ValueError("price cap requires at least one provider")
    return {
        "prompt_per_mtok": 1.01
        * max(float(row["prompt_price_per_token"]) for row in rows)
        * 1_000_000,
        "completion_per_mtok": 1.01
        * max(float(row["completion_price_per_token"]) for row in rows)
        * 1_000_000,
    }


def _task_cap(cap: Mapping[str, float]) -> float:
    return (
        float(cap["prompt_per_mtok"]) * INPUT_TOKENS / 1_000_000
        + float(cap["completion_per_mtok"]) * OUTPUT_TOKENS / 1_000_000
    )


def build_paid_assignments(
    candidate_rows: Sequence[Mapping[str, Any]],
    wave: Mapping[str, Any],
    *,
    active_providers: Sequence[str],
    anchor_providers: Sequence[str],
    replicates_per_arm: int,
    run_id: str,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build six randomized complete-block menu arms for one due wave."""
    candidates = collapse_provider_candidates(candidate_rows)
    by_key = {str(row["provider_key"]): row for row in candidates}
    active_keys = [provider_key(item) for item in active_providers if provider_key(item) in by_key]
    anchor_keys = [provider_key(item) for item in anchor_providers if provider_key(item) in by_key]
    focal_key = provider_key(wave.get("focal_provider"))
    co_keys = [provider_key(item) for item in wave.get("co_cutters") or []]
    co_keys = [item for item in co_keys if item in by_key and item != focal_key]
    if focal_key not in by_key or len(anchor_keys) < 2 or len(active_keys) < 2:
        return [], {
            "skip_reason": "missing_focal_two_anchors_or_second_active_provider",
            "present_active_providers": active_keys,
            "present_anchor_providers": anchor_keys,
        }
    choices = co_keys or [key for key in active_keys if key != focal_key]
    pair_key = random.Random(f"{seed}|{wave['event_id']}|{wave['wave_id']}").choice(choices)
    anchors = [by_key[key] for key in anchor_keys]
    active = [by_key[key] for key in active_keys]
    focal = by_key[focal_key]
    pair = by_key[pair_key]
    broad = candidates
    arm_rows = {
        "broad_default": broad,
        "broad_price_sort": broad,
        "singleton_with_anchors": [focal, *anchors],
        "pair_with_anchors": [focal, pair, *anchors],
        "active_group_with_anchors": [*active, *anchors],
        "anchor_only": anchors,
    }
    block_id = f"{STUDY_ID}|{wave['event_id']}|{wave['wave_id']}|{MODEL_ID}|short_chat"
    assignments = []
    for policy, menu in arm_rows.items():
        cap = _cap(menu)
        tags = [str(row.get("endpoint_tag") or "") for row in menu]
        if any(not tag for tag in tags):
            raise ValueError(f"{policy} contains a provider without an endpoint tag")
        for replicate in range(replicates_per_arm):
            task_id = f"{block_id}|{policy}|{replicate}"
            assignments.append(
                {
                    "study_id": STUDY_ID,
                    "plan_version": PLAN_VERSION,
                    "run_id": run_id,
                    "event_id": str(wave["event_id"]),
                    "wave_id": str(wave["wave_id"]),
                    "block_id": block_id,
                    "task_id": task_id,
                    "model_id": MODEL_ID,
                    "shape_id": "short_chat",
                    "policy": policy,
                    "replicate_index": replicate,
                    "requested_provider": None,
                    "requested_endpoint_tag": None,
                    "provider_order_tags": None,
                    "provider_only_tags": tags,
                    "provider_sort": "price" if policy == "broad_price_sort" else None,
                    "allow_fallbacks": True,
                    "max_price_prompt_per_mtok": cap["prompt_per_mtok"],
                    "max_price_completion_per_mtok": cap["completion_per_mtok"],
                    "task_quote_cap_usd": _task_cap(cap),
                    "conservative_input_tokens": INPUT_TOKENS,
                    "max_output_tokens": OUTPUT_TOKENS,
                    "session_group": f"fresh|{task_id}",
                    "assignment_seed": str(seed),
                    "payload_retained": False,
                }
            )
    random.Random(seed).shuffle(assignments)
    for position, assignment in enumerate(assignments):
        assignment["policy_order"] = position
    return assignments, {
        "focal_provider_key": focal_key,
        "pair_provider_key": pair_key,
        "present_active_providers": active_keys,
        "present_anchor_providers": anchor_keys,
        "policy_counts": {
            name: sum(row["policy"] == name for row in assignments) for name in arm_rows
        },
    }
