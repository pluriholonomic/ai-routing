"""Pure policy and assignment primitives for the adaptive-router experiment.

The experiment emulates a router rather than claiming that OpenRouter exposes
arbitrary allocation weights.  For each frozen public provider menu, a policy
defines a probability distribution, the planner draws one endpoint with a
recorded seed, and paid execution pins the owned request to that endpoint.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pyarrow as pa

from .price_experiments import plan_manifest, provider_key

STUDY_ID = "openrouter-adaptive-monotone-v1"
PLAN_VERSION = "adaptive-monotone-plan-v1"
FIXED_HORIZON_BLOCKS = 120
MAX_TASK_QUOTE_USD = 0.02
CAP_MARKUP = 1.05

POLICY_SPECS: tuple[dict[str, Any], ...] = (
    {
        "policy": "baseline_eta2",
        "eta": 2.0,
        "exploration": 0.0,
        "reliability_power": 1.0,
        "selection_rule": "fixed",
    },
    {
        "policy": "calibrated_eta145",
        "eta": 1.45,
        "exploration": 0.0,
        "reliability_power": 1.0,
        "selection_rule": "fixed",
    },
    {
        "policy": "independent_explore_eta2_eps10",
        "eta": 2.0,
        "exploration": 0.10,
        "reliability_power": 1.0,
        "selection_rule": "fixed",
    },
    {
        "policy": "historical_cone_eta125_eps10",
        "eta": 1.25,
        "exploration": 0.10,
        "reliability_power": 1.0,
        "selection_rule": "fixed_from_2026_07_20_historical_replay",
    },
    {
        "policy": "cone_projected_menu_adaptive",
        "eta": None,
        "exploration": None,
        "reliability_power": 1.0,
        "selection_rule": "public_menu_projection",
    },
)

ADAPTIVE_CANDIDATE_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("observed_at", pa.string()),
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("block_id", pa.string()),
        ("model_id", pa.string()),
        ("shape_id", pa.string()),
        ("provider_name", pa.string()),
        ("endpoint_tag", pa.string()),
        ("endpoint_name", pa.string()),
        ("prompt_price_per_token", pa.float64()),
        ("completion_price_per_token", pa.float64()),
        ("expected_quote_usd", pa.float64()),
        ("conservative_quote_usd", pa.float64()),
        ("public_uptime_30m", pa.float64()),
        ("compatible", pa.bool_()),
        ("exclusion_reason", pa.string()),
        ("snapshot_sha256", pa.string()),
        ("conservative_input_tokens", pa.int64()),
        ("max_output_tokens", pa.int64()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)

ADAPTIVE_ASSIGNMENT_SCHEMA = pa.schema(
    [
        ("study_id", pa.string()),
        ("plan_version", pa.string()),
        ("run_id", pa.string()),
        ("block_id", pa.string()),
        ("task_id", pa.string()),
        ("model_id", pa.string()),
        ("shape_id", pa.string()),
        ("policy", pa.string()),
        ("replicate_index", pa.int32()),
        ("policy_order", pa.int32()),
        ("requested_provider", pa.string()),
        ("requested_endpoint_tag", pa.string()),
        ("provider_order_tags", pa.list_(pa.string())),
        ("provider_only_tags", pa.list_(pa.string())),
        ("provider_sort", pa.string()),
        ("allow_fallbacks", pa.bool_()),
        ("max_price_prompt_per_mtok", pa.float64()),
        ("max_price_completion_per_mtok", pa.float64()),
        ("task_quote_cap_usd", pa.float64()),
        ("conservative_input_tokens", pa.int64()),
        ("max_output_tokens", pa.int64()),
        ("session_group", pa.string()),
        ("assignment_seed", pa.string()),
        ("policy_eta", pa.float64()),
        ("policy_exploration", pa.float64()),
        ("policy_reliability_power", pa.float64()),
        ("provider_probability", pa.float64()),
        ("arm_probability", pa.float64()),
        ("joint_probability", pa.float64()),
        ("expected_quote_usd", pa.float64()),
        ("public_uptime_30m", pa.float64()),
        ("candidate_count", pa.int32()),
        ("menu_sha256", pa.string()),
        ("target_probabilities_json", pa.string()),
        ("policy_metrics_json", pa.string()),
        ("selection_uniform", pa.float64()),
        ("manifest_sha256", pa.string()),
        ("preflight_only", pa.bool_()),
        ("payload_retained", pa.bool_()),
        ("run_ts", pa.string()),
        ("dt", pa.string()),
    ]
)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _quality(value: Any) -> float | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    if number > 1.0:
        number /= 100.0
    return min(max(number, 0.01), 1.0)


def _canonical(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=True)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def collapse_menu(
    rows: Sequence[Mapping[str, Any]], *, max_task_quote_usd: float = MAX_TASK_QUOTE_USD
) -> list[dict[str, Any]]:
    """Keep the cheapest eligible exact endpoint for each provider."""
    best: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not bool(raw.get("compatible", True)):
            continue
        provider = provider_key(raw.get("provider_name"))
        tag = str(raw.get("endpoint_tag") or raw.get("tag") or "")
        quote = _number(raw.get("expected_quote_usd"))
        prompt = _number(raw.get("prompt_price_per_token", raw.get("price_prompt")))
        completion = _number(
            raw.get("completion_price_per_token", raw.get("price_completion"))
        )
        uptime = _quality(raw.get("public_uptime_30m", raw.get("uptime_last_30m")))
        if (
            not provider
            or not tag
            or quote is None
            or prompt is None
            or completion is None
            or uptime is None
            or min(quote, prompt, completion) <= 0
            or quote > max_task_quote_usd
        ):
            continue
        row = dict(raw)
        row.update(
            {
                "provider_key": provider,
                "endpoint_tag": tag,
                "expected_quote_usd": quote,
                "prompt_price_per_token": prompt,
                "completion_price_per_token": completion,
                "quality": uptime,
            }
        )
        current = best.get(provider)
        if current is None or quote < float(current["expected_quote_usd"]):
            best[provider] = row
    return sorted(
        best.values(),
        key=lambda row: (float(row["expected_quote_usd"]), str(row["provider_key"])),
    )


def allocation_probabilities(
    costs: Sequence[float],
    qualities: Sequence[float],
    *,
    eta: float,
    exploration: float = 0.0,
    reliability_power: float = 1.0,
) -> np.ndarray:
    """Monotone score shares mixed with provider-independent exploration."""
    p = np.asarray(costs, dtype=float)
    q = np.asarray(qualities, dtype=float)
    if len(p) == 0 or len(p) != len(q):
        raise ValueError("costs and qualities must be equally sized and nonempty")
    if np.any(~np.isfinite(p)) or np.any(p <= 0):
        raise ValueError("costs must be finite and positive")
    if np.any(~np.isfinite(q)) or np.any(q <= 0) or np.any(q > 1):
        raise ValueError("qualities must lie in (0, 1]")
    if eta < 0 or reliability_power < 0 or not 0 <= exploration < 1:
        raise ValueError("eta and reliability power must be nonnegative; exploration in [0,1)")
    logits = reliability_power * np.log(q) - eta * np.log(p)
    logits -= float(logits.max())
    score = np.exp(logits)
    base = score / score.sum()
    return (1.0 - exploration) * base + exploration / len(base)


def log_price_jacobian(
    costs: Sequence[float],
    qualities: Sequence[float],
    *,
    eta: float,
    exploration: float = 0.0,
    reliability_power: float = 1.0,
) -> np.ndarray:
    """Jacobian of log allocation shares with respect to log quoted prices."""
    mixed = allocation_probabilities(
        costs,
        qualities,
        eta=eta,
        exploration=exploration,
        reliability_power=reliability_power,
    )
    base = allocation_probabilities(
        costs,
        qualities,
        eta=eta,
        exploration=0.0,
        reliability_power=reliability_power,
    )
    derivative = -eta * (np.diag(base) - np.outer(base, base))
    derivative *= 1.0 - exploration
    return derivative / mixed[:, None]


def policy_metrics(
    costs: Sequence[float],
    qualities: Sequence[float],
    *,
    eta: float,
    exploration: float = 0.0,
    reliability_power: float = 1.0,
) -> dict[str, float]:
    shares = allocation_probabilities(
        costs,
        qualities,
        eta=eta,
        exploration=exploration,
        reliability_power=reliability_power,
    )
    jacobian = log_price_jacobian(
        costs,
        qualities,
        eta=eta,
        exploration=exploration,
        reliability_power=reliability_power,
    )
    off_diagonal = jacobian.copy()
    np.fill_diagonal(off_diagonal, 0.0)
    p = np.asarray(costs, dtype=float)
    q = np.asarray(qualities, dtype=float)
    return {
        "expected_quote_usd": float(shares @ p),
        "expected_reliability": float(shares @ q),
        "hhi": float(np.square(shares).sum()),
        "max_share": float(shares.max()),
        "cheapest_share": float(shares[int(np.argmin(p))]),
        "cross_provider_gain": float(np.linalg.norm(off_diagonal, ord=2)),
        "own_price_gain": float(np.abs(np.diag(jacobian)).mean()),
    }


def projected_policy(
    costs: Sequence[float],
    qualities: Sequence[float],
    *,
    max_cost_premium: float = 0.02,
    max_reliability_loss: float = 0.002,
) -> dict[str, Any]:
    """Choose the lowest-coupling monotone rule under frozen menu constraints."""
    baseline = policy_metrics(costs, qualities, eta=2.0)
    feasible: list[dict[str, Any]] = []
    for eta in (0.50, 0.75, 1.00, 1.25, 1.45, 1.75, 2.00):
        for exploration in (0.0, 0.05, 0.10, 0.15):
            metrics = policy_metrics(
                costs, qualities, eta=eta, exploration=exploration
            )
            if (
                metrics["expected_quote_usd"]
                <= baseline["expected_quote_usd"] * (1.0 + max_cost_premium) + 1e-15
                and metrics["expected_reliability"]
                >= baseline["expected_reliability"] - max_reliability_loss - 1e-15
            ):
                feasible.append(
                    {"eta": eta, "exploration": exploration, "metrics": metrics}
                )
    if not feasible:
        return {"eta": 2.0, "exploration": 0.0, "metrics": baseline}
    return min(
        feasible,
        key=lambda row: (
            row["metrics"]["cross_provider_gain"],
            row["metrics"]["hhi"],
            row["metrics"]["expected_quote_usd"],
        ),
    )


def resolved_policy_specs(
    costs: Sequence[float], qualities: Sequence[float]
) -> list[dict[str, Any]]:
    projected = projected_policy(costs, qualities)
    output = []
    for raw in POLICY_SPECS:
        row = dict(raw)
        if row["selection_rule"] == "public_menu_projection":
            row["eta"] = float(projected["eta"])
            row["exploration"] = float(projected["exploration"])
        output.append(row)
    return output


def _draw_index(probabilities: np.ndarray, uniform: float) -> int:
    cumulative = np.cumsum(probabilities)
    return min(int(np.searchsorted(cumulative, uniform, side="right")), len(probabilities) - 1)


def _block_score(rows: Sequence[Mapping[str, Any]]) -> float:
    menu = collapse_menu(rows)
    if len(menu) < 3:
        return float("-inf")
    costs = [float(row["expected_quote_usd"]) for row in menu]
    return math.log1p(len(menu)) * math.log(max(costs) / min(costs))


def build_adaptive_assignments(
    candidate_rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    seed: int,
    max_blocks: int = 3,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Freeze exact provider draws for four emulated allocation policies."""
    if max_blocks <= 0:
        raise ValueError("max_blocks must be positive")
    by_block: dict[str, list[Mapping[str, Any]]] = {}
    for row in candidate_rows:
        block_id = str(row.get("block_id") or "")
        if block_id:
            by_block.setdefault(block_id, []).append(row)
    eligible = [
        block_id
        for block_id in sorted(by_block)
        if math.isfinite(_block_score(by_block[block_id]))
    ]
    # Rotate deterministically inside the high-information pool. This preserves
    # outcome independence while preventing a single model from monopolizing runs.
    ranked = sorted(eligible, key=lambda block: _block_score(by_block[block]), reverse=True)
    pool = ranked[: min(12, len(ranked))]
    chooser = random.Random(seed ^ 0xAD4A71)
    chooser.shuffle(pool)
    selected_blocks = pool[:max_blocks]
    assignments: list[dict[str, Any]] = []
    selected_scores = []
    for block_id in selected_blocks:
        menu = collapse_menu(by_block[block_id])
        costs = [float(row["expected_quote_usd"]) for row in menu]
        qualities = [float(row["quality"]) for row in menu]
        menu_sha = _sha(
            [
                {
                    "provider": row["provider_key"],
                    "tag": row["endpoint_tag"],
                    "quote": row["expected_quote_usd"],
                    "quality": row["quality"],
                }
                for row in menu
            ]
        )
        block_assignments = []
        for spec in resolved_policy_specs(costs, qualities):
            eta = float(spec["eta"])
            exploration = float(spec["exploration"])
            reliability_power = float(spec["reliability_power"])
            probabilities = allocation_probabilities(
                costs,
                qualities,
                eta=eta,
                exploration=exploration,
                reliability_power=reliability_power,
            )
            draw_seed = int(
                hashlib.sha256(f"{seed}|{block_id}|{spec['policy']}".encode()).hexdigest()[:16],
                16,
            )
            uniform = random.Random(draw_seed).random()
            index = _draw_index(probabilities, uniform)
            selected = menu[index]
            tag = str(selected["endpoint_tag"])
            prompt_cap = CAP_MARKUP * float(selected["prompt_price_per_token"]) * 1_000_000
            completion_cap = (
                CAP_MARKUP * float(selected["completion_price_per_token"]) * 1_000_000
            )
            probability_map = {
                str(row["provider_key"]): float(probabilities[position])
                for position, row in enumerate(menu)
            }
            metrics = policy_metrics(
                costs,
                qualities,
                eta=eta,
                exploration=exploration,
                reliability_power=reliability_power,
            )
            policy = str(spec["policy"])
            block_assignments.append(
                {
                    "study_id": STUDY_ID,
                    "plan_version": PLAN_VERSION,
                    "run_id": run_id,
                    "block_id": block_id,
                    "task_id": f"{STUDY_ID}|{run_id}|{block_id}|{policy}|0",
                    "model_id": str(selected.get("model_id") or ""),
                    "shape_id": str(selected.get("shape_id") or ""),
                    "policy": policy,
                    "replicate_index": 0,
                    "requested_provider": str(selected.get("provider_name") or ""),
                    "requested_endpoint_tag": tag,
                    "provider_order_tags": [tag],
                    "provider_only_tags": [tag],
                    "provider_sort": None,
                    "allow_fallbacks": False,
                    "max_price_prompt_per_mtok": prompt_cap,
                    "max_price_completion_per_mtok": completion_cap,
                    "task_quote_cap_usd": CAP_MARKUP
                    * float(selected["conservative_quote_usd"]),
                    "conservative_input_tokens": int(
                        selected.get("conservative_input_tokens") or 96
                    ),
                    "max_output_tokens": int(selected.get("max_output_tokens") or 8),
                    "session_group": f"fresh|{STUDY_ID}|{run_id}|{block_id}|{policy}",
                    "assignment_seed": str(draw_seed),
                    "policy_eta": eta,
                    "policy_exploration": exploration,
                    "policy_reliability_power": reliability_power,
                    "provider_probability": float(probabilities[index]),
                    # Every eligible block executes all arms; the randomization
                    # occurs over providers and execution order, not arm inclusion.
                    "arm_probability": 1.0,
                    "joint_probability": float(probabilities[index]),
                    "expected_quote_usd": float(selected["expected_quote_usd"]),
                    "public_uptime_30m": float(selected["quality"]),
                    "candidate_count": len(menu),
                    "menu_sha256": menu_sha,
                    "target_probabilities_json": _canonical(probability_map),
                    "policy_metrics_json": _canonical(metrics),
                    "selection_uniform": uniform,
                    "payload_retained": False,
                }
            )
        order_rng = random.Random(
            int(hashlib.sha256(f"{seed}|{block_id}|order".encode()).hexdigest()[:16], 16)
        )
        order_rng.shuffle(block_assignments)
        for position, assignment in enumerate(block_assignments):
            assignment["policy_order"] = position
        assignments.extend(block_assignments)
        selected_scores.append({"block_id": block_id, "score": _block_score(by_block[block_id])})

    summary = {
        "study_id": STUDY_ID,
        "plan_version": PLAN_VERSION,
        "run_id": run_id,
        "seed": str(seed),
        "fixed_horizon_blocks": FIXED_HORIZON_BLOCKS,
        "candidate_blocks": len(by_block),
        "eligible_blocks": len(eligible),
        "planned_blocks": len(selected_blocks),
        "planned_tasks": len(assignments),
        "planned_quote_cap_usd": sum(
            float(row["task_quote_cap_usd"]) for row in assignments
        ),
        "selected_block_scores": selected_scores,
        "arm_names": [str(spec["policy"]) for spec in POLICY_SPECS],
    }
    return assignments, summary


def adaptive_manifest(
    candidates: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    return plan_manifest(candidates, assignments, summary)
