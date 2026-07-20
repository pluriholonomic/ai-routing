"""Shared estimation and monitoring for the realized router price exponent."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp

PRIMARY_POLICIES = frozenset(
    {
        "default_budgeted_iid",
        "default_loose_fresh",
        "default_broad",
        "openrouter_default",
    }
)


def probabilities(costs: np.ndarray, eta: float) -> np.ndarray:
    if len(costs) == 0 or np.any(~np.isfinite(costs)) or np.any(costs <= 0):
        raise ValueError("costs must be finite, positive, and nonempty")
    logits = -float(eta) * np.log(costs)
    return np.exp(logits - logsumexp(logits))


def negative_log_likelihood(eta: float, observations: Sequence[dict[str, Any]]) -> float:
    total = 0.0
    for observation in observations:
        selected = observation.get("selected_index")
        if selected is None:
            continue
        costs = np.asarray(observation["costs"], dtype=float)
        if int(selected) < 0 or int(selected) >= len(costs):
            raise ValueError("selected_index outside candidate menu")
        total -= math.log(max(float(probabilities(costs, eta)[int(selected)]), 1e-15))
    return total


def _profile_nll(grid: np.ndarray, observations: Sequence[dict[str, Any]]) -> np.ndarray:
    """Vectorized likelihood profile used repeatedly by online bootstraps."""
    total = np.zeros(len(grid), dtype=float)
    for observation in observations:
        selected = observation.get("selected_index")
        if selected is None:
            continue
        log_costs = np.log(np.asarray(observation["costs"], dtype=float))
        index = int(selected)
        if index < 0 or index >= len(log_costs):
            raise ValueError("selected_index outside candidate menu")
        total += logsumexp(-np.outer(grid, log_costs), axis=1) + grid * log_costs[index]
    return total


def _prepare_likelihood(
    observations: Sequence[dict[str, Any]],
) -> list[tuple[np.ndarray, np.ndarray]]:
    by_size: dict[int, list[tuple[np.ndarray, float]]] = {}
    for observation in observations:
        selected = observation.get("selected_index")
        if selected is None:
            continue
        costs = np.asarray(observation["costs"], dtype=float)
        if len(costs) == 0 or np.any(~np.isfinite(costs)) or np.any(costs <= 0):
            raise ValueError("costs must be finite, positive, and nonempty")
        index = int(selected)
        if index < 0 or index >= len(costs):
            raise ValueError("selected_index outside candidate menu")
        logs = np.log(costs)
        by_size.setdefault(len(logs), []).append((logs, float(logs[index])))
    return [
        (
            np.stack([item[0] for item in values]),
            np.asarray([item[1] for item in values], dtype=float),
        )
        for values in by_size.values()
    ]


def _prepared_nll(eta: float, prepared: list[tuple[np.ndarray, np.ndarray]]) -> float:
    return float(
        sum(
            logsumexp(-eta * log_costs, axis=1).sum() + eta * selected_logs.sum()
            for log_costs, selected_logs in prepared
        )
    )


def fit_exponent(
    observations: Sequence[dict[str, Any]],
    *,
    minimum: int = 20,
    bounds: tuple[float, float] = (0.0, 8.0),
    profile: bool = True,
) -> dict[str, Any]:
    covered = [row for row in observations if row.get("selected_index") is not None]
    if len(covered) < minimum:
        return {
            "fit_ready": False,
            "status": "insufficient_observations",
            "n_fit": len(covered),
            "eta_hat": None,
            "eta_profile_ci_low": None,
            "eta_profile_ci_high": None,
        }
    prepared = _prepare_likelihood(covered)
    result = minimize_scalar(
        lambda eta: _prepared_nll(float(eta), prepared),
        bounds=bounds,
        method="bounded",
        options={"xatol": 1e-7},
    )
    eta_hat = float(result.x)
    minimum_nll = float(result.fun)
    accepted = np.asarray([], dtype=float)
    if profile:
        grid = np.linspace(bounds[0], bounds[1], 801)
        accepted = grid[_profile_nll(grid, covered) <= minimum_nll + 1.9207]
    return {
        "fit_ready": bool(result.success),
        "status": "ready" if result.success else "optimizer_failed",
        "n_fit": len(covered),
        "eta_hat": eta_hat,
        "eta_profile_ci_low": float(accepted.min()) if len(accepted) else None,
        "eta_profile_ci_high": float(accepted.max()) if len(accepted) else None,
        "minimum_nll": minimum_nll,
    }


def score(observations: Sequence[dict[str, Any]], eta: float) -> dict[str, Any]:
    rows = []
    for observation in observations:
        selected = observation.get("selected_index")
        costs = np.asarray(observation["costs"], dtype=float)
        p = probabilities(costs, eta)
        if selected is None:
            continue
        target = np.zeros(len(p))
        target[int(selected)] = 1.0
        rows.append(
            {
                "log_loss": -math.log(max(float(p[int(selected)]), 1e-15)),
                "brier": float(np.square(p - target).sum()),
                "top_one": int(np.argmax(p)) == int(selected),
                "cost_regret": float(costs[int(selected)] - costs.min()),
            }
        )
    if not rows:
        return {
            "n": 0,
            "mean_log_loss": None,
            "mean_brier_score": None,
            "top_one_accuracy": None,
            "mean_cost_regret_usd": None,
        }
    frame = pd.DataFrame(rows)
    return {
        "n": len(frame),
        "mean_log_loss": float(frame["log_loss"].mean()),
        "mean_brier_score": float(frame["brier"].mean()),
        "top_one_accuracy": float(frame["top_one"].mean()),
        "mean_cost_regret_usd": float(frame["cost_regret"].mean()),
    }


def block_bootstrap_interval(
    observations: Sequence[dict[str, Any]],
    *,
    draws: int = 500,
    seed: int = 20260718,
    minimum: int = 20,
) -> tuple[float | None, float | None]:
    by_block: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(observations):
        block = str(row.get("block_id") or f"row-{index}")
        by_block.setdefault(block, []).append(row)
    if len(by_block) < 2 or draws <= 0:
        return None, None
    keys = sorted(by_block)
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(draws):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        rows = [item for key in sampled for item in by_block[str(key)]]
        fitted = fit_exponent(rows, minimum=minimum, profile=False)
        if fitted["fit_ready"]:
            estimates.append(float(fitted["eta_hat"]))
    if not estimates:
        return None, None
    return tuple(float(value) for value in np.quantile(estimates, [0.025, 0.975]))


def support_status(
    observations: Sequence[dict[str, Any]],
    *,
    minimum_choices: int = 200,
    minimum_models: int = 5,
    minimum_providers: int = 5,
    minimum_blocks: int = 100,
    minimum_coverage: float = 0.90,
) -> dict[str, Any]:
    total = len(observations)
    covered = [row for row in observations if row.get("selected_index") is not None]
    models = {str(row.get("model_id") or "") for row in covered if row.get("model_id")}
    providers = {
        str(row.get("selected_provider") or "") for row in covered if row.get("selected_provider")
    }
    blocks = {str(row.get("block_id") or "") for row in covered if row.get("block_id")}
    coverage = len(covered) / total if total else 0.0
    selected_counts = pd.Series(
        [str(row.get("selected_provider") or "") for row in covered]
    ).value_counts()
    concentration = float(selected_counts.max() / len(covered)) if len(covered) else 1.0
    log_ratios = []
    for row in covered:
        raw_costs = row.get("costs")
        costs = np.asarray(raw_costs if raw_costs is not None else [], dtype=float)
        if len(costs) >= 2 and np.all(costs > 0):
            log_ratios.append(float(np.log(costs.max() / costs.min())))
    price_iqr = float(np.subtract(*np.percentile(log_ratios, [75, 25]))) if log_ratios else 0.0
    failures = []
    if len(covered) < minimum_choices:
        failures.append("choices")
    if len(models) < minimum_models:
        failures.append("models")
    if len(providers) < minimum_providers:
        failures.append("providers")
    if len(blocks) < minimum_blocks:
        failures.append("blocks")
    if coverage < minimum_coverage:
        failures.append("coverage")
    if price_iqr < 0.05:
        failures.append("price_variation")
    if concentration > 0.60:
        failures.append("provider_concentration")
    return {
        "status": "ready" if not failures else "insufficient_support",
        "failures": failures,
        "observations": total,
        "covered_choices": len(covered),
        "models": len(models),
        "providers": len(providers),
        "blocks": len(blocks),
        "candidate_coverage": coverage,
        "selected_provider_concentration": concentration,
        "log_price_ratio_iqr": price_iqr,
    }
