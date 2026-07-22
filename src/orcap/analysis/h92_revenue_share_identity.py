"""H92 — accounting decomposition of apparent unit routing elasticity.

For provider quantity q, price p, quantity share s=q/sum(q), and public
revenue-proxy share e=pq/sum(pq),

    log(s) = log(e) - log(p) + log(sum(pq)/sum(q)).

The final term is constant within a model-day-variant market. Consequently, in
any common weighted regression with market fixed effects and the same controls,
the price coefficient for log quantity share is exactly the price coefficient
for log revenue-proxy share minus one. A share coefficient near -1 is therefore
equivalent to revenue-proxy shares being locally uncorrelated with price in that
cross-section; it is not by itself a residual-demand derivative or a provider
first-order condition.

H92 verifies the identity numerically, estimates both sides with H4's exact
weights and cache control, tests daily stability, and permutes price labels
within markets to reject chance price/quantity matching. It also translates
H91's within/between quantity-share coefficients into revenue-share slopes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm

from .bm_common import load_gates
from .common import DEFAULT_OUT, save, save_json
from .h4_routing import load_shares


def build_identity_panel(frame: pd.DataFrame) -> pd.DataFrame:
    """Construct quantity and revenue-proxy shares plus the exact residual."""
    required = {
        "group",
        "dt",
        "provider_slug",
        "share",
        "total_tokens",
        "effective_output_price",
        "cache_hit_rate",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"identity panel missing columns: {sorted(missing)}")
    panel = frame.copy()
    for column in ["share", "total_tokens", "effective_output_price"]:
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
    panel = panel[
        (panel["share"] > 0)
        & (panel["share"] < 1)
        & (panel["total_tokens"] > 0)
        & (panel["effective_output_price"] > 0)
    ].copy()
    panel["revenue_proxy"] = panel["effective_output_price"] * panel["total_tokens"]
    panel["market_revenue_proxy"] = panel.groupby("group")["revenue_proxy"].transform("sum")
    panel["market_tokens"] = panel.groupby("group")["total_tokens"].transform("sum")
    panel["revenue_proxy_share"] = panel["revenue_proxy"] / panel["market_revenue_proxy"]
    panel["market_price_index"] = panel["market_revenue_proxy"] / panel["market_tokens"]
    panel["log_share"] = np.log(panel["share"])
    panel["log_revenue_proxy_share"] = np.log(panel["revenue_proxy_share"])
    panel["log_price"] = np.log(panel["effective_output_price"])
    panel["log_market_price_index"] = np.log(panel["market_price_index"])
    panel["cache"] = pd.to_numeric(panel["cache_hit_rate"], errors="coerce").fillna(0.0)
    panel["identity_residual"] = panel["log_share"] - (
        panel["log_revenue_proxy_share"]
        - panel["log_price"]
        + panel["log_market_price_index"]
    )
    return panel.reset_index(drop=True)


def _fit_market_fe(frame: pd.DataFrame, outcome: str) -> dict[str, Any]:
    columns = [outcome, "log_price", "cache", "group"]
    panel = frame[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()
    for column in [outcome, "log_price", "cache"]:
        panel[f"{column}_dm"] = panel[column] - panel.groupby("group")[column].transform("mean")
    panel["group_weight"] = 1.0 / panel.groupby("group")["group"].transform("size")
    model = sm.WLS(
        panel[f"{outcome}_dm"],
        panel[["log_price_dm", "cache_dm"]],
        weights=panel["group_weight"],
    ).fit(cov_type="cluster", cov_kwds={"groups": panel["group"]})
    beta = float(model.params["log_price_dm"])
    se = float(model.bse["log_price_dm"])
    return {
        "coefficient": beta,
        "standard_error": se,
        "ci95": [beta - 1.96 * se, beta + 1.96 * se],
        "p_value_zero": float(2.0 * norm.sf(abs(beta / se))),
        "n_observations": int(model.nobs),
        "n_groups": int(panel["group"].nunique()),
    }


def _equivalence_zero(
    coefficient: float, standard_error: float, *, margin: float, alpha: float
) -> dict[str, Any]:
    p_above_lower = float(norm.sf((coefficient + margin) / standard_error))
    p_below_upper = float(norm.cdf((coefficient - margin) / standard_error))
    p_value = max(p_above_lower, p_below_upper)
    return {
        "equivalence_target": 0.0,
        "equivalence_margin": margin,
        "equivalence_p": p_value,
        "equivalent_to_zero": bool(p_value < alpha),
    }


def _weighted_slope(y: np.ndarray, x: np.ndarray, z: np.ndarray, weights: np.ndarray) -> float:
    design = np.column_stack([x, z])
    cross = design.T @ (weights[:, None] * design)
    moment = design.T @ (weights * y)
    return float(np.linalg.lstsq(cross, moment, rcond=None)[0][0])


def price_label_permutation(
    frame: pd.DataFrame, *, draws: int, seed: int
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Shuffle price labels within markets, holding provider quantities fixed."""
    panel = frame[["group", "log_share", "log_price", "cache"]].copy()
    for column in ["log_share", "log_price", "cache"]:
        panel[f"{column}_dm"] = panel[column] - panel.groupby("group")[column].transform("mean")
    weights = (1.0 / panel.groupby("group")["group"].transform("size")).to_numpy(float)
    y = panel["log_share_dm"].to_numpy(float)
    x = panel["log_price_dm"].to_numpy(float)
    z = panel["cache_dm"].to_numpy(float)
    observed = _weighted_slope(y, x, z, weights)
    group_indices = [indices.to_numpy() for _, indices in panel.groupby("group").groups.items()]
    rng = np.random.default_rng(seed)
    rows = []
    for draw in range(draws):
        permuted = x.copy()
        for indices in group_indices:
            permuted[indices] = rng.permutation(permuted[indices])
        share_slope = _weighted_slope(y, permuted, z, weights)
        rows.append(
            {
                "draw": draw,
                "quantity_share_price_coefficient": share_slope,
                "revenue_share_price_coefficient": share_slope + 1.0,
            }
        )
    null = pd.DataFrame(rows)
    return null, {
        "draws": draws,
        "seed": seed,
        "observed_quantity_share_price_coefficient": observed,
        "one_sided_p_quantity_slope_at_most_observed": float(
            (1 + (null["quantity_share_price_coefficient"] <= observed).sum()) / (draws + 1)
        ),
        "quantity_slope_null_ci95": [
            float(null["quantity_share_price_coefficient"].quantile(0.025)),
            float(null["quantity_share_price_coefficient"].quantile(0.975)),
        ],
        "revenue_share_slope_null_ci95": [
            float(null["revenue_share_price_coefficient"].quantile(0.025)),
            float(null["revenue_share_price_coefficient"].quantile(0.975)),
        ],
    }


def _h91_translation(out_dir: Path) -> dict[str, Any]:
    try:
        summary = json.loads((out_dir / "h91_summary.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"status": "h91_unavailable"}
    translated: dict[str, Any] = {"status": "translated_by_exact_identity"}
    for source, target in [
        ("effective_price_within_between", "effective_price"),
        ("listed_price_within_between", "listed_prompt_open_weight"),
    ]:
        block = summary.get(source, {})
        if not block:
            continue
        translated[target] = {
            "between_revenue_share_price_coefficient": float(block["between_elasticity"]) + 1.0,
            "between_standard_error": float(block["between_standard_error"]),
            "within_revenue_share_price_coefficient": float(block["within_elasticity"]) + 1.0,
            "within_standard_error": float(block["within_standard_error"]),
            "identity": "revenue-share price coefficient = quantity-share price coefficient + 1",
        }
    two_way = summary.get("listed_prompt_open_weight_two_way_fe", {})
    if two_way:
        coefficient = float(two_way["elasticity"]) + 1.0
        standard_error = float(two_way["standard_error"])
        translated["listed_prompt_open_weight_two_way_fe"] = {
            "revenue_share_price_coefficient": coefficient,
            "standard_error": standard_error,
            "ci95": [
                coefficient - 1.96 * standard_error,
                coefficient + 1.96 * standard_error,
            ],
            "p_value_zero": float(2.0 * norm.sf(abs(coefficient / standard_error))),
            "quantity_share_price_coefficient": float(two_way["elasticity"]),
            "economic_interpretation": (
                "This coefficient is the estimated local log-gradient of public gross "
                "revenue with respect to price if the fixed-effect quantity coefficient "
                "is interpreted as the provider's causal own-price elasticity."
            ),
            "identity": "revenue-share price coefficient = quantity-share price coefficient + 1",
        }
    return translated


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    gates = load_gates()["revenue_identity"]
    margin = float(gates["equivalence_margin"])
    alpha = float(gates["alpha"])
    panel = build_identity_panel(load_shares())
    tolerance = float(gates["identity_tolerance"])
    max_residual = float(panel["identity_residual"].abs().max())
    identity_passes = bool(max_residual <= tolerance)

    quantity_fit = _fit_market_fe(panel, "log_share")
    revenue_fit = _fit_market_fe(panel, "log_revenue_proxy_share")
    coefficient_translation_error = float(
        revenue_fit["coefficient"] - quantity_fit["coefficient"] - 1.0
    )
    standard_error_translation_error = float(
        revenue_fit["standard_error"] - quantity_fit["standard_error"]
    )
    revenue_fit.update(
        _equivalence_zero(
            float(revenue_fit["coefficient"]),
            float(revenue_fit["standard_error"]),
            margin=margin,
            alpha=alpha,
        )
    )

    daily_rows = []
    for day, day_panel in panel.groupby("dt", sort=True):
        if day_panel["group"].nunique() < 2:
            continue
        quantity_day = _fit_market_fe(day_panel, "log_share")
        revenue_day = _fit_market_fe(day_panel, "log_revenue_proxy_share")
        daily_rows.append(
            {
                "dt": day,
                "quantity_share_price_coefficient": quantity_day["coefficient"],
                "revenue_share_price_coefficient": revenue_day["coefficient"],
                "revenue_share_standard_error": revenue_day["standard_error"],
                **_equivalence_zero(
                    float(revenue_day["coefficient"]),
                    float(revenue_day["standard_error"]),
                    margin=margin,
                    alpha=alpha,
                ),
            }
        )
    daily = pd.DataFrame(daily_rows)
    save(daily, out_dir, "h92_daily_revenue_share_identity")

    null, permutation = price_label_permutation(
        panel,
        draws=int(gates["permutation_draws"]),
        seed=int(gates["seed"]),
    )
    save(null, out_dir, "h92_price_label_permutation")
    save(
        panel[
            [
                "dt",
                "group",
                "provider_slug",
                "share",
                "effective_output_price",
                "revenue_proxy_share",
                "market_price_index",
                "identity_residual",
            ]
        ],
        out_dir,
        "h92_revenue_share_panel",
    )

    empirical_passes = bool(
        identity_passes
        and abs(coefficient_translation_error) <= tolerance
        and abs(standard_error_translation_error) <= tolerance
        and revenue_fit["equivalent_to_zero"]
        and permutation["one_sided_p_quantity_slope_at_most_observed"] <= alpha
    )
    summary = {
        "evidence_status": (
            "exact_accounting_decomposition_with_price_neutral_revenue_shares"
            if empirical_passes
            else "accounting_decomposition_or_empirical_gate_failed"
        ),
        "identity": {
            "formula": (
                "log quantity share = log revenue-proxy share - log price "
                "+ log market price index"
            ),
            "max_absolute_residual": max_residual,
            "tolerance": tolerance,
            "passes": identity_passes,
            "coefficient_translation_error": coefficient_translation_error,
            "standard_error_translation_error": standard_error_translation_error,
        },
        "quantity_share_price_regression": quantity_fit,
        "revenue_proxy_share_price_regression": revenue_fit,
        "daily_stability": {
            "days": int(len(daily)),
            "days_point_estimate_inside_zero_equivalence_band": int(
                (daily["revenue_share_price_coefficient"].abs() <= margin).sum()
            ),
            "days_statistically_equivalent_to_zero": int(daily["equivalent_to_zero"].sum()),
            "coefficient_range": [
                float(daily["revenue_share_price_coefficient"].min()),
                float(daily["revenue_share_price_coefficient"].max()),
            ],
        },
        "price_label_permutation": permutation,
        "within_between_revenue_share_translation": _h91_translation(out_dir),
        "interpretation": (
            "The pooled quantity-share coefficient near -1 is exactly the statement that "
            "public price-times-token revenue shares have a price coefficient near zero under "
            "the same fixed effects and controls. This is a stable cross-sectional allocation "
            "fact, not a provider residual-demand derivative or a revenue first-order condition."
        ),
        "claim_boundary": (
            "The revenue object is effective output price multiplied by total tokens, not "
            "provider billing or profit. The decomposition is an accounting identity and does "
            "not by itself explain why price and quantity assort negatively. Price labels are "
            "endogenous, and the permutation test rejects exchangeable matching rather than "
            "identifying routing causality."
        ),
    }
    save_json(summary, out_dir, "h92_summary")
    return summary
