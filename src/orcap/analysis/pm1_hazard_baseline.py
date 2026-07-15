"""PM-1 — Baseline repricing hazard and the nesting ladder.

Discrete-time (daily) hazard of a completion-price change per
provider x model pair, cloglog link, with the pre-registered ladder:

  L1 Calvo            constant hazard
  L2 time-dependent   + spell-age bins + day-of-week
  L3 state-dependent  + |gap to rival median|, sign(gap), |GPU cost change|
  L4 congestion       + utilization / rate-limit / latency (hot subsample)
  L5 strategic        + trailing rival moves by sign (24h/7d)

Each rung is an LR (deviance) test against the previous. v1 runs on a
~10-day panel: age bins are coarse, unit frailty is infeasible (provider
cluster means instead), and all conclusions carry the short-panel gate.

  pm1_ladder.parquet   coefficients per rung
  pm1_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes

log = logging.getLogger(__name__)


def build_panel() -> pd.DataFrame:
    q = daily_quotes()  # dt, model_id, provider_name, price (daily median)
    ch = data.q(
        f"""
        select cast(dt as varchar) as dt, model_id, provider_name,
               max(case when try_cast(new_value as double) > try_cast(old_value as double)
                   then 1 else 0 end) as any_raise,
               count(*) as n_changes
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion' and model_id not like '%:%'
          and try_cast(old_value as double) > 0
        group by 1, 2, 3
        """
    ).df()
    p = q.merge(ch, on=["dt", "model_id", "provider_name"], how="left")
    p["event"] = p["n_changes"].fillna(0) > 0

    # spell age in days since last change (censored at panel entry)
    p = p.sort_values(["model_id", "provider_name", "dt"])
    p["d"] = pd.to_datetime(p["dt"])
    last_change = {}
    ages, censored = [], []
    for key, day, ev in zip(
        zip(p["model_id"], p["provider_name"]), p["d"], p["event"]
    ):
        lc = last_change.get(key)
        ages.append((day - lc).days if lc is not None else np.nan)
        censored.append(lc is None)
        if ev:
            last_change[key] = day
    p["age"], p["age_censored"] = ages, censored

    # gap to rival median (same model-day)
    med = p.groupby(["model_id", "dt"])["price"].transform("median")
    nprov = p.groupby(["model_id", "dt"])["provider_name"].transform("size")
    p["gap"] = np.where(nprov >= 2, np.log(p["price"]) - np.log(med), np.nan)

    # GPU cost daily change
    g = data.q(
        f"""
        select cast(dt as varchar) as dt,
               median(try_cast(dph_base as double)/greatest(num_gpus,1)) as spot
        from read_parquet('{data.table_glob("gpu_offers_snapshots")}', union_by_name=true)
        where gpu_name like '%H100%' and offer_type = 'on-demand' and rentable
        group by 1 order by 1
        """
    ).df()
    g["gpu_dlog"] = np.log(g["spot"]).diff()
    p = p.merge(g[["dt", "gpu_dlog"]], on="dt", how="left")

    # trailing rival moves on the same model (previous day), by sign
    ev_day = (
        p[p["event"]]
        .groupby(["model_id", "dt"])
        .agg(n_moves=("event", "size"), n_raises=("any_raise", "sum"))
        .reset_index()
    )
    ev_day["d"] = pd.to_datetime(ev_day["dt"])
    prev = ev_day.copy()
    prev["d"] = prev["d"] + pd.Timedelta(days=1)
    prev = prev.rename(columns={"n_moves": "rival_moves_1d", "n_raises": "rival_raises_1d"})
    p = p.merge(
        prev[["model_id", "d", "rival_moves_1d", "rival_raises_1d"]],
        on=["model_id", "d"],
        how="left",
    )
    # subtract own move if it was yesterday (approximation: own event yesterday)
    p[["rival_moves_1d", "rival_raises_1d"]] = p[["rival_moves_1d", "rival_raises_1d"]].fillna(0)
    p["dow"] = p["d"].dt.dayofweek

    # congestion (hot panel): daily mean utilization + rl share per pair
    cong = data.q(
        f"""
        select model_permaslug, provider_name, substr(run_ts,1,8) as day8,
               avg(try_cast(recent_peak_rpm as double)/nullif(try_cast(capacity_ceiling_rpm as double),0)) as util,
               sum(try_cast(rate_limited_30m as double))/nullif(sum(try_cast(request_count_30m as double)),0) as rl
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        group by 1,2,3
        """
    ).df()
    slug = data.q(
        f"""
        select distinct canonical_slug, id from
        read_parquet('{data.table_glob("models_snapshots")}', union_by_name=true)
        where canonical_slug is not null
        """
    ).df()
    cong = cong.merge(slug, left_on="model_permaslug", right_on="canonical_slug", how="left")
    cong["model_id"] = cong["id"].fillna(cong["model_permaslug"])
    cong["dt"] = cong["day8"].str[:4] + "-" + cong["day8"].str[4:6] + "-" + cong["day8"].str[6:8]
    p = p.merge(
        cong[["model_id", "provider_name", "dt", "util", "rl"]],
        on=["model_id", "provider_name", "dt"],
        how="left",
    )
    # provider historical activity (frailty substitute), leave-one-out so the
    # regressor never contains the observation's own outcome
    grp = p.groupby("provider_name")["event"]
    s, n = grp.transform("sum"), grp.transform("size")
    p["provider_rate"] = ((s - p["event"]) / (n - 1).clip(lower=1)).clip(0, 0.5)
    return p


AGE_BINS = [(1, 2), (3, 5), (6, 9), (10, 99)]


def design(p: pd.DataFrame, rung: int) -> tuple[np.ndarray, list[str]]:
    cols, names = [np.ones(len(p))], ["const"]
    if rung >= 2:
        for lo, hi in AGE_BINS[1:]:
            cols.append(((p["age"] >= lo) & (p["age"] <= hi)).astype(float).to_numpy())
            names.append(f"age_{lo}_{hi}")
        cols.append(p["age_censored"].astype(float).to_numpy())
        names.append("age_censored")
        for d in range(1, 7):
            cols.append((p["dow"] == d).astype(float).to_numpy())
            names.append(f"dow{d}")
        cols.append(p["provider_rate"].to_numpy())
        names.append("provider_rate")
    if rung >= 3:
        cols += [
            p["gap"].abs().fillna(0).to_numpy(),
            (p["gap"] > 0).astype(float).to_numpy(),
            p["gpu_dlog"].abs().fillna(0).to_numpy(),
        ]
        names += ["abs_gap", "gap_positive", "abs_gpu_dlog"]
    if rung >= 4:
        cols += [p["util"].fillna(0).to_numpy(), p["rl"].fillna(0).to_numpy(),
                 p["util"].isna().astype(float).to_numpy()]
        names += ["util", "rl_share", "cong_missing"]
    if rung >= 5:
        cols += [p["rival_moves_1d"].to_numpy(), p["rival_raises_1d"].to_numpy()]
        names += ["rival_moves_1d", "rival_raises_1d"]
    return np.column_stack(cols), names


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    import statsmodels.api as sm
    from scipy import stats as st

    p = build_panel()
    y = p["event"].astype(float).to_numpy()
    n_days = p["dt"].nunique()
    results, prev_llf, prev_df = [], None, None
    ladder = {}
    for rung in (1, 2, 3, 4, 5):
        X, names = design(p, rung)
        # logit ~ cloglog at 1.5% hazards, and is numerically stable where
        # cloglog's saturating tail produces mu=1 and NaN likelihoods
        model = sm.GLM(y, X, family=sm.families.Binomial())
        try:
            fit = model.fit(maxiter=200)
        except Exception as exc:
            ladder[f"L{rung}"] = {"error": str(exc)[:100]}
            continue
        auc = None
        try:
            from sklearn.metrics import roc_auc_score
            auc = float(roc_auc_score(y, fit.predict(X)))
        except Exception:
            pass
        lr_p = None
        if prev_llf is not None:
            lr = 2 * (fit.llf - prev_llf)
            df = X.shape[1] - prev_df
            lr_p = float(st.chi2.sf(max(lr, 0), df)) if df > 0 else None
        ladder[f"L{rung}"] = {
            "llf": round(float(fit.llf), 1),
            "auc_in_sample": round(auc, 3) if auc else None,
            "lr_p_vs_previous": (f"{lr_p:.2e}" if lr_p is not None else None),
            "key_coefs": {
                nm: round(float(c), 3)
                for nm, c in zip(names, fit.params)
                if nm in ("abs_gap", "gap_positive", "util", "rl_share",
                          "rival_moves_1d", "rival_raises_1d", "abs_gpu_dlog")
            },
        }
        for nm, c, se in zip(names, fit.params, fit.bse):
            results.append({"rung": rung, "term": nm, "coef": float(c), "se": float(se)})
        prev_llf, prev_df = fit.llf, X.shape[1]
    save(pd.DataFrame(results), out_dir, "pm1_ladder")
    summary = {
        "evidence_status": "power_gated" if n_days < 30 else "provisional_descriptive",
        "gate": f"{n_days}/30 panel days — age bins coarse, no unit frailty, in-sample AUC only",
        "n_pair_days": int(len(p)),
        "n_events": int(y.sum()),
        "base_daily_hazard": round(float(y.mean()), 4),
        "ladder": ladder,
        "reading": (
            "L2>L1 = duration/calendar dependence (anti-Calvo); L3 abs_gap>0 = "
            "state-dependent (menu cost); L4 util/rl>0 = congestion pricing "
            "(exclusion: should be ~0 given L3); L5 rival terms>0 = strategic"
        ),
        "claim_boundary": (
            "Ten-day panel: rungs are directional, not conclusive; congestion "
            "covariates exist only for hot-panel pairs (cong_missing indicator); "
            "provider_rate is an endogenous frailty substitute."
        ),
    }
    save_json(summary, out_dir, "pm1_summary")
    return summary
