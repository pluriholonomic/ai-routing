"""Calibration bundle for the strategic market environment.

Fits every simulator primitive that CAN be fitted from the captured panel on
a train window (earliest ``train_frac`` of dates) and freezes the result as
an immutable bundle under ``output/market_env/calibration/<rev>/``:

  bundle.json      scalar parameters: species behavior, repricing hazard,
                   rationing slopes, demand process, cost bands, router
                   steering penalty, and the train/holdout date split
  pairs.parquet    per (model, provider) classification and fitted margins
  data_card.md     provenance, claim boundaries, holdout declaration

HOLDOUT DISCIPLINE (pre-registered in docs/simulation-moments-preregistration.md):
the last ``1 - train_frac`` of dates are never touched here, and the
validation moments (flow elasticity, elasticity wedge, dispersion level,
adopter level-persistence) are never fitted anywhere.

Everything here is kernel-independent: it reads parquet through the standard
analysis loader and emits plain dicts/frames that any kernel version (or the
moments harness) can consume.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..analysis import data
from ..analysis.pm9_author_anchor import is_author_provider
from ..analysis.wf13_provider_strata import tier_of, tiers

log = logging.getLogger(__name__)

DEFAULT_OUT = Path("output/market_env/calibration")
ADOPT_SHARE = 0.8
ACTIVE_CHANGES_PER_DAY = 0.05
MIN_DAYS = 5
# router steering: probe-panel selection of cheapest-with-recent-cut vs without
CUT_PENALTY_THETA = round(0.039 / 0.233, 4)
# spot-cost band: tokens per GPU-hour throughput assumptions (per Mtok cost scales 1/x)
THROUGHPUT_BAND_TOK_PER_GPU_HR = (1e6, 3e6, 10e6)
OWNED_TIERS = ("dc_hyperscaler", "own_silicon")


@dataclass(frozen=True)
class SpeciesParams:
    anchor_class: str
    n_pairs: int
    margin_log_median: float
    margin_log_iqr: float
    changes_per_day: float
    rationing_slope: float | None = None


@dataclass
class CalibrationBundle:
    rev: str
    train_dates: list[str]
    holdout_dates: list[str]
    species: dict[str, dict] = field(default_factory=dict)
    hazard: dict = field(default_factory=dict)
    demand: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)
    router: dict = field(default_factory=dict)
    markets: dict[str, dict] = field(default_factory=dict)


def _dates() -> list[str]:
    return sorted(
        data.q(
            f"select distinct cast(dt as varchar) d from "
            f"read_parquet('{data.table_glob('endpoints_snapshots')}', union_by_name=true)"
        ).df()["d"]
    )


def daily_prices(dates: list[str]) -> pd.DataFrame:
    dlist = ",".join(f"'{d}'" for d in dates)
    q = data.q(
        f"""
        select cast(dt as varchar) as dt, model_id, provider_name,
               median(price_completion) as p
        from read_parquet('{data.table_glob('endpoints_snapshots')}', union_by_name=true)
        where price_completion > 0 and model_id not like '%:%'
          and cast(dt as varchar) in ({dlist})
        group by 1, 2, 3
        """
    ).df()
    q["is_author"] = [
        is_author_provider(m, p) for m, p in zip(q["model_id"], q["provider_name"], strict=True)
    ]
    return q


def _intraday_change_counts(dates: list[str]) -> dict[tuple[str, str], int]:
    """Repricing counts from the SCD-2 ledger (catches micro-adjusters that
    daily medians smooth over)."""
    dlist8 = ",".join(f"'{d.replace('-', '')}'" for d in dates)
    try:
        ch = data.q(
            f"""
            select model_id, provider_name, count(*) n
            from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
            where field = 'price_completion'
              and substr(changed_at_run_ts, 1, 8) in ({dlist8})
            group by 1, 2
            """
        ).df()
    except Exception as e:
        log.warning("pricing_changes unavailable for cadence: %s", e)
        return {}
    return {(r.model_id, r.provider_name): int(r.n) for r in ch.itertuples()}


def classify_pairs(prices: pd.DataFrame, ledger_counts: dict | None = None) -> pd.DataFrame:
    """wf13 classification rules recomputed on the train window only."""
    anchor = (
        prices[prices.is_author].groupby(["model_id", "dt"])["p"].min()
        .rename("p_anchor").reset_index()
    )
    j = prices[~prices.is_author].merge(anchor, on=["model_id", "dt"])
    j["at_anchor"] = np.isclose(j["p"], j["p_anchor"], rtol=1e-9)
    j["rel"] = np.log(j["p"] / j["p_anchor"])
    ledger_counts = ledger_counts or {}
    rows = []
    for (m, prov), g in j.groupby(["model_id", "provider_name"]):
        g = g.sort_values("dt")
        if g["dt"].nunique() < MIN_DAYS:
            continue
        changes = ledger_counts.get(
            (m, prov), int((g["p"].diff().abs() > 1e-12).sum())
        )
        cpd = changes / max(g["dt"].nunique() - 1, 1)
        share_at = float(g["at_anchor"].mean())
        med = float(g["rel"].median())
        if share_at >= ADOPT_SHARE:
            cls = "adopter"
        elif med < 0:
            cls = "below_active" if cpd > ACTIVE_CHANGES_PER_DAY else "below_static"
        else:
            cls = "above"
        rows.append({
            "model_id": m, "provider_name": prov, "anchor_class": cls,
            "margin_log_median": med,
            "margin_log_iqr": float(g["rel"].quantile(0.75) - g["rel"].quantile(0.25)),
            "changes_per_day": round(cpd, 4),
            "share_days_at_anchor": round(share_at, 3),
            "n_days": int(g["dt"].nunique()),
        })
    return pd.DataFrame(rows)


def fit_hazard(prices: pd.DataFrame, pairs: pd.DataFrame | None = None) -> dict:
    """Logit of daily reprice on |gap to best rival| and gap sign, with
    species fixed effects (the pooled fit is dominated by rigid adopters and
    flips the gap sign otherwise). Duration dropped: on a thin panel the
    deterministic duration counter quasi-separates."""
    import statsmodels.api as sm

    p = prices.sort_values("dt").copy()
    grp = p.groupby(["model_id", "dt"])["p"]
    m1 = grp.transform("min")
    m2 = grp.transform(lambda s: s.nsmallest(2).iloc[-1] if len(s) > 1 else np.nan)
    p["min_rival"] = np.where(np.isclose(p["p"], m1), m2, m1)
    p = p.dropna(subset=["min_rival"]).copy()
    p["gap"] = np.log(p["p"] / p["min_rival"])
    p["prev"] = p.groupby(["model_id", "provider_name"])["p"].shift(1)
    p["repriced"] = (p["p"] - p["prev"]).abs() > 1e-12
    p = p.dropna(subset=["prev"]).copy()
    names = ["const", "abs_gap", "gap_positive"]
    cols = [p["gap"].abs().to_numpy(), (p["gap"] > 0).astype(float).to_numpy()]
    if pairs is not None and len(pairs):
        cls = pairs.set_index(["model_id", "provider_name"])["anchor_class"]
        p["cls"] = [
            cls.get((m, pr), "unclassified")
            for m, pr in zip(p["model_id"], p["provider_name"], strict=True)
        ]
        for c in ("adopter", "below_active", "above"):
            names.append(f"fe_{c}")
            cols.append((p["cls"] == c).astype(float).to_numpy())
    X = sm.add_constant(np.column_stack(cols))
    try:
        fit = sm.Logit(p["repriced"].astype(float), X).fit_regularized(
            alpha=1e-4, disp=0
        )
        coefs = dict(zip(names, fit.params, strict=True))
    except Exception as e:  # separation on thin panels — keep bands honest
        log.warning("hazard fit failed: %s", e)
        coefs = {}
    return {
        "coefs": {k: round(float(v), 4) for k, v in coefs.items()},
        "base_daily_rate": round(float(p["repriced"].mean()), 5),
        "n_pair_days": int(len(p)),
        "claim_boundary": (
            "thin daily panel with light ridge penalty; species FEs absorb the "
            "rigid-adopter mass; treat as bands and refit at the 30-day vintage"
        ),
    }


def fit_rationing(dates: list[str], pairs: pd.DataFrame) -> dict[str, float]:
    dlist = ",".join(f"'{d}'" for d in dates)
    c = data.q(
        f"""
        select model_permaslug, provider_name,
               sum(try_cast(rate_limited_30m as double)) rl,
               sum(try_cast(request_count_30m as double)) req,
               max(try_cast(recent_peak_rpm as double)) peak,
               max(try_cast(capacity_ceiling_rpm as double)) ceil,
               cast(dt as varchar) dt
        from read_parquet('{data.table_glob('congestion_intraday')}', union_by_name=true)
        where cast(dt as varchar) in ({dlist})
        group by model_permaslug, provider_name, cast(dt as varchar)
        """
    ).df()
    c = c[(c.req >= 100) & (c.ceil > 0)]
    c["rl_share"] = (c.rl / c.req.clip(lower=1)).clip(0, 1)
    c["util"] = (c.peak / c.ceil).clip(0, 2)
    cls = pairs.set_index("provider_name")["anchor_class"].to_dict()
    c["cls"] = c.provider_name.map(cls)
    out = {}
    for k, g in c.dropna(subset=["cls"]).groupby("cls"):
        if len(g) >= 20 and g["util"].std() > 0:
            out[k] = round(float(np.polyfit(g["util"], g["rl_share"], 1)[0]), 4)
    return out


def fit_demand(dates: list[str]) -> dict:
    dlist = ",".join(f"'{d}'" for d in dates)
    e = data.q(
        f"""
        select model_permaslug, cast(dt as varchar) dt, sum(total_tokens) tok
        from read_parquet('{data.table_glob('effective_pricing_daily')}', union_by_name=true)
        where cast(dt as varchar) in ({dlist}) and variant = 'standard'
        group by 1, 2
        """
    ).df()
    per_model, ar1s, sigmas = {}, [], []
    for m, g in e.groupby("model_permaslug"):
        g = g.sort_values("dt")
        lv = np.log(g["tok"].clip(lower=1))
        per_model[m] = {"log_level_mean": round(float(lv.mean()), 3), "n_days": len(g)}
        if len(lv) >= 6 and lv.std() > 0:
            r = float(np.corrcoef(lv[1:], lv[:-1])[0, 1])
            ar1s.append(r)
            sigmas.append(float(lv.diff().dropna().std()))
    prof = data.q(
        f"""
        select cast(substr(run_ts, 10, 2) as int) hr,
               sum(try_cast(request_count_30m as double)) req
        from read_parquet('{data.table_glob('congestion_intraday')}', union_by_name=true)
        where cast(dt as varchar) in ({dlist})
        group by 1 order by 1
        """
    ).df()
    shape = (prof.req / prof.req.mean()).round(3).tolist() if len(prof) == 24 else []
    return {
        "ar1_median": round(float(np.median(ar1s)), 3) if ar1s else None,
        "sigma_dlog_median": round(float(np.median(sigmas)), 3) if sigmas else None,
        "intraday_shape_24h": shape,
        "per_model_log_level": per_model,
    }


def fit_costs(dates: list[str], pairs: pd.DataFrame) -> dict:
    dlist = ",".join(f"'{d}'" for d in dates)
    reg = tiers()
    pair_tiers = {
        p: tier_of(p, reg) for p in pairs["provider_name"].unique()
    }
    dph = data.q(
        f"""
        select median(try_cast(dph_base as double)) dph
        from read_parquet('{data.table_glob('gpu_offers_snapshots')}', union_by_name=true)
        where cast(dt as varchar) in ({dlist}) and offer_type = 'on-demand'
          and gpu_name like '%H100%'
        """
    ).df()["dph"].iloc[0]
    spot_band = {
        f"tok_per_gpu_hr_{int(t/1e6)}M": round(float(dph) / (t / 1e6), 3)
        for t in THROUGHPUT_BAND_TOK_PER_GPU_HR
    } if pd.notna(dph) else {}
    return {
        "h100_dph_median": round(float(dph), 3) if pd.notna(dph) else None,
        "spot_cost_per_mtok_band": spot_band,
        "owned_capacity_cost_band_frac_of_min_price": [0.05, 0.25],
        "owned_tiers": list(OWNED_TIERS),
        "provider_tiers": pair_tiers,
        "claim_boundary": (
            "costs are identified sets, not points; every experiment reruns at "
            "band endpoints (execution-plan stop/go rules)"
        ),
    }


def market_snapshots(prices: pd.DataFrame, pairs: pd.DataFrame, top_n: int = 4) -> dict:
    """Initial menus for the most multi-homed model markets in the train window."""
    last = prices[prices.dt == prices.dt.max()]
    counts = last.groupby("model_id")["provider_name"].nunique().sort_values(ascending=False)
    with_author = set(prices[prices.is_author]["model_id"])
    picks = [m for m in counts.index if m in with_author][:top_n]
    out = {}
    for m in picks:
        g = last[last.model_id == m]
        anchor = g[g.is_author]["p"].min()
        cls = pairs[pairs.model_id == m].set_index("provider_name")["anchor_class"].to_dict()
        out[m] = {
            "anchor_price": float(anchor),
            "providers": {
                r.provider_name: {
                    "price": float(r.p),
                    "is_author": bool(r.is_author),
                    "anchor_class": cls.get(
                        r.provider_name, "author" if r.is_author else "unclassified"
                    ),
                }
                for r in g.itertuples()
            },
        }
    return out


def fit(out_dir: Path = DEFAULT_OUT, train_frac: float = 0.6) -> CalibrationBundle:
    dates = _dates()
    cut = max(int(len(dates) * train_frac), 1)
    train, holdout = dates[:cut], dates[cut:]
    prices = daily_prices(train)
    pairs = classify_pairs(prices, _intraday_change_counts(train))
    species = {}
    for cls, g in pairs.groupby("anchor_class"):
        species[cls] = asdict(SpeciesParams(
            anchor_class=cls,
            n_pairs=len(g),
            margin_log_median=round(float(g["margin_log_median"].median()), 4),
            margin_log_iqr=round(float(g["margin_log_iqr"].median()), 4),
            changes_per_day=round(float(g["changes_per_day"].mean()), 4),
        ))
    rationing = fit_rationing(train, pairs)
    for cls, slope in rationing.items():
        if cls in species:
            species[cls]["rationing_slope"] = slope
    rev = hashlib.blake2b(
        json.dumps([train, sorted(species)], sort_keys=True).encode(), digest_size=6
    ).hexdigest()
    bundle = CalibrationBundle(
        rev=rev,
        train_dates=train,
        holdout_dates=holdout,
        species=species,
        hazard=fit_hazard(prices, pairs),
        demand=fit_demand(train),
        cost=fit_costs(train, pairs),
        router={
            "policy": "openrouter_inverse_square",
            "cut_penalty_theta": CUT_PENALTY_THETA,
            "source": "probe panel: cheapest-with-recent-cut 3.9% vs 23.3%",
        },
        markets=market_snapshots(prices, pairs),
    )
    d = Path(out_dir) / rev
    d.mkdir(parents=True, exist_ok=True)
    (d / "bundle.json").write_text(json.dumps(asdict(bundle), indent=1))
    pairs.to_parquet(d / "pairs.parquet", index=False)
    (d / "data_card.md").write_text(
        f"# Calibration bundle {rev}\n\n"
        f"Train: {train[0]}..{train[-1]} ({len(train)} dates); "
        f"holdout: {holdout[0] if holdout else '-'}..{holdout[-1] if holdout else '-'} "
        f"({len(holdout)} dates, never read here).\n\n"
        "Held-out validation moments (never fitted anywhere): flow elasticity, "
        "elasticity wedge, dispersion level, adopter level-persistence.\n\n"
        "Species classification recomputed on train window with wf13 rules "
        f"(ADOPT_SHARE={ADOPT_SHARE}, active threshold {ACTIVE_CHANGES_PER_DAY}/day, "
        f"MIN_DAYS={MIN_DAYS}). Costs are identified sets. Hazard coefficients are "
        "bands (thin panel). Router cut-penalty from the randomized probe panel.\n"
    )
    log.info("calibration bundle %s -> %s", rev, d)
    return bundle


def load(rev: str, out_dir: Path = DEFAULT_OUT) -> dict:
    return json.loads((Path(out_dir) / rev / "bundle.json").read_text())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    b = fit()
    print(json.dumps({"rev": b.rev, "species": b.species, "hazard": b.hazard["coefs"],
                      "markets": list(b.markets)}, indent=1))
