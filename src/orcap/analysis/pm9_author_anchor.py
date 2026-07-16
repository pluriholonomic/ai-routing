"""PM-9 — Author-price anchoring: active focal-following or launch-and-forget?

PM-5 found an all-market atom of third-party quotes at the model author's
first-party price. Its older selected-tie match statistic was demoted because a
conditional random-label benchmark reproduces it mechanically.
Two explanations with opposite readings:
  active anchoring     third parties track the author's price; when the
                       author repricies, ties re-form at the new level fast
  launch-and-forget    listings copy the author's price at creation and
                       never move; ties are fossils, not coordination

Test: event study on author-provider price changes — do third-party
providers on the same model match the author's NEW price within the window,
vs their base repricing rate? Plus the Musolff resetting screen: hour-of-day
concentration of unilateral RAISES (24h-periodic raises at low-traffic hours
= algorithmic resetting).

  pm9_summary.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save_json
from .h19_provider_types import provider_family, serves_own

log = logging.getLogger(__name__)

WINDOW_H = 96


def all_changes() -> pd.DataFrame:
    df = data.q(
        f"""
        select changed_at_run_ts, model_id, provider_name,
               try_cast(old_value as double) o, try_cast(new_value as double) n
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field = 'price_completion' and model_id not like '%:%'
          and try_cast(old_value as double) > 0 and try_cast(new_value as double) > 0
        """
    ).df()
    df["ts"] = pd.to_datetime(df["changed_at_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    return df.sort_values("ts")


def is_author_provider(model_id: str, provider: str) -> bool:
    author = model_id.split("/")[0].lower()
    return serves_own(provider_family(provider), author)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    ch = all_changes()
    ch["author_move"] = [
        is_author_provider(m, p)
        for m, p in zip(ch["model_id"], ch["provider_name"], strict=True)
    ]
    author_moves = ch[ch["author_move"]]
    panel_end = ch["ts"].max()

    followed, n_eval, lags = 0, 0, []
    for _, e in author_moves.iterrows():
        if e["ts"] + pd.Timedelta(hours=WINDOW_H) > panel_end:
            continue
        n_eval += 1
        others = ch[
            (ch["model_id"] == e["model_id"])
            & (~ch["author_move"])
            & (ch["ts"] > e["ts"])
            & (ch["ts"] <= e["ts"] + pd.Timedelta(hours=WINDOW_H))
        ]
        matches = others[np.isclose(others["n"], e["n"], rtol=1e-6)]
        if len(matches):
            followed += 1
            lags.append(float((matches["ts"].min() - e["ts"]).total_seconds() / 3600))

    # base rate: probability any third-party provider matches ANY given price
    # level in a random window — approximate with the rate of exact-match events
    # among all non-author changes
    non_author = ch[~ch["author_move"]]
    n_models = ch["model_id"].nunique()
    base_rate_per_window = (
        len(non_author) / max(n_models, 1)
        / max((panel_end - ch["ts"].min()).total_seconds() / 3600 / WINDOW_H, 1)
    )

    # Musolff resetting screen: hour-of-day concentration of raises vs cuts
    ch["hour"] = ch["ts"].dt.hour
    raises = ch[ch["n"] > ch["o"]]
    cuts = ch[ch["n"] < ch["o"]]
    def hour_stats(df):
        if len(df) < 20:
            return None
        hc = df["hour"].value_counts(normalize=True)
        ent = float(-(hc * np.log(hc)).sum() / np.log(24))
        return {"n": int(len(df)), "normalized_entropy": round(ent, 3),
                "top_hour": int(hc.idxmax()), "top_hour_share": round(float(hc.max()), 3)}

    summary = {
        "evidence_status": "provisional_descriptive"
        if n_eval >= 10
        else "power_gated",
        "n_author_moves_evaluated": int(n_eval),
        "share_author_moves_matched_within_96h": round(followed / n_eval, 3)
        if n_eval
        else None,
        "match_lag_hours_median": round(float(np.median(lags)), 1) if lags else None,
        "third_party_changes_per_model_per_window_base": round(base_rate_per_window, 3),
        "read": (
            "matched-share >> base activity = active anchoring (third parties track "
            "the author's price); ~0 = launch-and-forget (ties are listing fossils)"
        ),
        "musolff_resetting_screen": {
            "raises": hour_stats(raises),
            "cuts": hour_stats(cuts),
            "read": "raises concentrated at one clock hour (low entropy) = "
            "algorithmic nightly resetting; symmetric entropy = no resetting",
        },
        "claim_boundary": (
            "Author identification uses the shared provider-family alias crosswalk; "
            "exact-price matching at "
            "rtol 1e-6; base rate is a crude per-window activity level, not a "
            "matched counterfactual — the DiD version gates on more author moves."
        ),
    }
    save_json(summary, out_dir, "pm9_summary")
    return summary
