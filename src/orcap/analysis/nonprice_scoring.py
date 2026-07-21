"""Reduced-form measurement of router scoring beyond observable price.

The estimand is deliberately relative.  Conditional on a frozen provider menu,
we model a realized choice as

    Pr(i | menu) proportional to price_i ** (-eta) * exp(alpha_i).

``alpha_i`` is a provider fixed effect, not a structural quality parameter.  It
bundles every stable non-price input visible to the router (health, capacity,
latency, internal scoring, and preferences) plus any persistent mismatch
between the public menu and the realized eligible menu.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp

DEFAULT_RIDGE = 1.0
DEFAULT_NULL_DRAWS = 5_000


def _clean(observations: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for row in observations:
        selected = row.get("selected_index")
        if selected is None:
            continue
        providers = [str(value) for value in (row.get("providers") or [])]
        raw_costs = row.get("costs")
        costs = np.asarray([] if raw_costs is None else raw_costs, dtype=float)
        index = int(selected)
        if not providers or len(providers) != len(costs):
            raise ValueError("providers and costs must form the same nonempty menu")
        if len(set(providers)) != len(providers):
            raise ValueError("provider menu must be unique")
        if np.any(~np.isfinite(costs)) or np.any(costs <= 0):
            raise ValueError("costs must be finite and positive")
        if index < 0 or index >= len(providers):
            raise ValueError("selected_index outside candidate menu")
        cleaned.append(
            {
                **row,
                "providers": providers,
                "costs": costs,
                "selected_index": index,
                "block_id": str(row.get("block_id") or ""),
            }
        )
    return cleaned


def _design(observations: Sequence[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    providers = sorted({provider for row in observations for provider in row["providers"]})
    locations = {provider: index for index, provider in enumerate(providers)}
    designed = []
    for row in observations:
        designed.append(
            {
                **row,
                "global_indices": np.asarray(
                    [locations[provider] for provider in row["providers"]], dtype=int
                ),
            }
        )
    return providers, designed


def _objective(
    alpha: np.ndarray,
    observations: Sequence[dict[str, Any]],
    *,
    eta: float,
    ridge: float,
) -> tuple[float, np.ndarray]:
    value = 0.5 * ridge * float(alpha @ alpha)
    gradient = ridge * alpha.copy()
    for row in observations:
        indices = row["global_indices"]
        logits = -eta * np.log(row["costs"]) + alpha[indices]
        probs = np.exp(logits - logsumexp(logits))
        selected = int(row["selected_index"])
        value += float(logsumexp(logits) - logits[selected])
        np.add.at(gradient, indices, probs)
        gradient[indices[selected]] -= 1.0
    return value, gradient


def _fit(
    observations: Sequence[dict[str, Any]], *, eta: float, ridge: float
) -> tuple[list[str], np.ndarray, list[dict[str, Any]], bool]:
    providers, designed = _design(observations)
    initial = np.zeros(len(providers), dtype=float)
    result = minimize(
        lambda alpha: _objective(alpha, designed, eta=eta, ridge=ridge),
        initial,
        jac=True,
        method="L-BFGS-B",
        options={"ftol": 1e-11, "gtol": 1e-7, "maxiter": 1_000},
    )
    alpha = np.asarray(result.x, dtype=float)
    # The likelihood is invariant to a common shift; the penalty selects a
    # nearly zero-mean representative.  Center explicitly for reproducibility.
    alpha -= float(alpha.mean())
    return providers, alpha, designed, bool(result.success)


def _probabilities(row: dict[str, Any], alpha: np.ndarray, eta: float) -> np.ndarray:
    logits = -eta * np.log(row["costs"]) + alpha[row["global_indices"]]
    return np.exp(logits - logsumexp(logits))


def _cluster_covariance(
    observations: Sequence[dict[str, Any]],
    alpha: np.ndarray,
    *,
    eta: float,
    ridge: float,
) -> np.ndarray | None:
    blocks = sorted({row["block_id"] for row in observations})
    if len(blocks) < 20:
        return None
    dimension = len(alpha)
    bread = ridge * np.eye(dimension)
    block_scores: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(dimension))
    for row in observations:
        indices = row["global_indices"]
        probs = _probabilities(row, alpha, eta)
        local_hessian = np.diag(probs) - np.outer(probs, probs)
        bread[np.ix_(indices, indices)] += local_hessian
        gradient = np.zeros(dimension)
        np.add.at(gradient, indices, probs)
        gradient[indices[int(row["selected_index"])]] -= 1.0
        block_scores[row["block_id"]] += gradient
    inverse = np.linalg.pinv(bread, rcond=1e-10)
    meat = sum(np.outer(score, score) for score in block_scores.values())
    meat *= len(blocks) / (len(blocks) - 1)
    covariance = inverse @ meat @ inverse
    return (covariance + covariance.T) / 2


def _cross_validated_log_loss(
    observations: Sequence[dict[str, Any]],
    *,
    eta: float,
    ridge: float,
    folds: int = 5,
) -> dict[str, Any]:
    blocks = sorted(
        {row["block_id"] for row in observations},
        key=lambda value: hashlib.sha256(value.encode()).hexdigest(),
    )
    if len(blocks) < 20 or len(observations) < 40:
        return {
            "ready": False,
            "status": "insufficient_blocks_or_choices",
            "folds": None,
            "choices": len(observations),
            "price_only_log_loss": None,
            "score_adjusted_log_loss": None,
            "nonprice_information_bits_per_choice": None,
        }
    fold_count = min(folds, len(blocks))
    assignment = {block: index % fold_count for index, block in enumerate(blocks)}
    total_price = 0.0
    total_scored = 0.0
    total = 0
    for fold in range(fold_count):
        train = [row for row in observations if assignment[row["block_id"]] != fold]
        test = [row for row in observations if assignment[row["block_id"]] == fold]
        providers, alpha, _, success = _fit(train, eta=eta, ridge=ridge)
        if not success:
            return {
                "ready": False,
                "status": "optimizer_failed",
                "folds": fold_count,
                "choices": total,
                "price_only_log_loss": None,
                "score_adjusted_log_loss": None,
                "nonprice_information_bits_per_choice": None,
            }
        alpha_map = dict(zip(providers, alpha, strict=True))
        for row in test:
            price_logits = -eta * np.log(row["costs"])
            price_probs = np.exp(price_logits - logsumexp(price_logits))
            score_logits = price_logits + np.asarray(
                [alpha_map.get(provider, 0.0) for provider in row["providers"]]
            )
            score_probs = np.exp(score_logits - logsumexp(score_logits))
            selected = int(row["selected_index"])
            total_price -= math.log(max(float(price_probs[selected]), 1e-15))
            total_scored -= math.log(max(float(score_probs[selected]), 1e-15))
            total += 1
    return {
        "ready": True,
        "status": "ready",
        "folds": fold_count,
        "choices": total,
        "price_only_log_loss": total_price / total,
        "score_adjusted_log_loss": total_scored / total,
        "nonprice_information_bits_per_choice": (total_price - total_scored)
        / total
        / math.log(2),
    }


def _price_only_null(
    observations: Sequence[dict[str, Any]],
    providers: Sequence[str],
    *,
    eta: float,
    draws: int,
    seed: int,
) -> dict[str, Any]:
    if len(observations) < 40 or draws <= 0:
        return {
            "ready": False,
            "status": "insufficient_choices",
            "observed_total_variation": None,
            "monte_carlo_p_value": None,
            "draws": draws,
        }
    locations = {provider: index for index, provider in enumerate(providers)}
    expected = np.zeros(len(providers))
    observed = np.zeros(len(providers))
    simulations = np.zeros((draws, len(providers)), dtype=np.int32)
    draw_indices = np.arange(draws)
    rng = np.random.default_rng(seed)
    for row in observations:
        logits = -eta * np.log(row["costs"])
        probs = np.exp(logits - logsumexp(logits))
        global_indices = np.asarray([locations[p] for p in row["providers"]], dtype=int)
        expected[global_indices] += probs
        observed[global_indices[int(row["selected_index"])]] += 1
        local_draws = rng.choice(len(probs), size=draws, p=probs)
        np.add.at(simulations, (draw_indices, global_indices[local_draws]), 1)
    n = len(observations)
    statistic = 0.5 * float(np.abs(observed / n - expected / n).sum())
    simulated = 0.5 * np.abs(simulations / n - expected[None, :] / n).sum(axis=1)
    p_value = (1 + int((simulated >= statistic).sum())) / (draws + 1)
    return {
        "ready": True,
        "status": "ready",
        "observed_total_variation": statistic,
        "null_total_variation_95_interval": [
            float(value) for value in np.quantile(simulated, [0.025, 0.975])
        ],
        "monte_carlo_p_value": float(p_value),
        "draws": draws,
    }


def _manipulation_panel(
    observations: Sequence[dict[str, Any]],
    providers: Sequence[str],
    alpha: np.ndarray,
    *,
    eta: float,
    benchmark_provider: str,
) -> pd.DataFrame:
    alpha_map = dict(zip(providers, alpha, strict=True))
    rows: dict[str, list[dict[str, float]]] = defaultdict(list)
    for row in observations:
        if benchmark_provider not in row["providers"]:
            continue
        benchmark_index = row["providers"].index(benchmark_provider)
        benchmark_cost = float(row["costs"][benchmark_index])
        local_alpha = np.asarray([alpha_map[provider] for provider in row["providers"]])
        price_logits = -eta * np.log(row["costs"])
        price_probs = np.exp(price_logits - logsumexp(price_logits))
        scored_logits = price_logits + local_alpha
        scored_probs = np.exp(scored_logits - logsumexp(scored_logits))
        for index, provider in enumerate(row["providers"]):
            cost = float(row["costs"][index])
            if provider == benchmark_provider or cost >= benchmark_cost * (1 - 1e-10):
                continue
            counterfactual_costs = row["costs"].copy()
            counterfactual_costs[index] = benchmark_cost
            cf_price_logits = -eta * np.log(counterfactual_costs)
            cf_price = np.exp(cf_price_logits - logsumexp(cf_price_logits))
            cf_scored_logits = cf_price_logits + local_alpha
            cf_scored = np.exp(cf_scored_logits - logsumexp(cf_scored_logits))
            price_gain = float(price_probs[index] - cf_price[index])
            scored_gain = float(scored_probs[index] - cf_scored[index])
            rows[provider].append(
                {
                    "undercut_fraction": 1 - cost / benchmark_cost,
                    "price_only_share": float(price_probs[index]),
                    "score_adjusted_share": float(scored_probs[index]),
                    "price_only_unilateral_gain": price_gain,
                    "score_adjusted_unilateral_gain": scored_gain,
                    "scoring_interaction": scored_gain - price_gain,
                }
            )
    output = []
    for provider, values in sorted(rows.items()):
        frame = pd.DataFrame(values)
        price_gain = float(frame["price_only_unilateral_gain"].mean())
        scored_gain = float(frame["score_adjusted_unilateral_gain"].mean())
        output.append(
            {
                "provider": provider,
                "undercut_opportunities": len(frame),
                "mean_undercut_fraction": float(frame["undercut_fraction"].mean()),
                "mean_price_only_share": float(frame["price_only_share"].mean()),
                "mean_score_adjusted_share": float(frame["score_adjusted_share"].mean()),
                "mean_price_only_unilateral_share_gain": price_gain,
                "mean_score_adjusted_unilateral_share_gain": scored_gain,
                "mean_scoring_interaction_share": scored_gain - price_gain,
                "scoring_attenuation_fraction": (
                    1 - scored_gain / price_gain if abs(price_gain) > 1e-12 else np.nan
                ),
            }
        )
    return pd.DataFrame(output)


def estimate_nonprice_scoring(
    observations: Sequence[dict[str, Any]],
    *,
    eta: float,
    benchmark_provider: str,
    ridge: float = DEFAULT_RIDGE,
    minimum_choices: int = 40,
    minimum_blocks: int = 20,
    minimum_selected_providers: int = 3,
    null_draws: int = DEFAULT_NULL_DRAWS,
    seed: int = 20260721,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    """Estimate relative score wedges and their undercutting interaction."""

    cleaned = _clean(observations)
    blocks = {row["block_id"] for row in cleaned}
    selected_providers = {row["providers"][row["selected_index"]] for row in cleaned}
    failures = []
    if len(cleaned) < minimum_choices:
        failures.append("choices")
    if len(blocks) < minimum_blocks:
        failures.append("blocks")
    if len(selected_providers) < minimum_selected_providers:
        failures.append("selected_providers")
    base = {
        "status": "ready" if not failures else "accruing",
        "support_failures": failures,
        "covered_choices": len(cleaned),
        "blocks": len(blocks),
        "selected_providers": len(selected_providers),
        "eta": eta,
        "ridge": ridge,
        "benchmark_provider": benchmark_provider,
        "estimand": (
            "relative provider fixed effects in choice odds after conditioning on "
            "the frozen public menu and the frozen price exponent"
        ),
        "claim_boundary": (
            "The score wedge is reduced-form. It bundles router scoring, QoS, health, "
            "capacity, eligibility mismatch, and persistent preferences; it is not a "
            "direct measure of quality, intent, or provider manipulation."
        ),
    }
    if failures:
        return base | {
            "fit_ready": False,
            "mean_probability_mass_reallocated_by_scoring": None,
            "cross_validated": _cross_validated_log_loss(cleaned, eta=eta, ridge=ridge),
            "price_only_null": {
                "ready": False,
                "status": "support_gate_failed",
                "observed_total_variation": None,
                "monte_carlo_p_value": None,
                "draws": null_draws,
            },
        }, pd.DataFrame(), pd.DataFrame()

    providers, alpha, designed, success = _fit(cleaned, eta=eta, ridge=ridge)
    if not success:
        return (
            base | {"status": "optimizer_failed", "fit_ready": False},
            pd.DataFrame(),
            pd.DataFrame(),
        )
    covariance = _cluster_covariance(designed, alpha, eta=eta, ridge=ridge)
    locations = {provider: index for index, provider in enumerate(providers)}
    reference = benchmark_provider if benchmark_provider in locations else providers[0]
    reference_index = locations[reference]
    observed = np.zeros(len(providers))
    expected_price = np.zeros(len(providers))
    expected_scored = np.zeros(len(providers))
    appearances = np.zeros(len(providers), dtype=int)
    menu_tv = []
    price_nll = 0.0
    scored_nll = 0.0
    for row in designed:
        indices = row["global_indices"]
        price_logits = -eta * np.log(row["costs"])
        price_probs = np.exp(price_logits - logsumexp(price_logits))
        scored_probs = _probabilities(row, alpha, eta)
        selected = int(row["selected_index"])
        observed[indices[selected]] += 1
        expected_price[indices] += price_probs
        expected_scored[indices] += scored_probs
        appearances[indices] += 1
        menu_tv.append(0.5 * float(np.abs(scored_probs - price_probs).sum()))
        price_nll -= math.log(max(float(price_probs[selected]), 1e-15))
        scored_nll -= math.log(max(float(scored_probs[selected]), 1e-15))

    provider_rows = []
    n = len(designed)
    for index, provider in enumerate(providers):
        difference = float(alpha[index] - alpha[reference_index])
        low = high = None
        if covariance is not None:
            contrast = np.zeros(len(providers))
            contrast[index] = 1
            contrast[reference_index] -= 1
            variance = max(0.0, float(contrast @ covariance @ contrast))
            standard_error = math.sqrt(variance)
            low, high = difference - 1.96 * standard_error, difference + 1.96 * standard_error
        discount = 1 - math.exp(-difference / eta)
        provider_rows.append(
            {
                "provider": provider,
                "reference_provider": reference,
                "menu_appearances": int(appearances[index]),
                "selections": int(observed[index]),
                "realized_share": float(observed[index] / n),
                "price_only_expected_share": float(expected_price[index] / n),
                "score_adjusted_expected_share": float(expected_scored[index] / n),
                "realized_to_price_expected_ratio": (
                    float(observed[index] / expected_price[index])
                    if expected_price[index] > 0
                    else np.nan
                ),
                "relative_log_score": difference,
                "relative_log_score_ci_low": low,
                "relative_log_score_ci_high": high,
                "odds_multiplier_vs_reference": math.exp(difference),
                "odds_multiplier_ci_low": math.exp(low) if low is not None else None,
                "odds_multiplier_ci_high": math.exp(high) if high is not None else None,
                "price_equivalent_discount_vs_reference": discount,
                "price_equivalent_discount_ci_low": (
                    1 - math.exp(-low / eta) if low is not None else None
                ),
                "price_equivalent_discount_ci_high": (
                    1 - math.exp(-high / eta) if high is not None else None
                ),
                "score_probability_shift": float(
                    (expected_scored[index] - expected_price[index]) / n
                ),
                "stable_provider_support": bool(
                    appearances[index] >= 20
                    and (observed[index] >= 5 or expected_price[index] >= 5)
                ),
            }
        )
    provider_panel = pd.DataFrame(provider_rows).sort_values(
        ["stable_provider_support", "relative_log_score"], ascending=[False, False]
    )
    manipulation = _manipulation_panel(
        designed,
        providers,
        alpha,
        eta=eta,
        benchmark_provider=benchmark_provider,
    )
    cv = _cross_validated_log_loss(cleaned, eta=eta, ridge=ridge)
    null = _price_only_null(
        cleaned,
        providers,
        eta=eta,
        draws=null_draws,
        seed=seed,
    )
    summary = base | {
        "fit_ready": True,
        "reference_provider": reference,
        "candidate_providers": len(providers),
        "price_only_in_sample_log_loss": price_nll / n,
        "score_adjusted_in_sample_log_loss": scored_nll / n,
        "in_sample_nonprice_information_bits_per_choice": (price_nll - scored_nll)
        / n
        / math.log(2),
        "mean_probability_mass_reallocated_by_scoring": float(np.mean(menu_tv)),
        "cross_validated": cv,
        "price_only_null": null,
        "interaction_interpretation": (
            "Negative mean_scoring_interaction_share means the fitted score attenuates "
            "the unilateral routing-share gain from undercutting the benchmark; positive "
            "means it amplifies that gain. Provider counterfactuals are one-at-a-time and "
            "are not additive when several providers undercut simultaneously."
        ),
    }
    return summary, provider_panel.reset_index(drop=True), manipulation


def price_sort_rule_contrast(
    observations: Sequence[dict[str, Any]],
    *,
    minimum_blocks: int = 20,
    draws: int = 5_000,
    seed: int = 20260722,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Within-block contrast of default routing and explicit price sorting."""

    rows = []
    for row in observations:
        if row.get("policy") not in {"default_broad", "price_sorted"}:
            continue
        providers = row.get("providers") or []
        raw_costs = row.get("costs")
        costs = np.asarray([] if raw_costs is None else raw_costs, dtype=float)
        selected = row.get("selected_index")
        covered = selected is not None and len(providers) == len(costs) and len(costs) > 0
        cheapest = False
        if covered:
            selected = int(selected)
            cheapest = bool(costs[selected] <= costs.min() * (1 + 1e-10))
        rows.append(
            {
                "block_id": str(row.get("block_id") or ""),
                "task_id": row.get("task_id"),
                "policy": row.get("policy"),
                "covered": bool(covered),
                "selected_provider": (
                    providers[int(selected)] if covered else row.get("selected_provider")
                ),
                "selected_cheapest": cheapest if covered else np.nan,
            }
        )
    panel = pd.DataFrame(
        rows,
        columns=[
            "block_id",
            "task_id",
            "policy",
            "covered",
            "selected_provider",
            "selected_cheapest",
        ],
    )
    covered = panel[panel["covered"]] if not panel.empty else panel
    default = covered[covered["policy"] == "default_broad"]
    sorted_arm = covered[covered["policy"] == "price_sorted"]
    complete_blocks = sorted(
        set(default["block_id"]).intersection(set(sorted_arm["block_id"]))
    )
    default_rate = float(default["selected_cheapest"].mean()) if len(default) else None
    sorted_rate = float(sorted_arm["selected_cheapest"].mean()) if len(sorted_arm) else None
    difference = (
        sorted_rate - default_rate if sorted_rate is not None and default_rate is not None else None
    )
    interval = None
    if len(complete_blocks) >= 2 and draws > 0:
        rng = np.random.default_rng(seed)
        effects = []
        for _ in range(draws):
            sampled = rng.choice(complete_blocks, size=len(complete_blocks), replace=True)
            default_values = []
            sorted_values = []
            for block in sampled:
                default_values.extend(
                    default.loc[default["block_id"] == block, "selected_cheapest"].astype(float)
                )
                sorted_values.extend(
                    sorted_arm.loc[
                        sorted_arm["block_id"] == block, "selected_cheapest"
                    ].astype(float)
                )
            effects.append(float(np.mean(sorted_values) - np.mean(default_values)))
        interval = [float(value) for value in np.quantile(effects, [0.025, 0.975])]
    summary = {
        "status": "ready" if len(complete_blocks) >= minimum_blocks else "accruing",
        "complete_blocks": len(complete_blocks),
        "default_covered_choices": len(default),
        "price_sorted_covered_choices": len(sorted_arm),
        "default_cheapest_selection_rate": default_rate,
        "price_sorted_cheapest_selection_rate": sorted_rate,
        "price_sorted_minus_default_cheapest_rate": difference,
        "block_bootstrap_95ci": interval,
        "estimand": (
            "owned-request effect of explicitly requesting price sorting rather than "
            "default broad routing, conditional on complete frozen-menu blocks"
        ),
        "claim_boundary": (
            "This rule contrast does not reveal the router's proprietary score or "
            "market-wide behavior and assumes no cross-task carryover within a block."
        ),
    }
    return summary, panel
