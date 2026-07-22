"""Model-specific reduced-form OpenRouter price-exponent estimates.

The documented inverse-square rule is a mechanism benchmark.  This module fits
model/shape-specific conditional-choice slopes on owned default-routing probes,
then partially pools the estimable cells.  It also reports the price-support
diagnostics needed to distinguish a cross-sectional reduced-form slope from a
quality-adjusted within-provider price response.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.dataset as pds
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp
from scipy.stats import chi2

from .live_router_exponent import OWNED_STUDIES, _read_tables, build_observations
from .router_exponent import block_bootstrap_interval, fit_exponent


def _covered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("selected_index") is not None]


def _read_owned_attempts(data_root: Path) -> pd.DataFrame:
    """Read only declared non-blinded studies from the redacted attempt lake."""

    paths = []
    for name in (
        "router_route_attempts",
        "market_measurement_attempts",
        "glm52_routing_attempts",
    ):
        paths.extend(sorted((data_root / "curated" / name).glob("dt=*/*.parquet")))
    if not paths:
        return pd.DataFrame()
    frames = []
    predicate = pds.field("study_id").isin(sorted(OWNED_STUDIES))
    for path in paths:
        # Files from different collectors can encode all-null optional columns
        # with different Arrow types, so filter each file before pandas aligns
        # their schemas.
        table = pds.dataset(str(path), format="parquet").to_table(filter=predicate)
        if table.num_rows:
            frames.append(table.to_pandas())
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _observed_information(rows: list[dict[str, Any]], eta: float) -> float:
    information = 0.0
    for row in _covered(rows):
        log_costs = np.log(np.asarray(row["costs"], dtype=float))
        logits = -float(eta) * log_costs
        probabilities = np.exp(logits - logsumexp(logits))
        mean = float(np.dot(probabilities, log_costs))
        information += float(np.dot(probabilities, np.square(log_costs - mean)))
    return information


def price_support(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return within-menu and within-provider price-support diagnostics."""

    provider_costs: dict[str, set[float]] = {}
    signatures: set[tuple[tuple[str, float], ...]] = set()
    within_menu_sd: list[float] = []
    within_menu_range: list[float] = []
    blocks: set[str] = set()
    selected: set[str] = set()
    candidate_counts: list[int] = []
    for row in _covered(rows):
        providers = [str(provider) for provider in row["providers"]]
        costs = np.asarray(row["costs"], dtype=float)
        blocks.add(str(row.get("block_id") or ""))
        if row.get("selected_provider"):
            selected.add(str(row["selected_provider"]))
        candidate_counts.append(len(costs))
        logs = np.log(costs)
        within_menu_sd.append(float(np.std(logs)))
        within_menu_range.append(float(logs.max() - logs.min()))
        signature = tuple(sorted(zip(providers, np.round(costs, 12), strict=True)))
        signatures.add(signature)
        for provider, cost in zip(providers, costs, strict=True):
            provider_costs.setdefault(provider, set()).add(round(float(cost), 12))
    moving = sum(len(costs) > 1 for costs in provider_costs.values())
    return {
        "blocks": len(blocks),
        "selected_providers": len(selected),
        "candidate_providers": len(provider_costs),
        "median_candidate_count": float(np.median(candidate_counts)) if candidate_counts else None,
        "menu_signatures": len(signatures),
        "price_moving_providers": moving,
        "median_within_menu_log_price_sd": (
            float(np.median(within_menu_sd)) if within_menu_sd else None
        ),
        "median_within_menu_log_price_range": (
            float(np.median(within_menu_range)) if within_menu_range else None
        ),
    }


def fit_cells(
    observations: list[dict[str, Any]],
    *,
    minimum_choices: int = 20,
    minimum_blocks: int = 5,
    bootstrap_draws: int = 200,
) -> pd.DataFrame:
    """Fit one price-only exponent per model and request shape."""

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in observations:
        key = (str(row.get("model_id") or ""), str(row.get("shape_id") or ""))
        groups.setdefault(key, []).append(row)
    output: list[dict[str, Any]] = []
    for (model_id, shape_id), rows in sorted(groups.items()):
        covered = _covered(rows)
        diagnostics = price_support(rows)
        fit = fit_exponent(covered, minimum=minimum_choices)
        eta = fit.get("eta_hat")
        information = (
            _observed_information(covered, float(eta)) if eta is not None else 0.0
        )
        standard_error = 1.0 / math.sqrt(information) if information > 1e-12 else None
        identified = information > 1e-12
        reported_eta = eta if identified else None
        bootstrap = (None, None)
        if (
            fit.get("fit_ready")
            and identified
            and diagnostics["blocks"] >= 2
            and bootstrap_draws > 0
        ):
            bootstrap = block_bootstrap_interval(
                covered,
                draws=bootstrap_draws,
                minimum=minimum_choices,
                seed=20260722,
            )
        failures: list[str] = []
        if len(covered) < minimum_choices:
            failures.append("choices")
        if diagnostics["blocks"] < minimum_blocks:
            failures.append("blocks")
        if information <= 1e-12:
            failures.append("within_menu_price_contrast")
        moving = int(diagnostics["price_moving_providers"])
        score_status = (
            "provisional_within_provider_support"
            if moving >= 2 and diagnostics["blocks"] >= minimum_blocks
            else "not_identified_from_provider_fixed_effects"
        )
        output.append(
            {
                "model_id": model_id,
                "shape_id": shape_id,
                "observations": len(rows),
                "covered_choices": len(covered),
                **diagnostics,
                "eta_price_only": reported_eta,
                "eta_profile_ci_low": fit.get("eta_profile_ci_low") if identified else None,
                "eta_profile_ci_high": fit.get("eta_profile_ci_high") if identified else None,
                "eta_block_bootstrap_low": bootstrap[0],
                "eta_block_bootstrap_high": bootstrap[1],
                "observed_information": information,
                "eta_asymptotic_se": standard_error,
                "price_only_status": "ready" if not failures else "insufficient_support",
                "price_only_failures": ",".join(failures),
                "score_adjusted_status": score_status,
                "minimum_nll": fit.get("minimum_nll") if identified else None,
            }
        )
    return pd.DataFrame(output)


def partial_pool(estimates: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Empirical-Bayes normal partial pooling of estimable cell slopes."""

    usable = estimates[
        estimates["eta_price_only"].notna()
        & estimates["eta_asymptotic_se"].notna()
        & np.isfinite(estimates["eta_asymptotic_se"])
    ].copy()
    if usable.empty:
        return estimates.assign(eta_partially_pooled=np.nan), {
            "cells": 0,
            "global_mean": None,
            "between_cell_sd": None,
        }
    y = usable["eta_price_only"].to_numpy(dtype=float)
    variance = np.square(usable["eta_asymptotic_se"].to_numpy(dtype=float))

    def profile(tau: float) -> float:
        weights = 1.0 / (variance + tau**2)
        mean = float(np.dot(weights, y) / weights.sum())
        return float(
            0.5 * np.sum(np.log(variance + tau**2) + np.square(y - mean) / (variance + tau**2))
        )

    optimized = minimize_scalar(profile, bounds=(0.0, 8.0), method="bounded")
    tau = float(optimized.x)
    weights = 1.0 / (variance + tau**2)
    mean = float(np.dot(weights, y) / weights.sum())
    if tau <= 1e-8:
        posterior_mean = np.repeat(mean, len(y))
        posterior_se = np.zeros(len(y))
    else:
        posterior_variance = 1.0 / (1.0 / variance + 1.0 / tau**2)
        posterior_mean = posterior_variance * (y / variance + mean / tau**2)
        posterior_se = np.sqrt(posterior_variance)
    estimates = estimates.copy()
    estimates["eta_partially_pooled"] = np.nan
    estimates["eta_partially_pooled_se"] = np.nan
    estimates.loc[usable.index, "eta_partially_pooled"] = posterior_mean
    estimates.loc[usable.index, "eta_partially_pooled_se"] = posterior_se
    return estimates, {
        "cells": len(usable),
        "global_mean": mean,
        "between_cell_sd": tau,
    }


def heterogeneity_test(
    observations: list[dict[str, Any]], estimates: pd.DataFrame
) -> dict[str, Any]:
    """Likelihood-ratio comparison of a pooled slope with separate cell slopes."""

    usable = estimates[
        estimates["eta_price_only"].notna()
        & estimates["eta_asymptotic_se"].notna()
        & np.isfinite(estimates["eta_asymptotic_se"])
    ]
    keys = set(zip(usable["model_id"], usable["shape_id"], strict=True))
    rows = [
        row
        for row in observations
        if row.get("selected_index") is not None
        and (str(row.get("model_id")), str(row.get("shape_id"))) in keys
    ]
    pooled = fit_exponent(rows, minimum=20)
    if not pooled.get("fit_ready") or len(usable) < 2:
        return {
            "cells": len(usable),
            "pooled_eta": pooled.get("eta_hat"),
            "lr_statistic": None,
            "degrees_of_freedom": None,
            "p_value": None,
        }
    separate_nll = float(usable["minimum_nll"].sum())
    statistic = max(0.0, 2.0 * (float(pooled["minimum_nll"]) - separate_nll))
    degrees = len(usable) - 1
    return {
        "cells": len(usable),
        "pooled_eta": pooled.get("eta_hat"),
        "pooled_profile_ci_low": pooled.get("eta_profile_ci_low"),
        "pooled_profile_ci_high": pooled.get("eta_profile_ci_high"),
        "lr_statistic": statistic,
        "degrees_of_freedom": degrees,
        "p_value": float(chi2.sf(statistic, degrees)),
    }


def run(data_root: Path, output_dir: Path) -> dict[str, Any]:
    candidates = _read_tables(
        data_root,
        (
            "router_calibration_candidates",
            "price_response_candidates",
            "market_measurement_candidates",
            "glm52_routing_candidates",
        ),
    )
    assignments = _read_tables(
        data_root,
        (
            "router_calibration_assignments",
            "price_response_assignments",
            "market_measurement_assignments",
            "glm52_routing_assignments",
        ),
    )
    # Predicate pushdown prevents unrelated blinded experiments from being
    # materialized when the generic redacted attempt lake is present.
    attempts = _read_owned_attempts(data_root)
    observations = build_observations(candidates, assignments, attempts)
    estimates = fit_cells(observations)
    estimates, pooling = partial_pool(estimates)
    heterogeneity = heterogeneity_test(observations, estimates)
    output_dir.mkdir(parents=True, exist_ok=True)
    estimates.to_csv(output_dir / "model_specific_router_exponents.csv", index=False)
    estimates.to_parquet(output_dir / "model_specific_router_exponents.parquet", index=False)
    summary = {
        "study_id": "model-specific-router-exponent-v1",
        "source_revision": os.environ.get("ORCAP_HF_REVISION"),
        "observations": len(observations),
        "covered_choices": sum(row.get("selected_index") is not None for row in observations),
        "cells": len(estimates),
        "partial_pooling": pooling,
        "heterogeneity": heterogeneity,
        "claim_boundary": (
            "Model-specific price-only slopes are reduced-form owned-choice estimates. "
            "A cell without within-provider repricing cannot separate price sensitivity "
            "from provider/model score levels. These estimates are not market-wide share, "
            "demand elasticity, or the proprietary router rule."
        ),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.data_root, args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
