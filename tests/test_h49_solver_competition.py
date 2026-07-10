import pandas as pd
import pytest

from orcap.analysis.h49_solver_competition import auction_panel, solver_panel, summarize


def _rows():
    return pd.DataFrame(
        [
            {
                "auction_id": "a1",
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "participant_id": "solver-a",
                "ranking": 1,
                "is_winner": True,
                "competition_score": 100.0,
            },
            {
                "auction_id": "a1",
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "participant_id": "solver-b",
                "ranking": 2,
                "is_winner": False,
                "competition_score": 90.0,
            },
            {
                "auction_id": "a1",
                "run_ts": "20260710T001500Z",
                "dt": "2026-07-10",
                "participant_id": "solver-a",
                "ranking": 1,
                "is_winner": True,
                "competition_score": 100.0,
            },
            {
                "auction_id": "a2",
                "run_ts": "20260710T003000Z",
                "dt": "2026-07-10",
                "participant_id": "solver-a",
                "ranking": 2,
                "is_winner": False,
                "competition_score": 110.0,
            },
            {
                "auction_id": "a2",
                "run_ts": "20260710T003000Z",
                "dt": "2026-07-10",
                "participant_id": "solver-c",
                "ranking": 1,
                "is_winner": True,
                "competition_score": 120.0,
            },
        ]
    )


def test_h49_deduplicates_repeated_latest_snapshot_per_auction_solver():
    auctions = auction_panel(_rows()).set_index("auction_id")
    assert auctions.loc["a1", "candidate_solver_count"] == 2
    assert auctions.loc["a1", "winner_solver_count"] == 1
    assert auctions.loc["a1", "relative_best_second_score_gap"] == pytest.approx(0.1)


def test_h49_keeps_current_auction_order_counts_as_sampled_snapshot_metadata():
    observations = pd.DataFrame(
        [
            {
                "auction_id": "a1",
                "run_ts": "20260710T000000Z",
                "dt": "2026-07-10",
                "candidate_order_count": 17,
                "settlement_transaction_count": 2,
                "auction_span_blocks": 4,
            },
            {
                "auction_id": "a1",
                "run_ts": "20260710T001500Z",
                "dt": "2026-07-10",
                "candidate_order_count": 19,
                "settlement_transaction_count": 3,
                "auction_span_blocks": 4,
            },
        ]
    )
    auction = auction_panel(_rows(), observations).set_index("auction_id").loc["a1"]
    assert auction["candidate_order_count"] == 19
    assert auction["settlement_transaction_count"] == 3
    assert auction["auction_span_blocks"] == 4


def test_h49_solver_frequencies_are_sampled_auction_statistics_only():
    solvers = solver_panel(_rows()).set_index("participant_id")
    assert solvers.loc["solver-a", "sampled_auctions"] == 2
    assert solvers.loc["solver-a", "sampled_wins"] == 1
    assert solvers.loc["solver-a", "sampled_win_rate_given_candidate"] == pytest.approx(0.5)
    assert solvers.loc["solver-a", "sampled_auction_participation_share"] == 1.0


def test_h49_summary_keeps_short_sample_power_gated():
    auctions = auction_panel(_rows())
    solvers = solver_panel(_rows())
    result = summarize(auctions, solvers)
    assert result["evidence_status"] == "power_gated"
    assert "not a market-wide" in result["claim_boundary"]
