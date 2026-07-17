from __future__ import annotations

import pandas as pd

from orcap.analysis.h94_cross_router_pass_through import (
    common_shock_matches,
    evidence_summary,
    exact_price_transitions,
    primary_quote_panel,
)


def _quote_panel() -> pd.DataFrame:
    base = pd.Timestamp("2026-07-17T05:00:00Z")
    rows: list[dict[str, object]] = []
    times = {
        "router-a": [base, pd.Timestamp("2026-07-17T05:15:00Z")],
        "router-b": [base, pd.Timestamp("2026-07-17T05:30:00Z")],
    }
    for router, captures in times.items():
        for capture_index, ts in enumerate(captures):
            for provider, input_price, output_price in [
                ("provider-p", 1.0 + 0.2 * capture_index, 2.0 + 0.2 * capture_index),
                ("provider-q", 4.0, 5.0),
            ]:
                rows.append(
                    {
                        "router": router,
                        "run_ts": ts,
                        "ts": ts,
                        "openrouter_model_id": "org/model",
                        "openrouter_hugging_face_id": "org/model",
                        "model_match_status": "exact_unique_official_suffix",
                        "provider_key": provider,
                        "price_input_usd_per_mtok": input_price,
                        "price_output_usd_per_mtok": output_price,
                        "scenario_cost_usd": (input_price * 1000 + output_price * 500)
                        / 1_000_000,
                    }
                )
    return pd.DataFrame(rows)


def test_exact_transitions_and_cross_router_match() -> None:
    primary = primary_quote_panel(_quote_panel())
    events = exact_price_transitions(primary)
    matches = common_shock_matches(events)

    assert len(events) == 2
    assert events["provider_key"].eq("provider-p").all()
    assert len(matches) == 1
    assert matches.iloc[0]["observed_leader"] == "router-a"
    assert matches.iloc[0]["absolute_lag_minutes"] == 15.0


def test_summary_stays_closed_below_prospective_gates() -> None:
    summary, frames = evidence_summary(_quote_panel(), bootstrap_draws=200)

    assert summary["evidence_status"] == "prospective_gate_closed"
    assert summary["observed"]["price_transitions"] == 2
    assert summary["observed"]["matched_common_shocks"] == 1
    assert not all(summary["gates"].values())
    assert len(frames["common_shock_matches"]) == 1
