"""Moment harness: score simulated trajectories against the observed panel.

The indirect-inference loop for the market environment: a simulation is
VALIDATED when the same statistics our empirical modules compute on the real
panel, computed by THIS module on the simulated trajectory, match within the
pre-registered thresholds (docs/simulation-moments-preregistration.md).

Neutral trajectory schema (any kernel version can emit it; one row per
provider-epoch):

    epoch          int or date-like (ordinal within run)
    model_id       str
    provider_name  str
    price          float   posted completion price
    is_author      bool
    anchor_class   str     adopter / below_static / below_active / above /
                           author / unclassified
    anchor_price   float   the author's price that epoch
    repriced       bool    changed price vs previous epoch
    flow_share     float   share of the model market's served tokens (optional)
    utilization    float   (optional)
    rationed_share float   (optional)
    profit         float   (optional; for Calvano delta)

Kernel-independent by design: no imports from kernel/routers/strategies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED = ("epoch", "model_id", "provider_name", "price", "is_author",
            "anchor_class", "anchor_price", "repriced")

#: moment -> (observed target, weight). Values COMPUTED from the panel by
#: observed_trajectory()+compute_moments() on the train window (2026-07-18
#: run; frozen in docs/simulation-moments-preregistration.md). Cadences are
#: at DAILY grain (same definition the simulator epochs use). The adopter
#: atom uses the OOS persistence of train-classified adopters (0.834), since
#: simulated epochs are post-classification by construction. flow_elasticity
#: carries weight 0 in the fitted distance: no calibration parameter targets
#: it — it gates separately on sign and order of magnitude.
DEFAULT_TARGETS = {
    "dispersion_max_min_ratio": (1.34, 1.0),
    "dispersion_sd_log_price": (0.068, 1.0),
    "adopter_atom_share": (0.834, 2.0),
    "premium_ladder_below_static": (-0.406, 1.0),
    "premium_ladder_adopter": (0.0, 2.0),
    "premium_ladder_above": (0.344, 1.0),
    "cadence_adopter": (0.0, 0.5),
    "cadence_below_active": (0.444, 1.0),
    "cadence_below_static": (0.0, 0.5),
    "cadence_above": (0.02, 0.5),
    "flow_elasticity": (-0.78, 0.0),
}


def _check(traj: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED if c not in traj.columns]
    if missing:
        raise ValueError(f"trajectory missing columns: {missing}")
    return traj


def compute_moments(traj: pd.DataFrame) -> dict[str, float | None]:
    """The empirical modules' statistics, on a trajectory."""
    t = _check(traj)
    t = t[t.price > 0]
    out: dict[str, float | None] = {}

    per_epoch = t.groupby(["model_id", "epoch"])["price"]
    ratio = per_epoch.max() / per_epoch.min()
    out["dispersion_max_min_ratio"] = float(ratio.mean())
    out["dispersion_sd_log_price"] = float(
        t.groupby(["model_id", "epoch"])["price"]
        .apply(lambda s: np.log(s).std(ddof=0)).mean()
    )

    nonauthor = t[~t.is_author.astype(bool)]
    adopters = nonauthor[nonauthor.anchor_class == "adopter"]
    out["adopter_atom_share"] = (
        float(np.isclose(adopters.price, adopters.anchor_price, rtol=1e-9).mean())
        if len(adopters) else None
    )

    for cls in ("below_static", "adopter", "above", "below_active"):
        g = nonauthor[nonauthor.anchor_class == cls]
        out[f"premium_ladder_{cls}"] = (
            float(np.log(g.price / g.anchor_price).median()) if len(g) else None
        )

    n_epochs = t.groupby(["model_id", "provider_name"])["epoch"].nunique()
    reps = t.groupby(["model_id", "provider_name"])["repriced"].sum()
    cadence = (reps / (n_epochs - 1).clip(lower=1)).rename("cpd").reset_index()
    cls_map = (
        t.groupby(["model_id", "provider_name"])["anchor_class"].first().reset_index()
    )
    cadence = cadence.merge(cls_map, on=["model_id", "provider_name"])
    for cls in ("adopter", "below_active", "below_static", "above"):
        g = cadence[cadence.anchor_class == cls]
        out[f"cadence_{cls}"] = float(g.cpd.mean()) if len(g) else None

    out["flow_elasticity"] = _flow_elasticity(t)
    if "profit" in t.columns and t["profit"].notna().any():
        out["mean_profit_per_provider_epoch"] = float(t["profit"].mean())
    return out


def _flow_elasticity(t: pd.DataFrame) -> float | None:
    """Within-pair demeaned regression of log flow share on log relative
    price (mirrors the empirical flow-elasticity script)."""
    if "flow_share" not in t.columns or t["flow_share"].isna().all():
        return None
    f = t[(t.flow_share > 0) & (t.price > 0)].copy()
    f["rel"] = np.log(f.price) - np.log(
        f.groupby(["model_id", "epoch"])["price"].transform("median")
    )
    f["ls"] = np.log(f.flow_share)
    key = f.model_id + "|" + f.provider_name
    f["rel_dm"] = f.rel - f.groupby(key)["rel"].transform("mean")
    f["ls_dm"] = f.ls - f.groupby(key)["ls"].transform("mean")
    if f["rel_dm"].std() < 1e-9 or len(f) < 30:
        return None
    b = np.polyfit(f["rel_dm"], f["ls_dm"], 1)[0]
    return float(b)


def moment_distance(
    sim: dict[str, float | None],
    targets: dict[str, tuple[float, float]] | None = None,
) -> dict:
    """Weighted squared relative error over FITTED moments + held-out gates."""
    targets = targets or DEFAULT_TARGETS
    total, per, n = 0.0, {}, 0
    for k, (obs, w) in targets.items():
        s = sim.get(k)
        if s is None:
            per[k] = None
            continue
        scale = max(abs(obs), 0.05)
        err = (s - obs) / scale
        per[k] = round(float(err), 3)
        if w > 0:
            total += w * err * err
            n += 1
    gates = {}
    fe = sim.get("flow_elasticity")
    obs_fe = targets.get("flow_elasticity", (None, 0))[0]
    if fe is not None and obs_fe is not None:
        gates["flow_elasticity_sign"] = bool(np.sign(fe) == np.sign(obs_fe))
        gates["flow_elasticity_order"] = bool(abs(obs_fe) / 10 <= abs(fe) <= abs(obs_fe) * 10)
    return {
        "distance": round(total / max(n, 1), 4),
        "relative_errors": per,
        "holdout_gates": gates,
        "n_moments_scored": n,
    }


def calvano_delta(mean_profit: float, pi_nash: float, pi_monopoly: float) -> float | None:
    """Delta = (pi - pi_N) / (pi_M - pi_N); the standard collusion index."""
    if pi_monopoly - pi_nash <= 0:
        return None
    return float((mean_profit - pi_nash) / (pi_monopoly - pi_nash))


def observed_trajectory(dates: list[str] | None = None) -> pd.DataFrame:
    """Build the neutral schema from the REAL panel (daily grain, same
    definitions as the simulator epochs) so observed targets and simulated
    moments are computed by identical code."""
    from ..analysis import data as adata
    from .calibration import _dates, classify_pairs, daily_prices

    dates = dates or _dates()
    prices = daily_prices(dates)
    pairs = classify_pairs(prices)
    cls = pairs.set_index(["model_id", "provider_name"])["anchor_class"]
    anchor = (
        prices[prices.is_author].groupby(["model_id", "dt"])["p"].min()
        .rename("anchor_price").reset_index()
    )
    t = prices.merge(anchor, on=["model_id", "dt"], how="inner").sort_values("dt")
    t["anchor_class"] = [
        "author" if a else cls.get((m, p), "unclassified")
        for m, p, a in zip(t.model_id, t.provider_name, t.is_author)
    ]
    t["prev"] = t.groupby(["model_id", "provider_name"])["p"].shift(1)
    t["repriced"] = (t["p"] - t["prev"]).abs() > 1e-12
    t = t.dropna(subset=["prev"])
    dlist = ",".join(f"'{d}'" for d in dates)
    flows = adata.q(
        f"""
        select cast(dt as varchar) dt,
               regexp_replace(model_permaslug, '-[0-9]{{8}}$', '') as model_permaslug,
               provider_name, sum(total_tokens) tok
        from read_parquet('{adata.table_glob('effective_pricing_daily')}', union_by_name=true)
        where cast(dt as varchar) in ({dlist}) and variant = 'standard'
        group by 1, 2, 3
        """
    ).df()
    flows["flow_share"] = flows.tok / flows.groupby(["model_permaslug", "dt"])["tok"].transform("sum")
    t = t.merge(
        flows[["dt", "model_permaslug", "provider_name", "flow_share"]],
        left_on=["dt", "model_id", "provider_name"],
        right_on=["dt", "model_permaslug", "provider_name"],
        how="left",
    )
    return t.rename(columns={"dt": "epoch", "p": "price"})[
        ["epoch", "model_id", "provider_name", "price", "is_author",
         "anchor_class", "anchor_price", "repriced", "flow_share"]
    ]


def conditional_targets(
    markets: list[str], dates: list[str],
    base: dict[str, tuple[float, float]] | None = None,
) -> tuple[dict[str, tuple[float, float]], float]:
    """Targets computed on the SAME market universe a simulation covers
    (composition-sensitive moments — ladder, dispersion, cadence — differ
    across market subsets; scoring a 4-market sim against global-panel
    targets is apples-to-oranges; see the dated addendum in
    docs/simulation-moments-preregistration.md). The adopter-atom target
    keeps the global OOS value (a within-pair property, composition-robust).
    Returns (targets, observed_author_daily_cadence) — the latter drives the
    simulator's exogenous anchor-walk hazard."""
    base = base or DEFAULT_TARGETS
    t = observed_trajectory(dates)
    tm = t[t.model_id.isin(markets)]
    obs = compute_moments(tm)
    targets = {}
    for k, (v, w) in base.items():
        if k == "adopter_atom_share":
            targets[k] = (v, w)
        elif obs.get(k) is not None:
            targets[k] = (round(float(obs[k]), 4), w)
    authors = tm[tm.is_author.astype(bool)]
    author_cadence = float(authors.repriced.mean()) if len(authors) else 0.0
    return targets, author_cadence


def trajectory_from_epoch_results(
    epochs: list, model_id: str, classes: dict[str, str],
    anchor_prices: list[float], authors: set[str] | None = None,
) -> pd.DataFrame:
    """Adapter: their kernel's EpochResult sequence -> neutral schema."""
    authors = authors or set()
    rows = []
    prev: dict[str, float] = {}
    for i, er in enumerate(epochs):
        total_served = sum(p.served_requests for p in er.providers) or 1
        for p in er.providers:
            rows.append({
                "epoch": i,
                "model_id": model_id,
                "provider_name": p.provider,
                "price": p.quote,
                "is_author": p.provider in authors,
                "anchor_class": classes.get(p.provider, "unclassified"),
                "anchor_price": anchor_prices[i],
                "repriced": (p.provider in prev)
                and abs(p.quote - prev[p.provider]) > 1e-12,
                "flow_share": p.served_requests / total_served,
                "utilization": (p.attempted_requests / p.admitted_capacity)
                if p.admitted_capacity else None,
                "rationed_share": (p.capacity_rejections
                                   / max(p.attempted_requests + p.capacity_rejections, 1)),
                "profit": p.profit,
            })
            prev[p.provider] = p.quote
    return pd.DataFrame(rows)
