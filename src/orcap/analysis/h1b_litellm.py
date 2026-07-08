"""H1b — Provider-level price dynamics from the LiteLLM archive (2023-2026).

The LiteLLM community price file's git history gives dated DIRECT prices per
(model, provider) — upgrading H1 from model-level to provider-level three
years before our own capture started, and measuring the mover/stayer split
(H18/H19's frailty) directly per provider.

  h1b_provider_dynamics   per provider: repricing rate, cut share, median move
  h1b_summary             market-level rates + most/least active providers
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def load_pairs() -> pd.DataFrame:
    df = data.q(
        f"""
        with obs as (
          select litellm_provider as provider, model, obs_date,
                 output_cost_per_token as p
          from {data.external("litellm_price_history")}
          where output_cost_per_token > 0 and litellm_provider is not null
        )
        select provider, model, obs_date, p,
               lag(p) over (partition by provider, model order by obs_date) prev,
               lag(obs_date) over (partition by provider, model order by obs_date) prev_date
        from obs
        """
    ).df()
    df = df[df["prev"].notna()].copy()
    df["changed"] = df["p"] != df["prev"]
    df["dlog"] = np.log(df["p"] / df["prev"])
    df["gap_days"] = (
        pd.to_datetime(df["obs_date"]) - pd.to_datetime(df["prev_date"])
    ).dt.days.clip(lower=1)
    return df


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = load_pairs()
    if df.empty:
        return {"note": "litellm history not available"}
    g = df.groupby("provider").agg(
        n_pairs=("changed", "size"),
        n_models=("model", "nunique"),
        n_changes=("changed", "sum"),
        exposure_months=("gap_days", lambda s: s.sum() / 30.44),
        cut_share=("dlog", lambda s: float((s[s != 0] < 0).mean()) if (s != 0).any() else np.nan),
        median_abs_move=(
            "dlog",
            lambda s: float(s[s != 0].abs().median()) if (s != 0).any() else np.nan,
        ),
    )
    g["reprices_per_model_month"] = g["n_changes"] / g["exposure_months"].clip(lower=1e-9)
    g = g[g["n_pairs"] >= 50].sort_values("reprices_per_model_month", ascending=False)
    save(g.reset_index(), out_dir, "h1b_provider_dynamics")

    ch = df[df["changed"]]
    results = {
        "n_pairs": int(len(df)),
        "n_providers": int(g.shape[0]),
        "market_share_pairs_changed": float(df["changed"].mean()),
        "market_median_abs_dlog": float(ch["dlog"].abs().median()) if len(ch) else None,
        "market_cut_share": float((ch["dlog"] < 0).mean()) if len(ch) else None,
        "most_active_providers": g.head(8)["reprices_per_model_month"].round(3).to_dict(),
        "least_active_providers": g.tail(8)["reprices_per_model_month"].round(4).to_dict(),
        "mover_stayer_ratio": float(
            g["reprices_per_model_month"].quantile(0.9)
            / max(1e-9, g["reprices_per_model_month"].quantile(0.1))
        ),
    }
    save_json(results, out_dir, "h1b_summary")
    log.info("H1b: %s", results)
    return results
