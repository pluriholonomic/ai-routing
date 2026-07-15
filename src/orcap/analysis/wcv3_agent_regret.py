"""WCV3 — calibrated one-shot provider and user regret screens."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .bm_common import load_gates
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes, demand_shares


def provider_best_response(
    price: float,
    share: float,
    cost: float,
    elasticity: float,
    grid: np.ndarray | None = None,
) -> dict:
    """Best response under a local isoelastic allocation calibration."""
    multiples = grid if grid is not None else np.geomspace(0.25, 4.0, 161)
    candidate_price = price * multiples
    own_weight = share * np.power(candidate_price / price, elasticity)
    candidate_share = own_weight / (own_weight + 1 - share)
    profit = candidate_share * (candidate_price - cost)
    actual_profit = share * (price - cost)
    index = int(np.nanargmax(profit))
    best = float(profit[index])
    return {
        "best_price": float(candidate_price[index]),
        "best_share": float(candidate_share[index]),
        "actual_profit_index": float(actual_profit),
        "best_profit_index": best,
        "normalized_regret": float(max(best - actual_profit, 0) / max(abs(actual_profit), 1e-12)),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    quotes = daily_quotes()
    shares = demand_shares()
    panel = shares.merge(quotes, on=["dt", "model_id", "provider_name"], how="inner")
    panel = panel[(panel["tokens"] > 0) & (panel["price"] > 0)].copy()
    panel["share"] = panel["tokens"] / panel.groupby(["dt", "model_id"])["tokens"].transform(
        "sum"
    )
    config = load_gates()
    elasticity = float(config["counterfactual"]["routing_elasticity"])
    provider_rows = []
    for row in panel.itertuples(index=False):
        if not 0 < row.share < 1:
            continue
        for cost_ratio in config["counterfactual"]["cost_ratios"]:
            result = provider_best_response(
                float(row.price),
                float(row.share),
                float(cost_ratio * row.price),
                elasticity,
            )
            provider_rows.append(
                {
                    "dt": row.dt,
                    "model_id": row.model_id,
                    "provider_name": row.provider_name,
                    "share": row.share,
                    "price": row.price,
                    "cost_ratio": cost_ratio,
                    **result,
                }
            )
    provider_regret = pd.DataFrame(provider_rows)
    save(provider_regret, out_dir, "wcv3_provider_regret")

    user_rows = []
    for (dt, model), group in panel.groupby(["dt", "model_id"]):
        if len(group) < 2:
            continue
        weighted = float(np.dot(group["share"], group["price"]))
        cheapest = float(group["price"].min())
        user_rows.append(
            {
                "dt": dt,
                "model_id": model,
                "n_providers": int(len(group)),
                "weighted_price": weighted,
                "cheapest_price": cheapest,
                "price_only_regret_pct": 100 * (weighted / cheapest - 1),
                "tokens": float(group["tokens"].sum()),
            }
        )
    user_regret = pd.DataFrame(user_rows)
    save(user_regret, out_dir, "wcv3_user_regret")
    threshold = float(config["equivalence"]["max_normalized_agent_regret"])
    median_regret = (
        float(provider_regret["normalized_regret"].median()) if len(provider_regret) else None
    )
    summary = {
        "evidence_status": "calibrated_regret_screen" if len(provider_regret) else "not_estimated",
        "n_provider_scenarios": int(len(provider_regret)),
        "n_user_market_days": int(len(user_regret)),
        "median_provider_normalized_regret": median_regret,
        "share_provider_scenarios_below_5pct_regret": (
            float((provider_regret["normalized_regret"] <= threshold).mean())
            if len(provider_regret)
            else None
        ),
        "token_weighted_user_price_only_regret_pct": (
            float(np.average(user_regret["price_only_regret_pct"], weights=user_regret["tokens"]))
            if len(user_regret)
            else None
        ),
        "router_regret": "not_identified_without_router_objective_and_propensities",
        "harness_regret": "not_identified_without_retry_policy_and_user retention",
        "claim_boundary": (
            "Provider regret uses a locally calibrated isoelastic share rule and scenario costs; "
            "it is not revealed profit regret. User regret is price-only and deliberately ignores "
            "quality, latency, availability, and private discounts."
        ),
    }
    save_json(summary, out_dir, "wcv3_summary")
    return summary
