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


def test_capacity_panel_preserves_resource_units_and_does_not_turn_missing_into_zero():
    panel = metric_panel(
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "akash",
                    "participant_id": "gpu-provider",
                    "resource_kind": "gpu",
                    "total": 8,
                    "available": 6,
                    "used": 2,
                },
                {
                    "dt": "2026-07-10",
                    "source": "akash",
                    "participant_id": "registry-only",
                    "resource_kind": "gpu",
                    "total": None,
                    "available": None,
                    "used": None,
                },
            ]
        ),
    )
    gpu = panel[panel["resource_kind"] == "gpu"].set_index("metric")
    assert gpu.loc["reported_capacity", "value"] == 8.0
    assert gpu.loc["reported_utilization", "value"] == 0.25
    assert gpu.loc["capacity_reporting_share", "value"] == 0.5


def test_quote_panel_keeps_quote_unit_with_aggregate_gpu_price():
    panel = metric_panel(
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "akash",
                    "quote_unit": "usd_per_gpu_hour",
                    "price_usd": 2.4,
                    "depth_usd": None,
                }
            ]
        ),
        pd.DataFrame(),
    )
    quote = panel.set_index("metric")
    assert quote.loc["median_quote_price_usd", "value"] == 2.4
    assert quote.loc["median_quote_price_usd", "quote_unit"] == "usd_per_gpu_hour"
