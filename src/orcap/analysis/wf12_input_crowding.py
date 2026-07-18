"""WF-12 — Input-market crowding: correlated spot sourcing as a cost channel.

Mechanism (registered): providers without owned capacity source demand
overflow on the GPU spot book; correlated bursts make them walk the SAME
book simultaneously, so each one's marginal cost depends on AGGREGATE
overflow (pecuniary externality through the input market). Distinct from
Brown-MacKay commitment: B-M price elevation is invariant to book depth;
crowding scales with (demand correlation x book impact) and is specific to
spot-dependent providers.

First-pass findings encoded here (11-day panel):
  - NO crowding premium in posted prices (within-model class gap ~ 0) — menu
    rigidity absorbs the channel; if crowding binds, it must appear in
    rationing, capacity dynamics, and buffers, i.e. in the FULL price.
  - Rationing interaction is NEGATIVE (spot-dependents ration LESS than
    DC-owners on thin-book days) — rejects naive crowding; consistent with
    ENDOGENOUS THINNING (spot-dependents' sourcing is what thins the book,
    and having sourced they ration less).
  - Sequencing hint: spot-dependent capacity growth correlates with
    PRIOR-day book thinning; DC-owners' does not.

Registered discriminators (gate: 60 joint days): (i) VAR/local projections
of {book impact, class capacity, class rationing, demand}; crowding via
endogenous thinning predicts demand -> gpu_market capacity ^ -> impact ^ ->
(relieved) rationing; (ii) an exogenous book-supply instrument (non-AI
demand for the same GPUs, e.g. rendering/mining proxies) to trace the cost
channel into rationing with the book exogenously thinned.

Formal ancestor: Chitra-Kulkarni-Pai (arXiv:2403.02525) model exactly this
externality among intent-market solvers — simultaneous fulfillment crowds the
same underlying liquidity, and the congestion term makes restricted entry
(interior k*) welfare-preferable to free entry. The inference version needs
three modifications: (i) STOCK congestion — capacity is rented for hours, the
book replenishes slowly, and sourcing is anticipatory rather than
per-request; (ii) menu rigidity — bids cannot carry the congestion cost, so
it routes into rationing/buffers (confirmed: no posted-price channel);
(iii) reputation dynamics (deranking) reward pre-sourcing. Corollary worth
testing: CKP-congestion offers a SECOND explanation for the flat entry law
(congestion-limited entry), discriminated from the long-memory story by
cross-sectional heterogeneity — entry slopes should be flatter for models
whose hardware class has a thinner spot book (higher impact lambda).

  wf12_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)

OWN_DC = (
    "azure", "google", "amazon bedrock", "cloudflare", "digitalocean", "ovh",
    "scaleway", "ibm", "watsonx", "oracle", "vertex", "aws", "alibaba",
    "baidu", "tencent",
)
OWN_SILICON = ("groq", "cerebras", "sambanova")


def provider_class(p: str) -> str:
    pl = p.lower()
    if any(k in pl for k in OWN_DC):
        return "dc_owner"
    if any(k in pl for k in OWN_SILICON):
        return "own_silicon"
    return "gpu_market"


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    imp = None
    curve = Path(out_dir) / "wf11_impact_curve.parquet"
    if curve.exists():
        c = pd.read_parquet(curve)
        imp = c[(c.gpu_class == "H100") & (c.k_gpus == 300)][["dt", "impact_pct"]]
    if imp is None or len(imp) < 6:
        summary = {"evidence_status": "power_gated", "gate": "wf11 impact curve unavailable"}
        save_json(summary, out_dir, "wf12_summary")
        return summary

    cong = data.q(
        f"""
        select model_permaslug, provider_name, substr(run_ts,1,8) as day8,
               sum(try_cast(rate_limited_30m as double)) rl,
               sum(try_cast(request_count_30m as double)) req,
               sum(try_cast(capacity_ceiling_rpm as double)) ceil
        from read_parquet('{data.table_glob("congestion_intraday")}', union_by_name=true)
        group by 1, 2, 3
        """
    ).df()
    cong["dt"] = cong.day8.str[:4] + "-" + cong.day8.str[4:6] + "-" + cong.day8.str[6:8]
    cong["cls"] = cong.provider_name.map(provider_class)
    cong["rl_share"] = (cong.rl / cong.req.clip(lower=1)).clip(0, 1)

    j = cong.merge(imp, on="dt").dropna(subset=["rl_share"])
    j = j[j.req >= 100].copy()
    j["key"] = j.model_permaslug + "|" + j.provider_name
    j["spotdep"] = (j.cls == "gpu_market").astype(float)
    for col in ("rl_share", "impact_pct"):
        j[col + "_dm"] = j[col] - j.groupby("key")[col].transform("mean")
    ldem = np.log(j.req.clip(lower=1))
    j["dem_dm"] = ldem - j.groupby("key")["req"].transform(lambda s: np.log(s.clip(lower=1)).mean())
    X = np.column_stack([j.impact_pct_dm, j.impact_pct_dm * j.spotdep, j.dem_dm, np.ones(len(j))])
    b, *_ = np.linalg.lstsq(X, j.rl_share_dm.to_numpy(), rcond=None)
    rng = np.random.default_rng(12)
    keys = j.key.unique()
    groups = {k: d for k, d in j.groupby("key")}
    draws = []
    for _ in range(200):
        pick = rng.choice(keys, len(keys), replace=True)
        bdf = pd.concat([groups[k] for k in pick])
        Xb = np.column_stack(
            [bdf.impact_pct_dm, bdf.impact_pct_dm * bdf.spotdep, bdf.dem_dm, np.ones(len(bdf))]
        )
        bb, *_ = np.linalg.lstsq(Xb, bdf.rl_share_dm.to_numpy(), rcond=None)
        draws.append(bb[1])
    lo, hi = np.percentile(draws, [2.5, 97.5])

    # capacity sequencing by class
    seq = {}
    agg = cong.groupby(["cls", "dt"]).ceil.sum().reset_index()
    imps = imp.sort_values("dt").assign(dimp=lambda d: d.impact_pct.diff())
    for c in ("gpu_market", "dc_owner"):
        s = agg[agg.cls == c].sort_values("dt").merge(imps, on="dt")
        s = s.assign(dcap=np.log(s.ceil).diff(), dimp_prev=s.dimp.shift(1))
        ok = s.dropna(subset=["dcap", "dimp_prev"])
        if len(ok) >= 5:
            seq[c] = round(float(np.corrcoef(ok.dcap, ok.dimp_prev)[0, 1]), 2)

    summary = {
        "evidence_status": "provisional_descriptive",
        "n_endpoint_days": int(len(j)),
        "class_counts": j.cls.value_counts().to_dict(),
        "rationing_impact_beta_dc_owner_base": round(float(b[0]) * 100, 4),
        "rationing_impact_x_spotdep_pp_per_pt": round(float(b[1]) * 100, 4),
        "interaction_ci95": [round(float(lo) * 100, 4), round(float(hi) * 100, 4)],
        "capacity_growth_vs_prior_day_thinning_corr": seq,
        "read": (
            "naive crowding (interaction > 0) REJECTED at first pass; the negative "
            "interaction + sequencing pattern fit endogenous thinning: spot-dependent "
            "sourcing thins the book and relieves their own rationing. No posted-price "
            "channel exists (within-model class gap ~ 0) — if crowding binds it taxes "
            "the FULL price (rationing/capacity), not the menu."
        ),
        "claim_boundary": (
            "11 joint days; provider capacity classes are name-heuristics (Together/"
            "Fireworks/Baseten own clusters AND rent — the 'gpu_market' class mixes "
            "exposure); fortuna ceilings are router estimates; the VAR and the "
            "exogenous-supply instrument gate at 60 days."
        ),
    }
    save_json(summary, out_dir, "wf12_summary")
    return summary
