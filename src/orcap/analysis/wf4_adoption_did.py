"""WF-4 — Brown-MacKay technology stage: does one firm's algorithm adoption
raise RIVALS' prices?

B-M theory: superior pricing technology by one firm raises ALL prices in the
unique MPE (commitment asymmetry), with no coordination. Test on the 3-year
LiteLLM direct-price backfill: detect adoption = structural break in a
provider's repricing frequency (Assad marker); event-study rivals' log price
level on shared models around adoption dates.

  wf4_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)

MIN_OBS_PROVIDER = 200
FREQ_RATIO_ADOPT = 3.0  # post/pre change-frequency ratio to call adoption
WINDOW_M = 6  # months around adoption for the event study


def litellm() -> pd.DataFrame:
    glob = data.table_glob("litellm_price_history", layer="external").replace(
        "/*/*.parquet", ".parquet"
    )
    df = data.q(
        f"""
        select litellm_provider as provider, model, cast(obs_date as timestamp) as ts,
               try_cast(output_cost_per_token as double) as price
        from read_parquet('{glob}')
        where try_cast(output_cost_per_token as double) > 0
        """
    ).df()
    # litellm model ids are provider-prefixed ("deepinfra/meta-llama/X"); use the
    # basename for cross-provider matching (coarse but serviceable for v1)
    df["model"] = df["model"].str.split("/").str[-1].str.lower()
    return df.sort_values("ts")


def detect_adoptions(df: pd.DataFrame) -> pd.DataFrame:
    """Provider-level break in monthly repricing frequency (post/pre >= ratio)."""
    df = df.sort_values(["provider", "model", "ts"])
    df["changed"] = df.groupby(["provider", "model"])["price"].diff().abs() > 1e-12
    df["month"] = df["ts"].dt.to_period("M")
    monthly = df.groupby(["provider", "month"])["changed"].sum().reset_index()
    out = []
    for prov, g in monthly.groupby("provider"):
        g = g.sort_values("month").reset_index(drop=True)
        if g["changed"].sum() < 10 or len(g) < 12:
            continue
        best = None
        for k in range(6, len(g) - 6):
            pre = g["changed"].iloc[:k].mean()
            post = g["changed"].iloc[k:].mean()
            if pre >= 0 and post > max(pre, 0.2) * FREQ_RATIO_ADOPT and post >= 2:
                ratio = post / max(pre, 0.1)
                if best is None or ratio > best[1]:
                    best = (g["month"].iloc[k], ratio)
        if best:
            out.append({"provider": prov, "adopt_month": best[0], "freq_ratio": best[1]})
    return pd.DataFrame(out)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = litellm()
    if len(df) < 5000:
        summary = {"evidence_status": "power_gated", "gate": "litellm history unavailable"}
        save_json(summary, out_dir, "wf4_summary")
        return summary
    adopt = detect_adoptions(df)
    if len(adopt) < 3:
        summary = {
            "evidence_status": "power_gated",
            "gate": f"only {len(adopt)}/3 adoption breaks detected",
        }
        save_json(summary, out_dir, "wf4_summary")
        return summary
    df["month"] = df["ts"].dt.to_period("M")
    # monthly median log price per provider-model
    pm = (
        df.groupby(["provider", "model", "month"])["price"].median().reset_index()
    )
    pm["logp"] = np.log(pm["price"])
    effects = []
    for _, a in adopt.iterrows():
        # rivals = other providers sharing >=1 model with the adopter
        adopter_models = set(df[df["provider"] == a["provider"]]["model"])
        riv = pm[(pm["provider"] != a["provider"]) & (pm["model"].isin(adopter_models))]
        pre = riv[
            (riv["month"] >= a["adopt_month"] - WINDOW_M) & (riv["month"] < a["adopt_month"])
        ]
        post = riv[
            (riv["month"] >= a["adopt_month"]) & (riv["month"] < a["adopt_month"] + WINDOW_M)
        ]
        # within provider-model diff to control composition
        j = pre.groupby(["provider", "model"])["logp"].mean().rename("pre").reset_index()
        j = j.merge(
            post.groupby(["provider", "model"])["logp"].mean().rename("post").reset_index(),
            on=["provider", "model"],
        )
        if len(j) < 10:
            continue
        effects.append(
            {
                "adopter": a["provider"],
                "adopt_month": str(a["adopt_month"]),
                "freq_ratio": round(float(a["freq_ratio"]), 1),
                "n_rival_pairs": int(len(j)),
                "rival_dlogp_mean": float((j["post"] - j["pre"]).mean()),
                "rival_dlogp_median": float((j["post"] - j["pre"]).median()),
            }
        )
    if len(effects) < 3:
        summary = {
            "evidence_status": "power_gated",
            "gate": f"only {len(effects)}/3 adoptions with rival panels",
            "adoptions_detected": adopt.to_dict("records"),
        }
        save_json(summary, out_dir, "wf4_summary")
        return summary
    med = float(np.median([e["rival_dlogp_median"] for e in effects]))
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_adoption_events": len(effects),
        "median_rival_dlogp_6m": round(med, 4),
        "events": effects,
        "read": (
            "B-M predicts rival prices RISE after one firm's adoption (positive "
            "dlogp); competitive-diffusion alternative predicts falls (adoption "
            "spreads price cuts)"
        ),
        "claim_boundary": (
            "LiteLLM community-edit timing noise; adoption detection is a frequency "
            "heuristic, not verified software adoption; secular token deflation means "
            "the NULL drift is negative — compare against matched non-event windows "
            "before structural claims (v2). No causal identification."
        ),
    }
    save_json(summary, out_dir, "wf4_summary")
    return summary
