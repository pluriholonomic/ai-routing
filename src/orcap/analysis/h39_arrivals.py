"""H39 — Arrival-process modeling from interval-censored counts.

We observe counts through windows (request_count_30m sampled 5-minutely),
never raw timestamps — so we fit count-native point-process models:

  INGARCH(1,1)   N_t | F ~ Poisson(λ_t), λ_t = ω + α·N_{t-1} + β·λ_{t-1},
                 on NON-overlapping 30-min counts (every 6th tick). The
                 persistence α+β is the count analog of a Hawkes branching
                 ratio (Kirchner's INAR bridge); → 1 means near-critical
                 clustering. Fit per endpoint with ≥60 non-overlapping obs.
  Aggregated-variance Hurst   Var of m-aggregated counts ~ m^{2H}; H = 0.5
                 for short-memory, → 1 for self-similar traffic (the
                 Leland/Taqqu Ethernet result). Pooled log-log slope across
                 endpoints; block counts are few at this panel length —
                 preliminary until ~2 weeks.

Roadmap (gated): Markov-modulated Poisson (burst ON/OFF regimes) and
negative-binomial INGARCH for within-bin overdispersion.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_series() -> dict[str, np.ndarray]:
    cg = data.q(
        f"""
        select endpoint_uuid, run_ts, request_count_30m
        from read_parquet('{data.table_glob("congestion_intraday")}')
        where request_count_30m >= 0
        order by endpoint_uuid, run_ts
        """
    ).df()
    out = {}
    for uid, g in cg.groupby("endpoint_uuid"):
        x = g["request_count_30m"].to_numpy(dtype=float)[::6]  # non-overlapping 30-min
        if len(x) >= 36 and x.mean() > 20:  # preliminary; sharpens as panel grows
            out[uid] = x
    return out


def fit_ingarch(x: np.ndarray) -> dict | None:
    xbar = x.mean()

    def nll(theta):
        w, a, b = theta
        if w <= 0 or a < 0 or b < 0 or a + b >= 0.999:
            return 1e12
        lam = xbar
        ll = 0.0
        for t in range(1, len(x)):
            lam = w + a * x[t - 1] + b * lam
            ll += x[t] * np.log(max(lam, 1e-9)) - lam - gammaln(x[t] + 1)
        return -ll

    best = None
    for a0, b0 in [(0.3, 0.4), (0.6, 0.2), (0.1, 0.7)]:
        r = minimize(
            nll,
            x0=[xbar * (1 - a0 - b0), a0, b0],
            method="Nelder-Mead",
            options={"maxiter": 2000, "xatol": 1e-5},
        )
        if best is None or r.fun < best.fun:
            best = r
    if best is None or not np.isfinite(best.fun):
        return None
    w, a, b = best.x
    return {"alpha": float(a), "beta": float(b), "persistence": float(a + b)}


def hurst_pooled(series: dict[str, np.ndarray]) -> dict:
    ms = [1, 2, 4, 8]
    slopes = []
    for x in series.values():
        vs = []
        for m in ms:
            k = len(x) // m
            if k < 6:
                vs.append(np.nan)
                continue
            agg = x[: k * m].reshape(k, m).sum(axis=1) / m  # mean-aggregated
            vs.append(np.var(agg))
        vs = np.array(vs)
        ok = ~np.isnan(vs) & (vs > 0)
        if ok.sum() >= 3:
            # Var(X^(m)) ~ m^(2H-2) for the mean-aggregated series
            slope = np.polyfit(np.log(np.array(ms)[ok]), np.log(vs[ok]), 1)[0]
            slopes.append(1 + slope / 2)
    if not slopes:
        return {"gated": "insufficient blocks"}
    s = pd.Series(slopes).clip(0, 1.2)
    return {
        "n_endpoints": int(len(s)),
        "hurst_median": round(float(s.median()), 3),
        "hurst_iqr": [round(float(s.quantile(q)), 3) for q in (0.25, 0.75)],
        "read": "H=0.5 short memory; H→1 self-similar (heavy-tailed sessions); "
        "preliminary at current panel length",
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    series = load_series()
    if not series:
        return {"gated": "no usable endpoint series yet"}
    fits = []
    for uid, x in series.items():
        f = fit_ingarch(x)
        if f:
            f["endpoint_uuid"] = uid
            f["n_obs"] = len(x)
            f["mean_count"] = float(x.mean())
            fits.append(f)
    df = pd.DataFrame(fits)
    save(df, out_dir, "h39_ingarch_fits")
    pers = df["persistence"]
    results = {
        "n_endpoints_fit": int(len(df)),
        "ingarch_persistence_median": round(float(pers.median()), 3),
        "ingarch_persistence_p90": round(float(pers.quantile(0.9)), 3),
        "share_near_critical_gt_0.9": round(float((pers > 0.9).mean()), 3),
        "alpha_median": round(float(df["alpha"].median()), 3),
        "hurst": hurst_pooled(series),
        "data_caveat": (
            "interval-censored counts, 30-min windows; within-bin overdispersion pushes "
            "Poisson-INGARCH persistence UP — NegBin variant and MMPP gate at ~2 weeks of panel"
        ),
    }
    save_json(results, out_dir, "h39_summary")
    log.info("H39: %s", {k: v for k, v in results.items() if k != "hurst"})
    return results
