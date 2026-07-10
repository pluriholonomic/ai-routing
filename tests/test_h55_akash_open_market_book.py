import pandas as pd

from orcap.analysis.h55_akash_open_market_book import coverage_gate, market_book_panel


def test_h55_keeps_native_bid_prices_separate_and_counts_gpu_units():
    shared = {
        "run_ts": "20260710T000000Z",
        "dt": "2026-07-10",
        "snapshot_height": "27652334",
        "snapshot_time": "2026-07-10T09:51:37Z",
    }
    bids = pd.DataFrame(
        [
            shared
            | {
                "bid_id": "b1",
                "provider": "provider-a",
                "gpu_units_total": 2,
                "native_price_amount": 4.5,
                "native_price_denom": "uact",
            }
        ]
    )
    panel = market_book_panel(bids).set_index(["side", "metric"])
    assert panel.loc[("provider_open_bid", "gpu_units_offered"), "value"] == 2.0
    assert panel.loc[("provider_open_bid", "median_native_bid_price"), "value"] == 4.5


def test_h55_requires_repeated_snapshots_before_dynamic_claims():
    empty = coverage_gate(pd.DataFrame())
    assert empty["status"] == "not_identified"
    panel = pd.DataFrame(
        [
            {
                "run_ts": "run-1",
                "dt": "2026-07-10",
                "snapshot_height": "1",
                "side": "provider_open_bid",
            },
        ]
    )
    gate = coverage_gate(panel)
    assert gate["status"] == "power_gated"
    assert gate["bid_snapshots"] == 1
