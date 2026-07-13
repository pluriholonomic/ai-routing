import numpy as np
import pandas as pd

from orcap.analysis.h68_competition import collapse, day_indicators, fit_factor

DAYS = [f"2026-07-{d:02d}" for d in range(1, 7)]


def _quotes() -> pd.DataFrame:
    """20 synthetic markets: half contested (many providers, wide quotes,
    churning leader), half quiet duopolies with tight, static quotes."""
    rng = np.random.default_rng(7)
    rows = []
    for i in range(10):  # contested
        for dt in DAYS:
            for p in range(6):
                rows.append(
                    {
                        "dt": dt,
                        "model_id": f"open/model-{i}",
                        "provider_name": f"prov-{(p + hash(dt) % 3) % 8}",
                        "price": float(np.exp(rng.normal(0, 0.6))),
                    }
                )
    for i in range(10):  # quiet
        for dt in DAYS:
            for p in range(2):
                rows.append(
                    {
                        "dt": dt,
                        "model_id": f"closed/model-{i}",
                        "provider_name": f"prov-{p}",
                        "price": 1.0 + 0.01 * p,
                    }
                )
    return pd.DataFrame(rows)


def _cuts() -> pd.DataFrame:
    rows = []
    for i in range(10):
        for dt in DAYS[::2]:
            rows.append(
                {
                    "dt": dt,
                    "model_id": f"open/model-{i}",
                    "provider_name": "prov-1",
                    "old_value": "2.0",
                    "new_value": "1.5",
                }
            )
    df = pd.DataFrame(rows)
    df["is_cut"] = True
    df["is_change"] = True
    return df


def test_contested_markets_outrank_quiet_duopolies():
    day = day_indicators(_quotes(), pd.DataFrame(), _cuts())
    models = collapse(day)
    assert len(models) == 20
    scores, loadings = fit_factor(models)
    assert loadings["n_providers"] > 0  # sign convention holds
    open_scores = [scores[f"open/model-{i}"] for i in range(10)]
    closed_scores = [scores[f"closed/model-{i}"] for i in range(10)]
    assert min(open_scores) > max(closed_scores)


def test_day_indicators_tracks_leader_turnover():
    quotes = pd.DataFrame(
        [
            {"dt": "2026-07-01", "model_id": "m", "provider_name": "a", "price": 1.0},
            {"dt": "2026-07-01", "model_id": "m", "provider_name": "b", "price": 2.0},
            {"dt": "2026-07-02", "model_id": "m", "provider_name": "a", "price": 3.0},
            {"dt": "2026-07-02", "model_id": "m", "provider_name": "b", "price": 2.0},
        ]
    )
    day = day_indicators(quotes, pd.DataFrame(), pd.DataFrame())
    turnover = day.sort_values("dt")["best_turnover"].tolist()
    assert np.isnan(turnover[0]) and turnover[1] == 1.0
