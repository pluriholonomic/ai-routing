"""WCV6 — unilateral provider revenue-gap and router-revenue identification audit.

The provider exercise combines public provider/model/day token shares with a
posted completion-price proxy. For one provider at a time it holds rivals'
prices fixed, moves the provider's price over a registered grid, and lets both
its routed share and aggregate market demand respond. This is a local gross-
revenue proxy, not observed billing, profit, a simultaneous equilibrium, or
social welfare.

Router revenue is not point identified because the repository does not observe
the applicable take rate, end-user price schedule, or a causal demand curve.
The module reports only the local elasticity implication under a constant take
rate; the take rate cancels from that elasticity.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.special import expit

from .bm_common import load_gates
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes, demand_shares


def counterfactual_revenue_ratio(
    *,
    price: float,
    share: float,
    competitor_price: float,
    price_multiple: np.ndarray | float,
    routing_elasticity: float,
    demand_elasticity: float,
) -> np.ndarray:
    """Gross-revenue proxy relative to the observed price/share point.

    The H4 input is a *share* elasticity. To extend that local estimate into a
    bounded logit counterfactual, the latent own-weight elasticity is therefore
    ``routing_elasticity / (1 - share)``. This makes the derivative of log share
    with respect to log price at ``m = 1`` equal the supplied H4 estimate.
    Rival weights and prices are held fixed. Total market demand responds to
    the resulting share-weighted price index with ``demand_elasticity``.
    """
    values = {
        "price": price,
        "share": share,
        "competitor_price": competitor_price,
        "routing_elasticity": routing_elasticity,
        "demand_elasticity": demand_elasticity,
    }
    if any(not np.isfinite(float(value)) for value in values.values()):
        raise ValueError("counterfactual inputs must be finite")
    if price <= 0 or competitor_price <= 0:
        raise ValueError("prices must be positive")
    if not 0 < share < 1:
        raise ValueError("share must lie strictly between zero and one")
    multiples = np.asarray(price_multiple, dtype=float)
    if np.any(~np.isfinite(multiples)) or np.any(multiples <= 0):
        raise ValueError("price multiples must be finite and positive")

    latent_weight_elasticity = routing_elasticity / (1.0 - share)
    counterfactual_log_odds = np.log(share / (1.0 - share)) + latent_weight_elasticity * np.log(
        multiples
    )
    counterfactual_share = expit(counterfactual_log_odds)
    observed_index = share * price + (1.0 - share) * competitor_price
    counterfactual_index = (
        counterfactual_share * price * multiples + (1.0 - counterfactual_share) * competitor_price
    )
    demand_ratio = np.power(counterfactual_index / observed_index, demand_elasticity)
    return multiples * (counterfactual_share / share) * demand_ratio


def optimize_provider_revenue(
    *,
    price: float,
    share: float,
    competitor_price: float,
    routing_elasticity: float,
    demand_elasticity: float,
    price_multiples: np.ndarray,
) -> dict[str, float | bool | str]:
    """Return the best bounded unilateral price deviation and its revenue gap."""
    ratios = counterfactual_revenue_ratio(
        price=price,
        share=share,
        competitor_price=competitor_price,
        price_multiple=price_multiples,
        routing_elasticity=routing_elasticity,
        demand_elasticity=demand_elasticity,
    )
    best_index = int(np.nanargmax(ratios))
    best_multiple = float(price_multiples[best_index])
    best_ratio = max(1.0, float(ratios[best_index]))
    lower = bool(best_index == 0)
    upper = bool(best_index == len(price_multiples) - 1)
    if lower:
        direction = "lower_boundary"
    elif upper:
        direction = "upper_boundary"
    elif best_multiple < 1.0 - 1e-9:
        direction = "lower_price"
    elif best_multiple > 1.0 + 1e-9:
        direction = "raise_price"
    else:
        direction = "observed_price"

    delta = 1e-4
    local = counterfactual_revenue_ratio(
        price=price,
        share=share,
        competitor_price=competitor_price,
        price_multiple=np.array([np.exp(-delta), np.exp(delta)]),
        routing_elasticity=routing_elasticity,
        demand_elasticity=demand_elasticity,
    )
    safe_local = np.clip(local, np.finfo(float).tiny, None)
    local_elasticity = float((np.log(safe_local[1]) - np.log(safe_local[0])) / (2.0 * delta))
    return {
        "revenue_maximizing_price_multiple_within_grid": best_multiple,
        "best_revenue_ratio_within_grid": best_ratio,
        "revenue_gap_share_within_grid": 1.0 - 1.0 / best_ratio,
        "normalized_revenue_regret": best_ratio - 1.0,
        "local_revenue_elasticity": local_elasticity,
        "optimum_at_grid_boundary": lower or upper,
        "deviation_direction": direction,
    }


def _elasticity_scenarios(out_dir: Path, fallback: float) -> list[dict[str, float | str]]:
    try:
        summary = json.loads((out_dir / "h4_summary.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        summary = {}
    beta = float(summary.get("share_price_elasticity", fallback))
    se = summary.get("se")
    scenarios: list[dict[str, float | str]] = [{"name": "h4_point", "value": beta}]
    if se is not None and np.isfinite(float(se)):
        scenarios.extend(
            [
                {"name": "h4_ci_more_elastic", "value": beta - 1.96 * float(se)},
                {"name": "h4_ci_less_elastic", "value": beta + 1.96 * float(se)},
            ]
        )
    robust = summary.get("elasticity_dropping_sub1pct_shares")
    if robust is not None and np.isfinite(float(robust)):
        scenarios.append({"name": "h4_drop_sub1pct", "value": float(robust)})
    return scenarios


def _analysis_panel() -> pd.DataFrame:
    quotes = daily_quotes()
    shares = demand_shares()
    panel = shares.merge(quotes, on=["dt", "model_id", "provider_name"], how="inner")
    panel["tokens"] = pd.to_numeric(panel["tokens"], errors="coerce")
    panel["price"] = pd.to_numeric(panel["price"], errors="coerce")
    panel = panel[(panel["tokens"] > 0) & (panel["price"] > 0)].copy()
    panel["market_tokens"] = panel.groupby(["dt", "model_id"])["tokens"].transform("sum")
    panel["share"] = panel["tokens"] / panel["market_tokens"]
    panel["weighted_price_tokens"] = panel["price"] * panel["tokens"]
    panel["market_price_index"] = (
        panel.groupby(["dt", "model_id"])["weighted_price_tokens"].transform("sum")
        / panel["market_tokens"]
    )
    numerator = panel["market_price_index"] - panel["share"] * panel["price"]
    panel["competitor_price_index"] = numerator / (1.0 - panel["share"])
    panel = panel[
        (panel["share"] > 0) & (panel["share"] < 1) & (panel["competitor_price_index"] > 0)
    ].copy()
    panel["observed_completion_revenue_proxy"] = panel["price"] * panel["tokens"]
    return panel.reset_index(drop=True)


def _bootstrap_capture_ratio(
    frame: pd.DataFrame, *, draws: int, seed: int
) -> tuple[float | None, float | None]:
    if frame.empty or draws <= 0:
        return None, None
    working = frame.assign(
        weighted_capture_numerator=frame["observed_completion_revenue_proxy"]
        / frame["best_revenue_ratio_within_grid"]
    )
    by_day = working.groupby("dt", as_index=False).agg(
        observed=("observed_completion_revenue_proxy", "sum"),
        weighted_capture_numerator=("weighted_capture_numerator", "sum"),
    )
    if len(by_day) < 2:
        return None, None
    rng = np.random.default_rng(seed)
    values = np.empty(draws, dtype=float)
    for draw in range(draws):
        sample = by_day.iloc[rng.integers(0, len(by_day), size=len(by_day))]
        values[draw] = float(sample["weighted_capture_numerator"].sum() / sample["observed"].sum())
    low, high = np.quantile(values, [0.025, 0.975])
    return float(low), float(high)


def _scenario_summary(frame: pd.DataFrame, *, draws: int, seed: int) -> dict[str, Any]:
    observed = float(frame["observed_completion_revenue_proxy"].sum())
    best = float(frame["best_completion_revenue_proxy"].sum())
    pooled_capture = observed / best if best > 0 else np.nan
    weighted_capture = float(
        np.average(
            1.0 / frame["best_revenue_ratio_within_grid"],
            weights=frame["observed_completion_revenue_proxy"],
        )
    )
    low, high = _bootstrap_capture_ratio(frame, draws=draws, seed=seed)
    return {
        "provider_market_days": int(len(frame)),
        "market_days": int(frame[["dt", "model_id"]].drop_duplicates().shape[0]),
        "providers": int(frame["provider_name"].nunique()),
        "median_revenue_gap_pct": float(100 * frame["revenue_gap_share_within_grid"].median()),
        "observed_proxy_weighted_revenue_capture_ratio": weighted_capture,
        "observed_proxy_weighted_revenue_gap_pct": float(100 * (1.0 - weighted_capture)),
        "weighted_capture_ratio_day_bootstrap_ci95": [low, high],
        "pooled_unilateral_capture_ratio": float(pooled_capture),
        "pooled_unilateral_gap_pct": float(100 * (1.0 - pooled_capture)),
        "share_within_5pct_of_grid_optimum": float(
            (frame["revenue_gap_share_within_grid"] <= 0.05).mean()
        ),
        "share_optimum_at_grid_boundary": float(frame["optimum_at_grid_boundary"].mean()),
        "share_with_raise_price_direction": float(
            frame["deviation_direction"].isin(["raise_price", "upper_boundary"]).mean()
        ),
        "share_with_lower_price_direction": float(
            frame["deviation_direction"].isin(["lower_price", "lower_boundary"]).mean()
        ),
        "median_local_revenue_elasticity": float(frame["local_revenue_elasticity"].median()),
        "median_optimal_price_multiple_within_grid": float(
            frame["revenue_maximizing_price_multiple_within_grid"].median()
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    config = load_gates()
    revenue_config = config["revenue_gap"]
    multiples = np.geomspace(
        float(revenue_config["price_multiple_min"]),
        float(revenue_config["price_multiple_max"]),
        int(revenue_config["grid_points"]),
    )
    panel = _analysis_panel()
    routing_scenarios = _elasticity_scenarios(
        out_dir, float(config["counterfactual"]["routing_elasticity"])
    )
    demand_scenarios = [float(value) for value in config["counterfactual"]["end_user_elasticities"]]
    rows: list[dict[str, Any]] = []
    for routing in routing_scenarios:
        for demand_elasticity in demand_scenarios:
            for row in panel.itertuples(index=False):
                result = optimize_provider_revenue(
                    price=float(row.price),
                    share=float(row.share),
                    competitor_price=float(row.competitor_price_index),
                    routing_elasticity=float(routing["value"]),
                    demand_elasticity=demand_elasticity,
                    price_multiples=multiples,
                )
                observed = float(row.observed_completion_revenue_proxy)
                rows.append(
                    {
                        "dt": row.dt,
                        "model_id": row.model_id,
                        "provider_name": row.provider_name,
                        "price": float(row.price),
                        "tokens": float(row.tokens),
                        "share": float(row.share),
                        "market_tokens": float(row.market_tokens),
                        "market_price_index": float(row.market_price_index),
                        "competitor_price_index": float(row.competitor_price_index),
                        "routing_elasticity_scenario": str(routing["name"]),
                        "routing_elasticity": float(routing["value"]),
                        "demand_elasticity": demand_elasticity,
                        "observed_completion_revenue_proxy": observed,
                        "best_completion_revenue_proxy": observed
                        * float(result["best_revenue_ratio_within_grid"]),
                        **result,
                    }
                )
    results = pd.DataFrame(rows)
    save(results, out_dir, "wcv6_provider_revenue_gap")

    summaries = []
    for index, ((routing_name, demand_elasticity), group) in enumerate(
        results.groupby(["routing_elasticity_scenario", "demand_elasticity"], sort=True)
    ):
        summaries.append(
            {
                "routing_elasticity_scenario": routing_name,
                "routing_elasticity": float(group["routing_elasticity"].iat[0]),
                "demand_elasticity": float(demand_elasticity),
                **_scenario_summary(
                    group,
                    draws=int(revenue_config["bootstrap_draws"]),
                    seed=int(revenue_config["seed"]) + index,
                ),
            }
        )
    scenario_panel = pd.DataFrame(summaries)
    save(scenario_panel, out_dir, "wcv6_revenue_gap_scenarios")

    point = results[results["routing_elasticity_scenario"].eq("h4_point")].copy()
    provider_panel = point.groupby(["provider_name", "demand_elasticity"], as_index=False).agg(
        provider_market_days=("model_id", "size"),
        models=("model_id", "nunique"),
        observed_completion_revenue_proxy=("observed_completion_revenue_proxy", "sum"),
        best_completion_revenue_proxy=("best_completion_revenue_proxy", "sum"),
        median_revenue_gap_share=("revenue_gap_share_within_grid", "median"),
        median_optimal_price_multiple=(
            "revenue_maximizing_price_multiple_within_grid",
            "median",
        ),
        boundary_share=("optimum_at_grid_boundary", "mean"),
    )
    provider_panel["pooled_unilateral_capture_ratio"] = (
        provider_panel["observed_completion_revenue_proxy"]
        / provider_panel["best_completion_revenue_proxy"]
    )
    provider_panel = provider_panel.sort_values(
        ["demand_elasticity", "pooled_unilateral_capture_ratio", "provider_market_days"],
        ascending=[True, False, False],
    )
    save(provider_panel, out_dir, "wcv6_provider_revenue_scorecard")
    point_summary = scenario_panel[
        scenario_panel["routing_elasticity_scenario"].eq("h4_point")
    ].to_dict("records")
    h4_uncertainty = scenario_panel[
        scenario_panel["routing_elasticity_scenario"].isin(
            ["h4_point", "h4_ci_more_elastic", "h4_ci_less_elastic"]
        )
    ]
    bootstrap_lows = h4_uncertainty["weighted_capture_ratio_day_bootstrap_ci95"].map(
        lambda interval: interval[0]
    )
    bootstrap_highs = h4_uncertainty["weighted_capture_ratio_day_bootstrap_ci95"].map(
        lambda interval: interval[1]
    )
    summary: dict[str, Any] = {
        "evidence_status": "bounded_revenue_proxy_sensitivity" if len(results) else "not_estimated",
        "price_multiple_grid": [
            float(revenue_config["price_multiple_min"]),
            float(revenue_config["price_multiple_max"]),
        ],
        "routing_elasticity_scenarios": routing_scenarios,
        "demand_elasticity_scenarios": demand_scenarios,
        "point_estimate_scenarios": point_summary,
        "conditional_elasticity_uncertainty_envelope": {
            "weighted_revenue_gap_pct_range": [
                float(h4_uncertainty["observed_proxy_weighted_revenue_gap_pct"].min()),
                float(h4_uncertainty["observed_proxy_weighted_revenue_gap_pct"].max()),
            ],
            "day_bootstrap_and_elasticity_endpoint_gap_pct_range": [
                float(100.0 * (1.0 - bootstrap_highs.max())),
                float(100.0 * (1.0 - bootstrap_lows.min())),
            ],
            "interpretation": (
                "This envelope combines the H4 point and clustered 95% endpoints with the "
                "registered demand-elasticity scenarios. It remains conditional on H4 being a "
                "causal own-price response and on the bounded logit counterfactual."
            ),
        },
        "all_scenarios": scenario_panel.to_dict("records"),
        "router_revenue_identification": {
            "status": "not_point_identified",
            "constant_take_rate_local_revenue_elasticities": [
                1.0 + value for value in demand_scenarios
            ],
            "reason": (
                "The applicable take rate, end-user price schedule, and causal demand curve are "
                "not observed. Under a constant take rate and the scenario demand elasticities, "
                "router revenue is locally increasing in a common price multiplier, so no "
                "finite revenue-maximizing price or distance is identified."
            ),
        },
        "claim_boundary": (
            "Each row is a bounded unilateral deviation around an observed public token share and "
            "posted completion-price proxy. It is not observed provider billing, profit, a causal "
            "demand curve, or a simultaneous equilibrium. Individual best-response revenue gains "
            "cannot be summed as an attainable market-wide revenue gain. Boundary optima mean the "
            "distance is unidentified beyond the registered grid."
        ),
    }
    save_json(summary, out_dir, "wcv6_summary")
    return summary
