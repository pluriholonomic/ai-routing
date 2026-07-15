"""BM4 — out-of-sample reaction-rule horse race."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .bm_common import (
    completion_events,
    load_gates,
    provider_cadence,
    temporal_training_cutoff,
)
from .common import DEFAULT_OUT, save, save_json


def link_reactions(
    events: pd.DataFrame,
    cadence: pd.DataFrame,
    *,
    lookback_hours: float = 72,
) -> pd.DataFrame:
    """Attach each repricing to the most recent rival move in the same model."""
    columns = [
        "ts",
        "model_id",
        "provider_name",
        "own_dlog",
        "rival_provider",
        "rival_dlog",
        "lag_hours",
        "gap_to_rival_new",
        "is_fast",
        "fast_x_rival_dlog",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)
    fast = cadence.set_index("provider_name")["is_fast"].to_dict()
    rows = []
    horizon = pd.to_timedelta(float(lookback_hours) * 3600, unit="s")
    for _, group in events.groupby("model_id"):
        ordered = group.sort_values("ts")
        history: list[pd.Series] = []
        for _, event in ordered.iterrows():
            candidates = [
                prior
                for prior in history
                if prior["provider_name"] != event["provider_name"]
                and event["ts"] - prior["ts"] <= horizon
            ]
            if candidates:
                rival = max(candidates, key=lambda item: item["ts"])
                is_fast = int(bool(fast.get(event["provider_name"], False)))
                rows.append(
                    {
                        "ts": event["ts"],
                        "model_id": event["model_id"],
                        "provider_name": event["provider_name"],
                        "own_dlog": event["dlog_price"],
                        "rival_provider": rival["provider_name"],
                        "rival_dlog": rival["dlog_price"],
                        "lag_hours": (event["ts"] - rival["ts"]).total_seconds() / 3600,
                        "gap_to_rival_new": np.log(event["old_price"] / rival["new_price"]),
                        "is_fast": is_fast,
                        "fast_x_rival_dlog": is_fast * rival["dlog_price"],
                    }
                )
            history.append(event)
    return pd.DataFrame(rows, columns=columns).sort_values("ts").reset_index(drop=True)


def _score(train: pd.DataFrame, test: pd.DataFrame, columns: list[str]) -> dict:
    from sklearn.linear_model import HuberRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    if len(train) < max(20, len(columns) * 4) or len(test) < 5:
        return {
            "error": "insufficient temporal holdout",
            "n_train": len(train),
            "n_test": len(test),
        }
    model = HuberRegressor(max_iter=500).fit(train[columns], train["own_dlog"])
    predicted = model.predict(test[columns])
    return {
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "mae": float(mean_absolute_error(test["own_dlog"], predicted)),
        "rmse": float(mean_squared_error(test["own_dlog"], predicted) ** 0.5),
        "coefficients": {
            key: float(value) for key, value in zip(columns, model.coef_, strict=True)
        },
        "intercept": float(model.intercept_),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    events = completion_events()
    cutoff = temporal_training_cutoff(events)
    training_events = events[events["ts"] <= cutoff] if cutoff is not None else events
    cadence = provider_cadence(training_events)
    panel = link_reactions(events, cadence)
    save(panel, out_dir, "bm4_reaction_rules")
    if cutoff is None:
        train, test = panel.iloc[:0], panel
    else:
        train = panel[panel["ts"] <= cutoff]
        test = panel[panel["ts"] > cutoff]
    base_columns = ["gap_to_rival_new"]
    bm_columns = [
        "gap_to_rival_new",
        "rival_dlog",
        "lag_hours",
        "is_fast",
        "fast_x_rival_dlog",
    ]
    baseline = _score(train, test, base_columns)
    brown_mackay = _score(train, test, bm_columns)
    slopes = []
    min_events = load_gates()["brown_mackay"]["min_active_events_per_provider"]
    for provider, group in panel.groupby("provider_name"):
        if len(group) < min_events or group["rival_dlog"].std() == 0:
            continue
        design = np.column_stack([np.ones(len(group)), group["rival_dlog"]])
        coef = np.linalg.lstsq(design, group["own_dlog"], rcond=None)[0]
        slopes.append(
            {
                "provider_name": provider,
                "n_linked_events": int(len(group)),
                "rival_reaction_slope": float(coef[1]),
            }
        )
    save(pd.DataFrame(slopes), out_dir, "bm4_provider_slopes")
    min_linked = load_gates()["brown_mackay"]["min_linked_reactions"]
    summary = {
        "evidence_status": (
            "provisional_descriptive" if len(panel) >= min_linked else "power_gated"
        ),
        "n_linked_reactions": int(len(panel)),
        "min_linked_reactions": min_linked,
        "state_only_holdout": baseline,
        "brown_mackay_holdout": brown_mackay,
        "n_provider_specific_slopes": len(slopes),
        "cadence_training_cutoff": cutoff.isoformat() if cutoff is not None else None,
        "cadence_training_fraction": 0.7,
        "cadence_training_events": int(len(training_events)),
        "claim_boundary": (
            "Cadence classes are frozen on the first 70% of events before the temporal holdout. "
            "The Brown-MacKay feature set winning does not prove strategic observation; both "
            "models omit latent common shocks and costs."
        ),
    }
    save_json(summary, out_dir, "bm4_summary")
    return summary
