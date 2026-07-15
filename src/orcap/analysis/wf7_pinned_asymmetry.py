"""WF-7 — Preferential-treatment screen from pinned probes (C9 kickbacks).

If provider-router compensation flows in non-price dimensions, one visible
form is asymmetric admission: providers granting the router's traffic
preferential rate limits when they are default-favored, or throttling pinned
(non-default) requests differentially. Screen: per provider, 429 rate on
pinned probes vs (i) its default-selection share, (ii) its quoted rank.

  wf7_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    att = data.q(
        f"""
        select policy, model_id, requested_provider, selected_provider, outcome, retry_reason
        from read_parquet('{data.table_glob("router_route_attempts")}', union_by_name=true)
        """
    ).df()
    pinned = att[att["policy"].str.startswith("pinned", na=False)].copy()
    if len(pinned) < 150:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(pinned)}/150 pinned probes"}
        save_json(summary, out_dir, "wf7_summary")
        return summary
    pinned["rejected"] = (pinned["outcome"] == "failed") & (
        pinned["retry_reason"].fillna("").str.contains("429")
    )
    default = att[(att["policy"] == "openrouter_default") & (att["outcome"] == "succeeded")]
    fav = default.groupby(["model_id", "selected_provider"]).size().rename("n_default")
    tot = default.groupby("model_id").size().rename("n_total")

    per = (
        pinned.groupby(["model_id", "requested_provider", "policy"])
        .agg(n=("rejected", "size"), reject_rate=("rejected", "mean"))
        .reset_index()
    )
    per = per.merge(fav, left_on=["model_id", "requested_provider"], right_index=True, how="left")
    per = per.merge(tot, left_on="model_id", right_index=True, how="left")
    per["default_share"] = (per["n_default"].fillna(0) / per["n_total"]).fillna(0)
    per = per[per["n"] >= 8]
    if len(per) < 12:
        summary = {"evidence_status": "power_gated", "gate": f"only {len(per)}/12 provider cells with n>=8"}
        save_json(summary, out_dir, "wf7_summary")
        return summary
    corr = float(per["reject_rate"].rank().corr(per["default_share"].rank()))
    by_policy = per.groupby("policy")["reject_rate"].mean().round(3).to_dict()
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_cells": int(len(per)),
        "n_pinned_probes": int(len(pinned)),
        "mean_reject_rate_by_policy": by_policy,
        "spearman_reject_x_default_share": round(corr, 3),
        "read": (
            "strongly negative correlation = default-favored providers admit the "
            "router's traffic preferentially (a non-price compensation channel "
            "consistent with C9); near zero = admission independent of favor"
        ),
        "claim_boundary": (
            "Our API key's rate limits may differ from market flow; pinned requests "
            "disable fallbacks, which providers may treat differently; small cells."
        ),
    }
    save_json(summary, out_dir, "wf7_summary")
    return summary
