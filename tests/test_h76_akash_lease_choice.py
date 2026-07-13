import pandas as pd

from orcap.analysis.h76_akash_lease_choice import (
    coverage_gate,
    event_choice_panel,
    retained_choice_panel,
)


def _rows():
    rows = []
    for provider, price, selected in [("cheap", 4.0, False), ("winner", 5.0, True)]:
        rows.append(
            {
                "order_id": "tenant/1/1/1",
                "choice_set_id": "tenant/1/1/1@42",
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "snapshot_height": "42",
                "snapshot_time": "2026-07-10T00:00:00Z",
                "bid_id": f"tenant/1/1/1/{provider}/7",
                "provider": provider,
                "resource_index": 0,
                "native_price_amount": price,
                "native_price_denom": "uact",
                "selected_contract": selected,
                "choice_set_pagination_complete": True,
                "post_selection_query": True,
            }
        )
    return pd.DataFrame(rows)


def test_h76_reports_selection_inside_retained_public_bid_set():
    panel = retained_choice_panel(_rows())

    assert len(panel) == 1
    assert panel.iloc[0]["retained_providers"] == 2
    assert panel.iloc[0]["selected_provider"] == "winner"
    assert panel.iloc[0]["selected_price_rank"] == 2
    assert not panel.iloc[0]["selected_is_lowest_price"]
    assert panel.iloc[0]["selected_price_premium_to_lowest"] == 0.25


def test_h76_remains_power_gated_for_one_retained_choice_set():
    gate = coverage_gate(retained_choice_panel(_rows()))
    assert gate["status"] == "power_gated"
    assert gate["retained_multi_provider_choice_sets"] == 1
    assert "only 1/1000 retained multi-provider choice sets" in gate["gate_reasons"]


def test_h76_event_window_recovers_preselection_losing_bid():
    rows = _rows().drop(
        columns=[
            "snapshot_height",
            "snapshot_time",
            "resource_index",
            "choice_set_pagination_complete",
            "post_selection_query",
        ]
    )
    rows["event_window_end_height_inclusive"] = 42
    rows["event_window_complete"] = True

    panel = event_choice_panel(rows)

    assert len(panel) == 1
    assert panel.iloc[0]["retained_providers"] == 2
    assert panel.iloc[0]["selected_price_rank"] == 2
    assert not panel.iloc[0]["post_selection_query"]
