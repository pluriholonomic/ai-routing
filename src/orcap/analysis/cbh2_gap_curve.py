"""CBH-2 (was H71) — Baye-Morgan gap(N) curve: dispersion between the two cheapest quotes.

Benchmark (Baye-Morgan-Scholten 2004, Shopper.com): gap between the two lowest
posted prices averages 22% with N=2 sellers, falling to 3.5% at N=17, and
never converges to the law of one price. Clearinghouse equilibria sustain
dispersion through 'loyal' (price-insensitive) traffic.

Compute Brokerage Hypothesis prediction Q3: quality-adjusted gap stays >= ~3%
at every N — the pinned/BYOK share funds it. Bertrand-commodity alternative:
gap -> 0 for N >= 3 because the router automates shopping.

  h71_gap_by_n.parquet    per-N: mean/median gap, n obs
  h71_summary.json        curve + benchmark comparison
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes

log = logging.getLogger(__name__)


def gaps(quotes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (model, dt), g in quotes.groupby(["model_id", "dt"]):
        p = np.sort(g["price"].to_numpy())
        if len(p) < 2 or p[0] <= 0:
            continue
        rows.append(
            {
                "model_id": model,
                "dt": dt,
                "n_providers": len(p),
                "gap_pct": 100.0 * (p[1] - p[0]) / p[0],
                "range_pct": 100.0 * (p[-1] - p[0]) / p[0],
            }
        )
    return pd.DataFrame(rows)


BMS_BENCHMARK = {2: 22.0, 17: 3.5}  # Baye-Morgan-Scholten 2004
GRID_NULL_SEED = 20260716
GRID_NULL_REPS = 1_000
GRID_BOOTSTRAP_REPS = 2_000
CENT_PER_MTOK = 1e-8
DIME_PER_MTOK = 1e-7


def _grid_null_inputs(quotes: pd.DataFrame) -> tuple[dict[str, list[tuple]], dict[str, np.ndarray]]:
    """Collapse quotes into model clusters used by the independent grid null.

    Each group tuple is ``(n providers, log median, observed minimum-tie)``.
    Deviations are pooled only over multi-provider model-days so the null and
    observed statistic have the same support.
    """
    groups: dict[str, list[tuple]] = {}
    deviations: dict[str, list[np.ndarray]] = {}
    for (model, _dt), g in quotes.groupby(["model_id", "dt"], sort=False):
        prices = pd.to_numeric(g["price"], errors="coerce").to_numpy(dtype=float)
        prices = prices[np.isfinite(prices) & (prices > 0)]
        if len(prices) < 2:
            continue
        ordered = np.sort(prices)
        log_prices = np.log(prices)
        log_median = float(np.median(log_prices))
        observed_tie = bool(100.0 * (ordered[1] - ordered[0]) / ordered[0] < 0.01)
        groups.setdefault(str(model), []).append((len(prices), log_median, observed_tie))
        deviations.setdefault(str(model), []).append(log_prices - log_median)
    return groups, {model: np.concatenate(parts) for model, parts in deviations.items()}


def _one_grid_null_rate(
    selected_models: np.ndarray,
    groups: dict[str, list[tuple]],
    deviations: dict[str, np.ndarray],
    grid: float,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Return observed and simulated tie rates for one cluster resample."""
    pool = np.concatenate([deviations[str(model)] for model in selected_models])
    observed_ties = 0
    simulated_ties = 0
    n_groups = 0
    for model in selected_models:
        for n_providers, log_median, observed_tie in groups[str(model)]:
            observed_ties += int(observed_tie)
            draws = rng.choice(pool, size=n_providers, replace=True)
            # Integer grid bins avoid floating-point equality decisions.
            bins = np.rint(np.exp(log_median + draws) / grid).astype(np.int64)
            two_smallest = np.partition(bins, 1)[:2]
            simulated_ties += int(two_smallest[0] == two_smallest[1])
            n_groups += 1
    return observed_ties / n_groups, simulated_ties / n_groups


def grid_null_tie_inference(
    quotes: pd.DataFrame,
    *,
    grid: float = CENT_PER_MTOK,
    null_reps: int = GRID_NULL_REPS,
    bootstrap_reps: int = GRID_BOOTSTRAP_REPS,
    seed: int = GRID_NULL_SEED,
) -> dict:
    """Independent-grid null plus model-cluster interval for the tie excess.

    The point null holds the observed model-day medians and provider counts
    fixed while drawing provider log-price deviations independently from the
    pooled empirical distribution. The confidence interval resamples models
    (all their days move together) and re-runs one null draw in every outer
    bootstrap replicate. The inner Monte Carlo noise makes the interval
    conservative relative to integrating out the null draw.
    """
    groups, deviations = _grid_null_inputs(quotes)
    models = np.asarray(sorted(groups), dtype=object)
    if len(models) < 2:
        return {"evidence_status": "power_gated", "gate": "fewer than two model clusters"}

    rng = np.random.default_rng(seed)
    observed_rate, _ = _one_grid_null_rate(models, groups, deviations, grid, rng)
    null_rates = np.empty(null_reps, dtype=float)
    for rep in range(null_reps):
        _, null_rates[rep] = _one_grid_null_rate(models, groups, deviations, grid, rng)

    excess = np.empty(bootstrap_reps, dtype=float)
    for rep in range(bootstrap_reps):
        selected = rng.choice(models, size=len(models), replace=True)
        observed_boot, null_boot = _one_grid_null_rate(selected, groups, deviations, grid, rng)
        excess[rep] = observed_boot - null_boot

    lo, hi = np.quantile(excess, [0.025, 0.975])
    return {
        "evidence_status": "cluster_inference",
        "n_model_days": int(sum(len(v) for v in groups.values())),
        "n_model_clusters": int(len(models)),
        "grid_dollars_per_token": float(grid),
        "observed_tie_rate": float(observed_rate),
        "null_tie_rate_mean": float(null_rates.mean()),
        "null_tie_rate_sd": float(null_rates.std(ddof=1)),
        "observed_minus_null": float(observed_rate - null_rates.mean()),
        "cluster_bootstrap_ci95": [float(lo), float(hi)],
        "cluster_bootstrap_reps": int(bootstrap_reps),
        "null_simulation_reps": int(null_reps),
        "seed": int(seed),
        "bootstrap_unit": "model; all model-days move together",
        "interval_note": (
            "One re-simulated null draw per outer replicate; conservative for null "
            "Monte Carlo noise."
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    quotes = daily_quotes()
    day = gaps(quotes)
    if day.empty:
        summary = {"evidence_status": "power_gated", "gate": "no multi-provider model-days"}
        save_json(summary, out_dir, "cbh2_summary")
        return summary
    day["n_bucket"] = day["n_providers"].clip(upper=15)
    curve = (
        day.groupby("n_bucket")
        .agg(
            mean_gap_pct=("gap_pct", "mean"),
            median_gap_pct=("gap_pct", "median"),
            share_gap_lt_1pct=("gap_pct", lambda s: float((s < 1.0).mean())),
            mean_range_pct=("range_pct", "mean"),
            n_model_days=("gap_pct", "size"),
        )
        .reset_index()
    )
    save(curve, out_dir, "cbh2_gap_by_n")
    lo = day[day["n_providers"] == 2]
    hi = day[day["n_providers"] >= 10]
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_model_days": int(len(day)),
        "n_models": int(day["model_id"].nunique()),
        "gap_at_n2_median_pct": float(lo["gap_pct"].median()) if len(lo) else None,
        "gap_at_n10plus_median_pct": float(hi["gap_pct"].median()) if len(hi) else None,
        "share_exact_tie_at_min": float((day["gap_pct"] < 0.01).mean()),
        "curve": curve.to_dict("records"),
        "benchmark_bms2004": BMS_BENCHMARK,
        "prediction_q3": "quality-unadjusted gap floor >= ~3% at high N (clearinghouse); "
        "Bertrand alternative: gap -> 0 for N >= 3",
        "claim_boundary": (
            "Posted completion quotes, standard variants, not quality-adjusted; a nonzero "
            "gap can reflect quality differentiation as well as loyal-flow rents. The "
            "quality-adjusted version gates on the fingerprint probe panel."
        ),
        "cent_grid_null_inference": grid_null_tie_inference(quotes),
        "dime_grid_null_inference": grid_null_tie_inference(
            quotes,
            grid=DIME_PER_MTOK,
            seed=GRID_NULL_SEED + 1,
        ),
    }
    save_json(summary, out_dir, "cbh2_summary")
    return summary
