"""BM2 — do fast pricing technologies react disproportionately to slow rivals?"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .bm_common import completion_events, independent_waves, load_gates
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes


def build_reaction_panel(
    events: pd.DataFrame,
    quotes: pd.DataFrame,
    cadence: pd.DataFrame,
    *,
    independence_hours: float = 6,
    response_hours: float = 24,
) -> pd.DataFrame:
    """Risk-set event study with an equal-length pre-event placebo window."""
    columns = [
        "wave_ts",
        "dt",
        "model_id",
        "initiator",
        "initiator_class",
        "responder",
        "responder_class",
        "responded",
        "placebo_move",
        "response_lag_hours",
        "same_direction",
    ]
    if events.empty or quotes.empty or cadence.empty:
        return pd.DataFrame(columns=columns)
    waves = independent_waves(events, independence_hours)
    classes = cadence.set_index("provider_name")["cadence_class"].to_dict()
    by_pair = {
        key: group.sort_values("ts")
        for key, group in events.groupby(["model_id", "provider_name"])
    }
    active = quotes.groupby(["model_id", "dt"])["provider_name"].unique().to_dict()
    response_delta = pd.to_timedelta(float(response_hours) * 3600, unit="s")
    rows = []
    for wave in waves.itertuples(index=False):
        day = str(wave.dt)
        providers = active.get((wave.model_id, day), [])
        for responder in providers:
            if responder == wave.provider_name:
                continue
            history = by_pair.get((wave.model_id, responder))
            if history is None:
                post = pre = pd.DataFrame()
            else:
                post = history[
                    (history["ts"] > wave.ts) & (history["ts"] <= wave.ts + response_delta)
                ]
                pre = history[
                    (history["ts"] < wave.ts) & (history["ts"] >= wave.ts - response_delta)
                ]
            response = post.iloc[0] if not post.empty else None
            rows.append(
                {
                    "wave_ts": wave.ts,
                    "dt": day,
                    "model_id": wave.model_id,
                    "initiator": wave.provider_name,
                    "initiator_class": classes.get(wave.provider_name, "inactive"),
                    "responder": responder,
                    "responder_class": classes.get(responder, "inactive"),
                    "responded": int(response is not None),
                    "placebo_move": int(not pre.empty),
                    "response_lag_hours": (
                        (response["ts"] - wave.ts).total_seconds() / 3600
                        if response is not None
                        else np.nan
                    ),
                    "same_direction": (
                        int(response["direction"] == wave.direction)
                        if response is not None
                        else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _contrast(panel: pd.DataFrame, mask: pd.Series) -> dict:
    group = panel[mask]
    if group.empty:
        return {"n": 0, "post_rate": None, "placebo_rate": None, "uplift": None, "ci95": None}
    delta = group["responded"].to_numpy(float) - group["placebo_move"].to_numpy(float)
    mean = float(delta.mean())
    rng = np.random.default_rng(20260716)
    draws = [float(rng.choice(delta, size=len(delta), replace=True).mean()) for _ in range(500)]
    return {
        "n": int(len(group)),
        "post_rate": round(float(group["responded"].mean()), 4),
        "placebo_rate": round(float(group["placebo_move"].mean()), 4),
        "uplift": round(mean, 4),
        "ci95": [round(float(value), 4) for value in np.percentile(draws, [2.5, 97.5])],
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    events = completion_events()
    quotes = daily_quotes()
    cadence_path = out_dir / "bm1_provider_cadence.parquet"
    if cadence_path.exists():
        cadence = pd.read_parquet(cadence_path)
    else:
        from .bm_common import provider_cadence

        cadence = provider_cadence(events, set(quotes["provider_name"].dropna()))
    gate = load_gates()["brown_mackay"]
    panel = build_reaction_panel(
        events,
        quotes,
        cadence,
        independence_hours=gate["independence_window_hours"],
        response_hours=gate["response_window_hours"],
    )
    save(panel, out_dir, "bm2_reaction_panel")
    fast = (
        panel["responder_class"].isin(["intraday", "daily"])
        if not panel.empty
        else pd.Series(dtype=bool)
    )
    slow_init = (
        panel["initiator_class"].isin(["weekly", "episodic"])
        if not panel.empty
        else pd.Series(dtype=bool)
    )
    focal = (
        _contrast(panel, fast & slow_init)
        if not panel.empty
        else _contrast(panel, pd.Series(dtype=bool))
    )
    slow_response = (
        _contrast(panel, ~fast & slow_init)
        if not panel.empty
        else _contrast(panel, pd.Series(dtype=bool))
    )
    n_waves = int(panel[["wave_ts", "model_id", "initiator"]].drop_duplicates().shape[0])
    ready = n_waves >= gate["min_independent_waves"] and focal["n"] >= gate["min_slow_risk_pairs"]
    summary = {
        "evidence_status": "provisional_descriptive" if ready else "power_gated",
        "n_independent_waves": n_waves,
        "n_risk_pairs": int(len(panel)),
        "fast_response_after_slow_initiator": focal,
        "slow_response_after_slow_initiator": slow_response,
        "gate": {
            "min_independent_waves": gate["min_independent_waves"],
            "min_slow_risk_pairs": gate["min_slow_risk_pairs"],
        },
        "claim_boundary": (
            "Post-versus-pre movement is an event-study screen, not causal evidence. Common "
            "cost, author-price, or demand news can move both providers; BM4 adds state controls."
        ),
    }
    save_json(summary, out_dir, "bm2_summary")
    return summary
