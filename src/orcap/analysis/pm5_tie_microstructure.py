"""PM-5 — Tie microstructure: the gap density, tie formation, and focality.

Adapts three collusion-econometrics designs to the 5-min quote panel:
  - Chassang et al. missing-mass logic: pooled density of the relative gap
    to the cheapest quote; an atom at exactly 0 with missing mass at small
    undercuts is the coordination-by-matching signature (competitive
    leapfrogging predicts smooth mass through small undercuts).
  - Tie formation/breaking direction: who moved to create a tie (moving DOWN
    to match = competitive price-matching; a below-min provider moving UP to
    the min = coordination signature), and whether ties break by undercut
    (down) or retreat (up).
  - Knittel-Stango focality: do tie levels sit at the model author's
    first-party price (the salient nonbinding focal point) or round numbers?

  pm5_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)

EPS = 1e-12


def quote_ticks() -> pd.DataFrame:
    return data.q(
        f"""
        select run_ts, model_id, provider_name,
               min(price_completion) as price
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        where price_completion > 0 and model_id not like '%:%'
        group by 1, 2, 3
        """
    ).df()


def gap_density(q: pd.DataFrame) -> dict:
    m = q.groupby(["model_id", "run_ts"])["price"].transform("min")
    n = q.groupby(["model_id", "run_ts"])["price"].transform("size")
    rel = (q["price"] - m) / m
    rel = rel[(n >= 2)]
    nonmin = rel[rel > EPS]
    return {
        "share_ticks_at_exact_min_excl_holder": float(
            ((rel <= EPS).groupby([q["model_id"], q["run_ts"]]).sum() >= 2).mean()
        ),
        "gap_bins_pct": {
            "0_to_0.5": float(((nonmin > 0) & (nonmin <= 0.005)).mean()),
            "0.5_to_2": float(((nonmin > 0.005) & (nonmin <= 0.02)).mean()),
            "2_to_5": float(((nonmin > 0.02) & (nonmin <= 0.05)).mean()),
            "5_to_15": float(((nonmin > 0.05) & (nonmin <= 0.15)).mean()),
            "gt_15": float((nonmin > 0.15).mean()),
        },
        "n_nonmin_obs": int(len(nonmin)),
    }


def tie_events(q: pd.DataFrame) -> pd.DataFrame:
    """Tie formations/breaks at the minimum, with the mover's direction."""
    q = q.sort_values("run_ts")
    events = []
    for model, g in q.groupby("model_id"):
        piv = g.pivot_table(index="run_ts", columns="provider_name", values="price")
        if piv.shape[1] < 2 or len(piv) < 10:
            continue
        mins = piv.min(axis=1)
        tied = piv.eq(mins, axis=0).sum(axis=1) >= 2
        moved = piv.diff()
        for i in range(1, len(piv)):
            if tied.iloc[i] == tied.iloc[i - 1]:
                continue
            movers = moved.iloc[i].dropna()
            movers = movers[movers != 0]
            if len(movers) != 1:  # ambiguous multi-mover ticks skipped
                continue
            events.append(
                {
                    "model_id": model,
                    "kind": "formation" if tied.iloc[i] else "break",
                    "mover_direction": "down" if movers.iloc[0] < 0 else "up",
                }
            )
    return pd.DataFrame(events)


def focality(q: pd.DataFrame) -> dict:
    last = q[q["run_ts"] == q["run_ts"].max()]
    m = last.groupby("model_id")["price"].transform("min")
    n = last.groupby("model_id")["provider_name"].transform("size")
    tied_rows = last[(last["price"] <= m * (1 + 1e-9)) & (n >= 2)]
    tie_levels = tied_rows.groupby("model_id")["price"].first()
    per_mtok = tie_levels * 1e6
    author = {mid: mid.split("/")[0].lower() for mid in tie_levels.index}
    first_party = {}
    for mid, g in last.groupby("model_id"):
        a = author.get(mid)
        if not a:
            continue
        own = g[g["provider_name"].str.lower().str.replace(" ", "").str.contains(a.replace("-", ""), na=False)]
        if len(own):
            first_party[mid] = float(own["price"].min())
    at_fp = [
        mid for mid in tie_levels.index
        if mid in first_party and abs(tie_levels[mid] - first_party[mid]) <= tie_levels[mid] * 1e-6
    ]
    return {
        "n_tied_models_latest_tick": int(len(tie_levels)),
        "share_tie_levels_round_tenth_mtok": float(
            np.isclose(per_mtok * 10, np.round(per_mtok * 10), atol=1e-6).mean()
        )
        if len(per_mtok)
        else None,
        "n_tied_models_with_first_party_quote": int(
            sum(1 for mid in tie_levels.index if mid in first_party)
        ),
        "share_ties_at_first_party_price": (
            len(at_fp) / max(sum(1 for mid in tie_levels.index if mid in first_party), 1)
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    q = quote_ticks()
    ties = tie_events(q)
    formation = ties[ties["kind"] == "formation"] if len(ties) else pd.DataFrame()
    brk = ties[ties["kind"] == "break"] if len(ties) else pd.DataFrame()
    summary = {
        "evidence_status": "provisional_descriptive",
        "gap_density": gap_density(q),
        "tie_formation": {
            "n": int(len(formation)),
            "share_formed_by_downward_move": float((formation["mover_direction"] == "down").mean())
            if len(formation)
            else None,
        },
        "tie_break": {
            "n": int(len(brk)),
            "share_broken_by_downward_move": float((brk["mover_direction"] == "down").mean())
            if len(brk)
            else None,
        },
        "focality": focality(q),
        "signatures": {
            "coordination": "atom at 0 + missing mass at small undercuts; ties formed by "
            "upward moves; ties at first-party focal price; breaks upward",
            "competition": "smooth small-undercut mass; ties formed downward; breaks downward",
        },
        "claim_boundary": (
            "Single-mover tie events only (multi-mover ticks skipped); first-party "
            "matching by author-name heuristic; 5-min grid means sub-tick sequencing "
            "within a tie tick is unobserved."
        ),
    }
    save_json(summary, out_dir, "pm5_summary")
    return summary
