import numpy as np
import pandas as pd

from orcap.market_env.calibration import classify_pairs, fit_hazard


def synth_prices() -> pd.DataFrame:
    days = [f"2026-07-{d:02d}" for d in range(1, 11)]
    rows = []
    for i, dt in enumerate(days):
        rows.append(dict(dt=dt, model_id="m/x", provider_name="AuthorCo", p=1.0, is_author=True))
        rows.append(dict(dt=dt, model_id="m/x", provider_name="CopyCo", p=1.0, is_author=False))
        rows.append(dict(dt=dt, model_id="m/x", provider_name="CheapCo", p=0.67, is_author=False))
        rows.append(dict(dt=dt, model_id="m/x", provider_name="JitterCo",
                         p=0.60 + 0.01 * (i % 3), is_author=False))
        rows.append(dict(dt=dt, model_id="m/x", provider_name="PremiumCo", p=1.4, is_author=False))
    return pd.DataFrame(rows)


def test_classify_pairs_species():
    pairs = classify_pairs(synth_prices())
    cls = pairs.set_index("provider_name")["anchor_class"].to_dict()
    assert cls["CopyCo"] == "adopter"
    assert cls["CheapCo"] == "below_static"
    assert cls["JitterCo"] == "below_active"
    assert cls["PremiumCo"] == "above"
    assert "AuthorCo" not in cls  # authors excluded from species


def test_classify_pairs_ledger_counts_override():
    # daily medians show zero changes, but the intraday ledger says otherwise
    prices = synth_prices()
    counts = {("m/x", "CheapCo"): 20}
    pairs = classify_pairs(prices, counts)
    cls = pairs.set_index("provider_name")["anchor_class"].to_dict()
    assert cls["CheapCo"] == "below_active"


def test_fit_hazard_returns_bounded_rate():
    prices = synth_prices()
    pairs = classify_pairs(prices)
    h = fit_hazard(prices, pairs)
    assert 0 <= h["base_daily_rate"] <= 1
    assert h["n_pair_days"] > 0
    assert "claim_boundary" in h
