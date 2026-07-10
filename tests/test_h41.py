import pandas as pd

from orcap.analysis import h41_market_comparison as h41
from orcap.analysis.h41_market_comparison import finalized_log_window_coverage, metric_panel


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


def test_geckoterminal_is_an_indexed_amm_control_not_unknown_market():
    panel = metric_panel(
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "geckoterminal",
                    "price_usd": 2000.0,
                    "depth_usd": 1_000_000.0,
                }
            ]
        ),
        pd.DataFrame(),
    )
    assert set(panel["market"]) == {"defi_amm_indexed_control"}


def test_chutes_active_deployment_proxy_is_kept_in_decentralized_compute_market():
    panel = metric_panel(
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "chutes",
                    "participant_id": "chute-1",
                    "resource_kind": "active_configured_gpu",
                    "total": 16.0,
                    "available": None,
                    "used": None,
                }
            ]
        ),
    )
    assert set(panel["market"]) == {"decentralized_compute"}
    assert panel.loc[panel["metric"] == "reported_capacity", "value"].iloc[0] == 16.0


def test_participant_count_does_not_coerce_non_comparable_metadata_into_a_value():
    panel = metric_panel(
        pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "cow",
                    "participant_id": "solver-a",
                    "value": None,
                }
            ]
        ),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    )
    assert set(panel["metric"]) == {"participants"}


def test_h41_does_not_treat_indexed_uniswap_depth_as_finalized_depth(monkeypatch, tmp_path):
    tables = {
        "market_participants": pd.DataFrame(),
        "market_executions": pd.DataFrame(
            [{"dt": "2026-07-10", "source": "cow", "execution_id": "cow-a", "success": True}]
        ),
        "market_quotes": pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "uniswap",
                    "depth_usd": 100.0,
                    "finalized": False,
                }
            ]
        ),
        "market_capacity": pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "akash",
                    "participant_id": "provider-a",
                    "total": 8.0,
                }
            ]
        ),
    }
    monkeypatch.setattr(h41, "_table", lambda name, _columns: tables.get(name, pd.DataFrame()))
    summary = h41.run(tmp_path)
    assert summary["finalized_uniswap_swap_observed"] is False
    assert summary["finalized_uniswap_depth_observed"] is False
    assert "no finalized Uniswap swap" in summary["comparison_status"]


def test_h41_requires_capacity_from_the_compute_market(monkeypatch, tmp_path):
    tables = {
        "market_participants": pd.DataFrame(),
        "market_executions": pd.DataFrame(),
        "market_quotes": pd.DataFrame(),
        "market_capacity": pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "defillama",
                    "participant_id": "not-a-compute-provider",
                    "total": 8.0,
                }
            ]
        ),
    }
    monkeypatch.setattr(h41, "_table", lambda name, _columns: tables.get(name, pd.DataFrame()))
    summary = h41.run(tmp_path)
    assert "no non-null decentralized-compute capacity" in summary["comparison_status"]


def test_h41_labels_fixed_notional_quote_curve_as_distinct_from_depth(monkeypatch, tmp_path):
    tables = {
        "market_participants": pd.DataFrame(),
        "market_executions": pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "uniswap",
                    "execution_id": "swap-a",
                    "success": True,
                    "finalized": True,
                },
                {
                    "dt": "2026-07-10",
                    "source": "cow",
                    "execution_id": "cow-a",
                    "success": True,
                },
            ]
        ),
        "market_quotes": pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "uniswap",
                    "quote_side": "usdc_to_weth_exact_input_simulation",
                    "depth_usd": None,
                    "finalized": True,
                }
            ]
        ),
        "market_capacity": pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "akash",
                    "participant_id": "provider-a",
                    "total": 8.0,
                }
            ]
        ),
    }
    monkeypatch.setattr(h41, "_table", lambda name, _columns: tables.get(name, pd.DataFrame()))
    summary = h41.run(tmp_path)
    assert summary["finalized_uniswap_quote_curve_observed"] is True
    assert summary["finalized_uniswap_depth_observed"] is False
    assert "fixed-notional quote curves" in summary["comparison_status"]


def test_h41_finalized_log_coverage_counts_gaps_between_query_windows():
    coverage = finalized_log_window_coverage(
        pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "uniswap",
                    "detail_json": '{"from_block":100,"to_block":200,"log_query_succeeded":true}',
                },
                {
                    "dt": "2026-07-11",
                    "source": "uniswap",
                    "detail_json": '{"from_block":201,"to_block":300,"log_query_succeeded":true}',
                },
                {
                    "dt": "2026-07-12",
                    "source": "uniswap",
                    "detail_json": '{"from_block":350,"to_block":400,"log_query_succeeded":true}',
                },
                {
                    "dt": "2026-07-12",
                    "source": "uniswap",
                    "detail_json": '{"from_block":401,"to_block":500}',
                },
            ]
        ),
        "uniswap",
    )
    assert coverage["window_count"] == 3
    assert coverage["covered_blocks"] == 252
    assert coverage["uncovered_blocks_between_windows"] == 49
    assert coverage["contiguous_observed"] is False
    assert coverage["observation_days"] == 3
    assert coverage["dynamic_panel_ready"] is False


def test_h41_keeps_usdc_weth_prices_separate_by_fixed_quote_bucket_and_direction():
    panel = metric_panel(
        pd.DataFrame(),
        pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "cow",
                    "execution_id": "buy-1",
                    "success": True,
                    "side": "usdc_to_weth",
                    "price_unit": "usdc_per_weth",
                    "price_usdc_per_weth": 2_000,
                },
                {
                    "dt": "2026-07-10",
                    "source": "cow",
                    "execution_id": "buy-2",
                    "success": True,
                    "side": "usdc_to_weth",
                    "price_unit": "usdc_per_weth",
                    "price_usdc_per_weth": 2_100,
                },
                {
                    "dt": "2026-07-10",
                    "source": "cow",
                    "execution_id": "sell-1",
                    "success": True,
                    "side": "weth_to_usdc",
                    "price_unit": "usdc_per_weth",
                    "price_usdc_per_weth": 1_900,
                },
            ]
        ),
        pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "uniswap",
                    "quote_unit": "usdc_per_weth",
                    "input_bucket_usdc": 100,
                    "price_usdc_per_weth": 2_001,
                },
                {
                    "dt": "2026-07-10",
                    "source": "uniswap",
                    "quote_unit": "usdc_per_weth",
                    "input_bucket_usdc": 1_000,
                    "price_usdc_per_weth": 2_010,
                },
            ]
        ),
        pd.DataFrame(),
    )
    usdc_prices = panel[panel["metric"].str.contains("price_usdc_per_weth")]
    by_cohort = usdc_prices.set_index("cohort")
    assert by_cohort.loc["side:usdc_to_weth", "value"] == 2_050
    assert by_cohort.loc["side:weth_to_usdc", "value"] == 1_900
    assert by_cohort.loc["input_bucket_usdc:100", "value"] == 2_001
    assert by_cohort.loc["input_bucket_usdc:1000", "value"] == 2_010


def test_h41_does_not_pool_fixed_notional_quotes_across_amm_pools():
    panel = metric_panel(
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(
            [
                {
                    "dt": "2026-07-10",
                    "source": "uniswap",
                    "quote_unit": "usdc_per_weth",
                    "pool_id": "0xlowfee",
                    "input_bucket_usdc": 1_000,
                    "price_usdc_per_weth": 2_000,
                },
                {
                    "dt": "2026-07-10",
                    "source": "uniswap",
                    "quote_unit": "usdc_per_weth",
                    "pool_id": "0xhighfee",
                    "input_bucket_usdc": 1_000,
                    "price_usdc_per_weth": 2_020,
                },
            ]
        ),
        pd.DataFrame(),
    )
    quotes = panel[panel["metric"] == "median_quote_price_usdc_per_weth"].set_index("cohort")
    assert set(quotes.index) == {
        "pool:0xlowfee;input_bucket_usdc:1000",
        "pool:0xhighfee;input_bucket_usdc:1000",
    }
    assert quotes.loc["pool:0xlowfee;input_bucket_usdc:1000", "value"] == 2_000
    assert quotes.loc["pool:0xhighfee;input_bucket_usdc:1000", "value"] == 2_020
