"""WF-2 — JRW steering audit: does the router reward PAST undercutting?

Johnson-Rhodes-Wildenbeest (Ecta 2023): steering to the CURRENT lowest price
does not destabilize collusion; granting PERSISTENT future prominence to past
undercutters does. Test which rule OpenRouter runs, from default-routed
probes: probability a provider is selected, as a function of (i) current
price rank, (ii) whether it CUT price in the trailing 7 days.

Static price-steering: selection loads on current rank only.
JRW dynamic steering: past-cut indicator has positive weight given rank.

  wf2_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .blinding import exclude_outcome_blinded
from .common import DEFAULT_OUT, save_json
from .h68_competition import daily_quotes

log = logging.getLogger(__name__)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    probes = data.q(
        f"""
        select observed_at, model_id, selected_provider, study_id
        from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
        where policy = 'openrouter_default' and outcome = 'succeeded'
          and selected_provider is not null
        """
    ).df()
    probes, _ = exclude_outcome_blinded(probes)
    if len(probes) < 100:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(probes)}/100 default probes"}
        save_json(summary, out_dir, "wf2_summary")
        return summary
    probes["ts"] = pd.to_datetime(probes["observed_at"], format="%Y%m%dT%H%M%SZ", utc=True)
    probes["dt"] = probes["ts"].dt.strftime("%Y-%m-%d")
    quotes = daily_quotes()
    cuts = data.q(
        f"""
        select changed_at_run_ts, model_id, provider_name
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion'
          and try_cast(new_value as double) < try_cast(old_value as double)
        """
    ).df()
    cuts["ts"] = pd.to_datetime(cuts["changed_at_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)

    rows = []
    for (model, dt), g in probes.groupby(["model_id", "dt"]):
        q = quotes[(quotes["model_id"] == model) & (quotes["dt"] == dt)]
        if len(q) < 2:
            continue
        q = q.sort_values("price").reset_index(drop=True)
        sel_counts = g["selected_provider"].value_counts()
        t0 = g["ts"].min()
        for rank, r in q.iterrows():
            past_cut = bool(
                len(
                    cuts[
                        (cuts["model_id"] == model)
                        & (cuts["provider_name"] == r["provider_name"])
                        & (cuts["ts"] < t0)
                        & (cuts["ts"] >= t0 - pd.Timedelta(days=7))
                    ]
                )
            )
            rows.append(
                {
                    "model": model,
                    "dt": dt,
                    "provider": r["provider_name"],
                    "rank_pct": rank / max(len(q) - 1, 1),
                    "is_cheapest": rank == 0,
                    "past_cut_7d": past_cut,
                    "n_selected": int(sel_counts.get(r["provider_name"], 0)),
                    "n_probes": int(len(g)),
                }
            )
    df = pd.DataFrame(rows)
    if df.empty or df["past_cut_7d"].nunique() < 2:
        summary = {"evidence_status": "power_gated", "gate": "no rank/past-cut variation in probe join"}
        save_json(summary, out_dir, "wf2_summary")
        return summary
    df["sel_share"] = df["n_selected"] / df["n_probes"].clip(lower=1)
    # selection share on rank + past-cut (rank regression)
    r = df[["sel_share", "rank_pct"]].rank()
    X = np.column_stack(
        [r["rank_pct"], df["past_cut_7d"].astype(float), df["is_cheapest"].astype(float), np.ones(len(df))]
    )
    beta, *_ = np.linalg.lstsq(X, r["sel_share"].to_numpy(), rcond=None)
    by_cell = (
        df.groupby(["is_cheapest", "past_cut_7d"])["sel_share"].mean().round(3).to_dict()
    )
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_provider_model_days": int(len(df)),
        "n_default_probes": int(len(probes)),
        "rank_beta_past_cut_given_rank": round(float(beta[1]), 3),
        "mean_selection_share_by_cell": {str(k): v for k, v in by_cell.items()},
        "read": (
            "positive past-cut beta given current rank = JRW dynamic steering "
            "(collusion-destabilizing); zero = static lowest-price steering "
            "(collusion-neutral, tie-friendly)"
        ),
        "claim_boundary": (
            "One-token probes on hot models; selection shares per model-day are "
            "coarse; provider eligibility (region/context) unmodeled. This audits the "
            "default policy's memory, not its full scoring function."
        ),
    }
    save_json(summary, out_dir, "wf2_summary")
    return summary
