"""H68 — Which model markets are most competitive? A latent-factor ranking.

Competition intensity is not directly observable; treating any single proxy
(provider count, price cuts) as "the" measure invites cherry-picking. This
module specifies one measurement model: per model-market, seven observable
indicators load on a single latent competition factor fit by maximum
likelihood. The factor is sign-aligned to load positively on provider count,
scores are Bartlett factor scores, and ranking uncertainty comes from a
bootstrap over days (the panel's exchangeable unit).

Indicators (per model, standard variant only, providers quoting completion):
  n_providers          mean daily distinct quoting providers
  eff_providers        mean daily exp(entropy) of token share (demand-side N)
  dispersion           mean daily std of log completion quotes across providers
  span                 mean daily log(max/min) completion quote
  best_turnover        share of day-pairs where the cheapest provider changed
  cut_intensity        completion-price cuts per provider-day
  cut_share            share of completion-price changes that are decreases

The model reports its own internal consistency (Cronbach's alpha, split-half
score correlation). Dispersion/span loadings are diagnostics, not assumptions:
Baye-Morgan clearinghouse logic allows either sign.

  h68_competition.parquet   indicators + factor score + bootstrap CI per model
  h68_summary.json          loadings, consistency stats, top/bottom ranking
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .market_scope import paid_model_sql

log = logging.getLogger(__name__)

MIN_DAYS = 4
MIN_MODELS = 30
MIN_PROVIDERS = 2
BOOTSTRAP = 200
INDICATORS = [
    "n_providers",
    "eff_providers",
    "dispersion",
    "span",
    "best_turnover",
    "cut_intensity",
    "cut_share",
]


# ---------------------------------------------------------------- indicators


def daily_quotes() -> pd.DataFrame:
    """One completion quote per (dt, model, provider): the daily median."""
    return data.q(
        f"""
        select cast(dt as varchar) as dt, model_id, provider_name,
               median(price_completion) as price
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        where price_completion > 0 and {paid_model_sql("model_id")}
        group by 1, 2, 3
        """
    ).df()


def demand_shares() -> pd.DataFrame:
    """Token shares keyed back to model_id via the canonical-slug map."""
    shares = data.q(
        f"""
        select cast(dt as varchar) as dt, model_permaslug, provider_name,
               sum(total_tokens) as tokens
        from read_parquet('{data.table_glob("effective_pricing_daily")}', union_by_name=true)
        where variant = 'standard' and total_tokens > 0
        group by 1, 2, 3
        """
    ).df()
    slug_map = data.q(
        f"""
        select distinct canonical_slug, id as model_id
        from read_parquet('{data.table_glob("models_snapshots")}', union_by_name=true)
        where canonical_slug is not null
        """
    ).df()
    shares = shares.merge(
        slug_map, left_on="model_permaslug", right_on="canonical_slug", how="left"
    )
    shares["model_id"] = shares["model_id"].fillna(shares["model_permaslug"])
    return shares


def completion_cuts() -> pd.DataFrame:
    changes = data.q(
        f"""
        select cast(dt as varchar) as dt, model_id, provider_name, old_value, new_value
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion' and {paid_model_sql("model_id")}
        """
    ).df()
    old = pd.to_numeric(changes["old_value"], errors="coerce")
    new = pd.to_numeric(changes["new_value"], errors="coerce")
    changes["is_cut"] = (new < old) & new.notna() & old.notna()
    changes["is_change"] = new.notna() & old.notna()
    return changes


def day_indicators(quotes: pd.DataFrame, shares: pd.DataFrame, cuts: pd.DataFrame) -> pd.DataFrame:
    """Per (model, dt) indicator rows; day is the bootstrap resampling unit."""
    rows = []
    for (model, dt), g in quotes.groupby(["model_id", "dt"]):
        if len(g) < MIN_PROVIDERS:
            continue
        logp = np.log(g["price"].to_numpy())
        rows.append(
            {
                "model_id": model,
                "dt": dt,
                "n_providers": float(len(g)),
                "dispersion": float(np.std(logp, ddof=0)),
                "span": float(logp.max() - logp.min()),
                "best_provider": g.loc[g["price"].idxmin(), "provider_name"],
            }
        )
    day = pd.DataFrame(rows)
    if day.empty:
        return day

    # demand-side effective provider count (permaslug ≈ model id for standard)
    if not shares.empty:
        ent = []
        for (model, dt), g in shares.groupby(["model_id", "dt"]):
            p = g["tokens"].to_numpy(dtype=float)
            p = p / p.sum()
            ent.append(
                {
                    "model_id": model,
                    "dt": dt,
                    "eff_providers": float(np.exp(-(p * np.log(p)).sum())),
                }
            )
        day = day.merge(pd.DataFrame(ent), on=["model_id", "dt"], how="left")
    else:
        day["eff_providers"] = np.nan

    # cheapest-provider turnover vs the previous observed day
    day = day.sort_values(["model_id", "dt"])
    prev = day.groupby("model_id")["best_provider"].shift()
    day["best_turnover"] = np.where(prev.isna(), np.nan, (day["best_provider"] != prev) * 1.0)

    # repricing cuts, normalized by that day's quoting providers
    if not cuts.empty:
        agg = (
            cuts.groupby(["model_id", "dt"])[["is_cut", "is_change"]]
            .sum()
            .reset_index()
            .rename(columns={"is_cut": "n_cuts", "is_change": "n_changes"})
        )
        day = day.merge(agg, on=["model_id", "dt"], how="left")
    else:
        day["n_cuts"] = day["n_changes"] = 0.0
    day[["n_cuts", "n_changes"]] = day[["n_cuts", "n_changes"]].fillna(0.0)
    day["cut_intensity"] = day["n_cuts"] / day["n_providers"]
    day["cut_share"] = np.where(day["n_changes"] > 0, day["n_cuts"] / day["n_changes"], np.nan)
    return day


def collapse(day: pd.DataFrame, min_days: int = MIN_DAYS) -> pd.DataFrame:
    """Average day rows to one indicator vector per model."""
    agg = day.groupby("model_id").agg(
        days=("dt", "nunique"),
        n_providers=("n_providers", "mean"),
        eff_providers=("eff_providers", "mean"),
        dispersion=("dispersion", "mean"),
        span=("span", "mean"),
        best_turnover=("best_turnover", "mean"),
        cut_intensity=("cut_intensity", "mean"),
        cut_share=("cut_share", "mean"),
    )
    return agg[agg["days"] >= min_days].reset_index()


# --------------------------------------------------------------- factor model


def _standardize(x: pd.DataFrame) -> pd.DataFrame:
    """Normal-scores (van der Waerden) transform per indicator.

    Rank-based scoring is scale-free and keeps heavy-tailed indicators (span,
    cut intensity) from dominating loadings or bunching the top of the ranking
    the way winsorized z-scores do. Missing values sit at the neutral point.
    """
    from scipy.stats import norm

    out = {}
    for col in x.columns:
        ranks = x[col].rank(method="average")
        out[col] = pd.Series(
            norm.ppf(ranks / (x[col].notna().sum() + 1.0)), index=x.index
        )
    return pd.DataFrame(out).fillna(0.0)


def fit_factor(models: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """One-factor ML fit; returns (scores indexed like models, loadings)."""
    from sklearn.decomposition import FactorAnalysis

    z = _standardize(models[INDICATORS])
    fa = FactorAnalysis(n_components=1, random_state=0)
    fa.fit(z.to_numpy())
    loadings = pd.Series(fa.components_[0], index=INDICATORS)
    if loadings["n_providers"] < 0:  # sign convention: more providers = more competition
        loadings = -loadings
    # Bartlett scores: (L' Psi^-1 L)^-1 L' Psi^-1 z
    lam = loadings.to_numpy()[:, None]
    psi_inv = np.diag(1.0 / np.maximum(fa.noise_variance_, 1e-6))
    weights = np.linalg.solve(lam.T @ psi_inv @ lam, lam.T @ psi_inv).ravel()
    scores = pd.Series(z.to_numpy() @ weights, index=models["model_id"].to_numpy())
    return scores, loadings


def bootstrap_scores(day: pd.DataFrame, n_boot: int = BOOTSTRAP) -> pd.DataFrame:
    """Resample days with replacement; refit; collect score distributions."""
    days = sorted(day["dt"].unique())
    rng = np.random.default_rng(20260712)
    samples: dict[str, list[float]] = {}
    for _ in range(n_boot):
        pick = rng.choice(days, size=len(days), replace=True)
        boot_day = pd.concat([day[day["dt"] == d] for d in pick], ignore_index=True)
        models = collapse(boot_day)
        if len(models) < MIN_MODELS:
            continue
        try:
            scores, _ = fit_factor(models)
        except Exception:
            continue
        for m, s in scores.items():
            samples.setdefault(m, []).append(float(s))
    rows = [
        {
            "model_id": m,
            "score_lo": float(np.percentile(v, 5)),
            "score_hi": float(np.percentile(v, 95)),
            "n_boot": len(v),
        }
        for m, v in samples.items()
        if len(v) >= n_boot * 0.5
    ]
    return pd.DataFrame(rows)


def consistency(models: pd.DataFrame, loadings: pd.Series, day: pd.DataFrame) -> dict:
    z = _standardize(models[INDICATORS])
    aligned = z * np.sign(loadings)
    k = aligned.shape[1]
    item_var = aligned.var(ddof=1).sum()
    total_var = aligned.sum(axis=1).var(ddof=1)
    alpha = (k / (k - 1)) * (1 - item_var / total_var) if total_var > 0 else np.nan

    days = sorted(day["dt"].unique())
    half = len(days) // 2
    split_min = max(2, half - 1)
    first = collapse(day[day["dt"].isin(days[:half])], min_days=split_min)
    second = collapse(day[day["dt"].isin(days[half:])], min_days=split_min)
    split_r = np.nan
    if len(first) >= MIN_MODELS and len(second) >= MIN_MODELS:
        try:
            s1, _ = fit_factor(first)
            s2, _ = fit_factor(second)
            joined = pd.concat([s1.rename("a"), s2.rename("b")], axis=1).dropna()
            if len(joined) >= 10:
                split_r = float(joined["a"].corr(joined["b"], method="spearman"))
        except Exception:
            pass
    return {"cronbach_alpha": float(alpha), "split_half_spearman": split_r}


# ------------------------------------------------------------------------ run


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    quotes, shares, cuts = daily_quotes(), demand_shares(), completion_cuts()
    day = day_indicators(quotes, shares, cuts)
    models = collapse(day) if not day.empty else pd.DataFrame()
    if len(models) < MIN_MODELS:
        summary = {
            "evidence_status": "power_gated",
            "n_models": int(len(models)),
            "gate": f"needs >= {MIN_MODELS} multi-provider models with >= {MIN_DAYS} days",
        }
        save_json(summary, out_dir, "h68_summary")
        return summary

    scores, loadings = fit_factor(models)
    models["competition_score"] = models["model_id"].map(scores)
    ci = bootstrap_scores(day)
    models = models.merge(ci, on="model_id", how="left")
    models = models.sort_values("competition_score", ascending=False).reset_index(drop=True)
    models["rank"] = models.index + 1
    save(models, out_dir, "h68_competition")

    checks = consistency(models, loadings, day)
    top = models.head(10)[["rank", "model_id", "competition_score", "score_lo", "score_hi"]]
    bottom = models.tail(5)[["rank", "model_id", "competition_score", "score_lo", "score_hi"]]
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_models": int(len(models)),
        "n_days": int(day["dt"].nunique()),
        "loadings": {k: round(float(v), 3) for k, v in loadings.items()},
        **checks,
        "top10": top.to_dict("records"),
        "bottom5": bottom.to_dict("records"),
        "claim_boundary": (
            "One latent factor over public quote/repricing/demand-share indicators on a "
            "short panel. It ranks markets by observable competitive activity; it does not "
            "identify conduct, markups over cost, or welfare, and dispersion's loading sign "
            "is a diagnostic, not an assumption."
        ),
    }
    save_json(summary, out_dir, "h68_summary")
    log.info(
        "h68: %d models, alpha=%.2f split-half=%.2f",
        len(models),
        checks["cronbach_alpha"],
        checks["split_half_spearman"] or float("nan"),
    )
    return summary
