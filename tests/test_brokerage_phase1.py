import numpy as np
import pandas as pd

from orcap.analysis.cbh2_gap_curve import gaps
from orcap.analysis.cbh4_reaction_typing import type_event
from orcap.analysis.cbh6_price_forensics import _round_share
from orcap.analysis.cbh12_cold_start import _latest_common_day


def test_gap_curve_computes_two_lowest_gap():
    quotes = pd.DataFrame(
        [
            {"dt": "d1", "model_id": "m", "provider_name": "a", "price": 1.0},
            {"dt": "d1", "model_id": "m", "provider_name": "b", "price": 1.1},
            {"dt": "d1", "model_id": "m", "provider_name": "c", "price": 3.0},
        ]
    )
    g = gaps(quotes)
    assert len(g) == 1
    assert np.isclose(g["gap_pct"].iloc[0], 10.0)
    assert np.isclose(g["range_pct"].iloc[0], 200.0)


def _changes(rows):
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["is_cut"] = df["new_value"] < df["old_value"]
    return df


def test_reaction_typing_distinguishes_revert_from_stick():
    end = pd.Timestamp("2026-01-20", tz="UTC")
    base = [
        {
            "ts": "2026-01-01",
            "model_id": "m",
            "provider_name": "i",
            "old_value": 2.0,
            "new_value": 1.5,
        },
        {
            "ts": "2026-01-02",
            "model_id": "m",
            "provider_name": "r",
            "old_value": 2.0,
            "new_value": 1.6,
        },
    ]
    stick = _changes(base)
    cut = stick.iloc[0]
    assert type_event(cut, stick, end) == "match_and_stick"

    revert = _changes(
        base
        + [
            {
                "ts": "2026-01-04",
                "model_id": "m",
                "provider_name": "r",
                "old_value": 1.6,
                "new_value": 2.0,
            }
        ]
    )
    assert type_event(revert.iloc[0], revert, end) == "punish_and_revert"

    lonely = _changes(base[:1])
    assert type_event(lonely.iloc[0], lonely, end) == "no_response"
    # unobserved window -> None
    assert type_event(cut, stick, pd.Timestamp("2026-01-01 12:00", tz="UTC")) is None


def test_round_share_orders_by_grid_coarseness():
    x = np.array([1.0, 2.5, 0.11, 3.07])
    r = _round_share(x)
    assert r["share_integer"] <= r["share_half"] <= r["share_tenth"] <= r["share_hundredth"]
    assert np.isclose(r["share_integer"], 0.25)
    assert np.isclose(r["share_hundredth"], 1.0)


def test_cold_start_uses_latest_common_quote_and_share_day():
    quotes = pd.DataFrame({"dt": ["2026-07-12", "2026-07-13", "2026-07-14"]})
    shares = pd.DataFrame({"dt": ["2026-07-12", "2026-07-13"]})

    assert _latest_common_day(quotes, shares) == "2026-07-13"
