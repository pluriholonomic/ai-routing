import pandas as pd

from orcap.analysis.h65_cow_settlement_arrivals import settlement_bins, summarize


def _events(days: int = 7) -> pd.DataFrame:
    base = pd.Timestamp("2026-07-01T00:00:00Z")
    rows = []
    for index in range(days * 24):
        # One settlement per hour and a second at a varying minute: exact transaction
        # identity avoids making the Trade-event batch size the unit of analysis.
        stamp = base + pd.offsets.Hour(index)
        rows.append(
            {"event_type": "settlement", "transaction_hash": f"0x{index:04x}", "event_time": stamp}
        )
        rows.append(
            {
                "event_type": "settlement",
                "transaction_hash": f"0x{index:04x}b",
                "event_time": stamp + pd.offsets.Minute((index % 4) * 3),
            }
        )
        rows.append(
            {"event_type": "trade", "transaction_hash": f"0x{index:04x}", "event_time": stamp}
        )
    return pd.DataFrame(rows)


def test_settlement_bins_deduplicates_transactions_and_keeps_complete_utc_days():
    panel = settlement_bins(_events())
    assert len(panel) == 7 * 96
    assert panel["settlement_count"].sum() == 7 * 24 * 2
    assert panel["bin_start"].dt.tz is not None


def test_h65_is_descriptive_only_after_day_and_settlement_gates():
    result = summarize(settlement_bins(_events()))
    assert result["evidence_status"] == "descriptive_arrival_comparator"
    assert result["n_settlements"] == 336
    assert result["count_model_comparison"]["model_status"] == "ok"
    assert "diurnal_poisson_test_log_likelihood" in result["count_model_comparison"]
    assert "not individual Trade events" in result["claim_boundary"]


def test_h65_short_panel_remains_power_gated():
    result = summarize(settlement_bins(_events(days=1)))
    assert result["evidence_status"] == "power_gated"
    assert result["n_complete_utc_days"] == 1
