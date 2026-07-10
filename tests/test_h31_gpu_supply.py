import numpy as np
import pandas as pd

from orcap.analysis.h31_gpu_supply import market_panel, supply_response


def test_gpu_market_panel_uses_offer_book_state_not_raw_offer_count():
    panel = market_panel(
        pd.DataFrame(
            [
                {
                    "run_ts": "20260710T000000Z",
                    "gpu_class": "H100",
                    "offer_type": "on-demand",
                    "dph_total": 2.0,
                    "rented": True,
                },
                {
                    "run_ts": "20260710T000000Z",
                    "gpu_class": "H100",
                    "offer_type": "on-demand",
                    "dph_total": 4.0,
                    "rented": False,
                },
            ]
        )
    )
    assert panel.iloc[0]["n_offers"] == 2
    assert panel.iloc[0]["rented_share"] == 0.5
    assert panel.iloc[0]["median_usd_hr"] == 3.0


def test_gpu_supply_response_recovers_planted_descriptive_response():
    rows = []
    beta = 0.4
    for gpu_index, gpu_class in enumerate(["H100", "H200", "B200"]):
        for hour in range(180):
            share = 0.2 + 0.001 * hour + 0.01 * gpu_index
            price = (1.0 + gpu_index) * np.exp(beta * np.log(share / 0.2))
            rows.append(
                {
                    "run_ts": (pd.Timestamp("2026-07-01", tz="UTC") + pd.Timedelta(hour, unit="h"))
                    .strftime("%Y%m%dT%H%M%SZ"),
                    "gpu_class": gpu_class,
                    "offer_type": "on-demand",
                    "n_offers": 20,
                    "rented_share": share,
                    "median_usd_hr": price,
                    "p25_usd_hr": price * 0.9,
                    "p75_usd_hr": price * 1.1,
                }
            )
    summary, fit = supply_response(pd.DataFrame(rows))
    assert summary["gate"]["passed"] is True
    assert abs(summary["rented_share_price_elasticity"] - beta) < 1e-6
    assert "dlog_rented_share" in set(fit["term"])
