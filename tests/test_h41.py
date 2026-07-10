import pandas as pd

from orcap.analysis.h41_market_comparison import metric_panel


def test_common_metric_panel_keeps_source_and_market_boundaries():
    participants = pd.DataFrame(
        [{"dt": "2026-07-09", "source": "defillama", "participant_id": "u", "value": 2.0}]
    )
    executions = pd.DataFrame([{"dt": "2026-07-09", "source": "cow", "success": True}])
    quotes = pd.DataFrame([{"dt": "2026-07-09", "source": "uniswap", "depth_usd": 4.0}])
    capacity = pd.DataFrame(
        [{"dt": "2026-07-09", "source": "akash", "participant_id": "p", "total": 8.0}]
    )
    panel = metric_panel(participants, executions, quotes, capacity)
    assert set(panel["market"]) == {
        "defi_aggregate",
        "defi_rfq",
        "defi_amm",
        "decentralized_compute",
    }
    assert panel.loc[panel["metric"] == "reported_capacity", "value"].iat[0] == 8.0
