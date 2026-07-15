"""WCV2 — transparent cadence-neutral price/allocation sensitivity bounds."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .bm_common import load_gates
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes, demand_shares


def cadence_neutral_market(
    market: pd.DataFrame,
    beta_fast: float,
    routing_elasticity: float,
    demand_elasticity: float,
    cost_ratio: float,
) -> dict:
    """One market-day partial-equilibrium sensitivity calculation."""
    frame = market.copy()
    shares = frame["tokens"].to_numpy(float)
    shares = shares / shares.sum()
    price = frame["price"].to_numpy(float)
    is_fast = frame["is_fast"].to_numpy(bool)
    counterfactual_price = np.where(is_fast, price, price * np.exp(beta_fast))
    weights = shares * np.power(counterfactual_price / price, routing_elasticity)
    counterfactual_share = weights / weights.sum()
    actual_index = float(np.dot(shares, price))
    counterfactual_index = float(np.dot(counterfactual_share, counterfactual_price))
    demand_ratio = float((counterfactual_index / actual_index) ** demand_elasticity)
    total_tokens = float(frame["tokens"].sum())
    actual_spend = total_tokens * actual_index
    counterfactual_spend = total_tokens * demand_ratio * counterfactual_index
    cost = cost_ratio * price
    actual_surplus = float(total_tokens * np.dot(shares, price - cost))
    counterfactual_surplus = float(
        total_tokens
        * demand_ratio
        * np.dot(counterfactual_share, counterfactual_price - cost)
    )
    return {
        "actual_weighted_price": actual_index,
        "counterfactual_weighted_price": counterfactual_index,
        "price_change_pct": 100 * (counterfactual_index / actual_index - 1),
        "demand_change_pct": 100 * (demand_ratio - 1),
        "spend_change_pct": 100 * (counterfactual_spend / actual_spend - 1),
        "provider_surplus_change_pct": (
            100 * (counterfactual_surplus / actual_surplus - 1) if actual_surplus > 0 else np.nan
        ),
        "tokens": total_tokens,
    }


def _read_betas(out_dir: Path) -> list[dict]:
    try:
        summary = json.loads((out_dir / "bm3_summary.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    adjusted = summary.get("quality_adjusted", {})
    basic = summary.get("cadence_only", {})
    estimates = []
    for source, result in (("cadence_only", basic), ("quality_adjusted", adjusted)):
        if "beta_fast" in result:
            estimates.append(
                {"beta": result["beta_fast"], "ci95": result.get("ci95"), "source": source}
            )
    return estimates


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    beta_estimates = _read_betas(out_dir)
    if not beta_estimates:
        summary = {"evidence_status": "not_estimated", "error": "BM3 cadence coefficient missing"}
        save(pd.DataFrame(), out_dir, "wcv2_welfare_scenarios")
        save_json(summary, out_dir, "wcv2_summary")
        return summary
    cadence = pd.read_parquet(out_dir / "bm1_provider_cadence.parquet")
    quotes = daily_quotes().merge(
        cadence[["provider_name", "is_fast"]], on="provider_name", how="inner"
    )
    shares = demand_shares()
    panel = shares.merge(
        quotes[["dt", "model_id", "provider_name", "price", "is_fast"]],
        on=["dt", "model_id", "provider_name"],
        how="inner",
    )
    panel = panel[(panel["tokens"] > 0) & (panel["price"] > 0)]
    gates = load_gates()["counterfactual"]
    rows = []
    for beta_info in beta_estimates:
        beta = float(beta_info["beta"])
        for demand_elasticity in gates["end_user_elasticities"]:
            for cost_ratio in gates["cost_ratios"]:
                markets = []
                for (dt, model), group in panel.groupby(["dt", "model_id"]):
                    if len(group) < 2 or group["is_fast"].nunique() < 2:
                        continue
                    result = cadence_neutral_market(
                        group,
                        beta,
                        float(gates["routing_elasticity"]),
                        float(demand_elasticity),
                        float(cost_ratio),
                    )
                    markets.append(result | {"dt": dt, "model_id": model})
                if not markets:
                    continue
                market_frame = pd.DataFrame(markets)
                weight = market_frame["tokens"] / market_frame["tokens"].sum()
                rows.append(
                    {
                        "beta_source": beta_info["source"],
                        "demand_elasticity": demand_elasticity,
                        "cost_ratio": cost_ratio,
                        "routing_elasticity": gates["routing_elasticity"],
                        "beta_fast": beta,
                        "n_market_days": int(len(market_frame)),
                        **{
                            key: float(np.dot(weight, market_frame[key]))
                            for key in [
                                "price_change_pct",
                                "demand_change_pct",
                                "spend_change_pct",
                                "provider_surplus_change_pct",
                            ]
                        },
                    }
                )
    scenarios = pd.DataFrame(rows)
    save(scenarios, out_dir, "wcv2_welfare_scenarios")
    summary = {
        "evidence_status": "sensitivity_analysis" if len(scenarios) else "not_estimated",
        "n_matched_provider_days": int(len(panel)),
        "n_scenarios": int(len(scenarios)),
        "beta_estimates": beta_estimates,
        "scenarios": scenarios.to_dict("records"),
        "claim_boundary": (
            "This is a transparent partial-equilibrium sensitivity bound, not structural Bertrand "
            "estimation or social welfare. Costs are scenario ratios, user value and quality "
            "losses "
            "are absent, and the BM coefficient is observational."
        ),
    }
    save_json(summary, out_dir, "wcv2_summary")
    return summary
