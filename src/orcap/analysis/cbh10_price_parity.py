"""CBH-10 — Price-parity sign test: do providers undercut their own channel?

Hotel-booking MFN literature (Hunold et al. 2018): when price-parity clauses
were banned, hotels priced their *direct* channel strictly below the OTA.
OpenRouter imposes no parity clause, so providers are free to undercut the
router on their own APIs. If they never do — parity holds voluntarily — the
router is not being disciplined by disintermediation on price (its 5.5% is
levied on top without channel competition); systematic direct<router instead
means the MFN-ban equilibrium (router as showroom).

Uses H13's matched router/direct pairs; H13 reports |basis|≈0, this module
reads the SIGN of the nonzero tail and its persistence.

  cbh10_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .common import DEFAULT_OUT, save_json
from .h13_venue_basis import load_direct, load_routed

log = logging.getLogger(__name__)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    routed, direct = load_routed(), load_direct()
    m = routed.merge(direct, on=["dt", "provider", "model_name"], how="inner")
    if m.empty:
        summary = {"evidence_status": "power_gated", "gate": "no matched pairs"}
        save_json(summary, out_dir, "cbh10_summary")
        return summary
    m["diff_pct"] = 100.0 * (m["routed_out"] - m["direct_out"]) / m["direct_out"]
    nz = m[m["diff_pct"].abs() > 0.01]
    persist = None
    if not nz.empty:
        # persistence: share of nonzero (provider, model) pairs keeping one sign all days
        sign_stable = (
            nz.assign(sign=lambda d: d["diff_pct"] > 0)
            .groupby(["provider", "model_name"])["sign"]
            .nunique()
        )
        persist = float((sign_stable == 1).mean())
    summary = {
        "evidence_status": "provisional_descriptive",
        "n_pairs": int(len(m)),
        "share_parity_exact": float((m["diff_pct"].abs() <= 0.01).mean()),
        "share_router_above_direct": float((m["diff_pct"] > 0.01).mean()),
        "share_direct_below_router": float((m["diff_pct"] < -0.01).mean()),
        "nonzero_sign_persistence": persist,
        "read": (
            "near-total exact parity = voluntary MFN (no price discipline from "
            "disintermediation); persistent direct<router = showroom equilibrium"
        ),
        "claim_boundary": (
            "Output-price parity on H13's matched sample (DeepInfra-dominated); "
            "parity on price does not preclude channel competition on rate limits, "
            "priority, or contract terms."
        ),
    }
    save_json(summary, out_dir, "cbh10_summary")
    return summary
