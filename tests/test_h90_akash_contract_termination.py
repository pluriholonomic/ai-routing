import json

import pandas as pd

from orcap.analysis.h90_akash_contract_termination import analyze_frames, lifecycle_panel


def _lease(
    execution_id,
    run_ts,
    snapshot_height,
    created_at,
    closed_on,
    state="closed",
):
    return {
        "source": "akash",
        "execution_id": execution_id,
        "run_ts": run_ts,
        "lease_state": state,
        "snapshot_height": snapshot_height,
        "created_at_block": created_at,
        "closed_on_block": closed_on,
        "participant_id": execution_id.split("/")[-2],
        "rate_denom": "uact",
        "rate_amount_native": 5.0,
        "settled_amount_native": 10.0,
        "record_json": json.dumps(
            {"lease": {"created_at": str(created_at), "closed_on": str(closed_on)}}
        ),
    }


def _choice(order, winner, winner_price, loser, loser_price, run_ts, dt):
    choice_set = f"{order}@events:1:1000"
    return [
        {
            "order_id": order,
            "choice_set_id": choice_set,
            "run_ts": run_ts,
            "dt": dt,
            "bid_id": winner,
            "provider": winner.split("/")[-2],
            "native_price_amount": winner_price,
            "native_price_denom": "uact",
            "selected_contract": True,
            "event_window_complete": True,
        },
        {
            "order_id": order,
            "choice_set_id": choice_set,
            "run_ts": run_ts,
            "dt": dt,
            "bid_id": loser,
            "provider": loser.split("/")[-2],
            "native_price_amount": loser_price,
            "native_price_denom": "uact",
            "selected_contract": False,
            "event_window_complete": True,
        },
    ]


def test_h90_keeps_confirmatory_close_outcomes_masked_before_fixed_cutoff():
    pre_high = "tenant-a/1/1/1/provider-a/0"
    pre_low = "tenant-b/2/1/1/provider-b/0"
    future = "tenant-c/3/1/1/provider-c/0"
    future_ineligible = "tenant-d/4/1/1/provider-d/0"
    leases = pd.DataFrame(
        [
            _lease(pre_high, "20260715T000000Z", 1000, 600, 650),
            _lease(pre_low, "20260715T010000Z", 1010, 610, 700),
            _lease(future, "20260716T020000Z", 1100, 1050, 1080),
            _lease(future_ineligible, "20260716T020000Z", 1100, 1030, 1090),
        ]
    )
    close_events = pd.DataFrame(
        [
            {
                "execution_id": pre_high,
                "run_ts": "20260715T000000Z",
                "close_block_height": 650,
                "close_reason": "lease_closed_provider",
                "close_actor_class": "provider",
                "event_scope": "transaction",
            },
            {
                "execution_id": pre_low,
                "run_ts": "20260715T010000Z",
                "close_block_height": 700,
                "close_reason": "lease_closed_owner",
                "close_actor_class": "owner",
                "event_scope": "transaction",
            },
            {
                "execution_id": future,
                "run_ts": "20260716T020000Z",
                "close_block_height": 1080,
                "close_reason": "lease_closed_provider",
                "close_actor_class": "provider",
                "event_scope": "transaction",
            },
            {
                "execution_id": future_ineligible,
                "run_ts": "20260716T020000Z",
                "close_block_height": 1090,
                "close_reason": "lease_closed_provider",
                "close_actor_class": "provider",
                "event_scope": "transaction",
            },
        ]
    )
    bid_events = pd.DataFrame(
        _choice(
            "tenant-a/1/1/1",
            pre_high,
            6.0,
            "tenant-a/1/1/1/loser-a/0",
            5.0,
            "20260715T000000Z",
            "2026-07-15",
        )
        + _choice(
            "tenant-b/2/1/1",
            pre_low,
            5.0,
            "tenant-b/2/1/1/loser-b/0",
            6.0,
            "20260715T010000Z",
            "2026-07-15",
        )
        + _choice(
            "tenant-c/3/1/1",
            future,
            6.0,
            "tenant-c/3/1/1/loser-c/0",
            5.0,
            "20260716T020000Z",
            "2026-07-16",
        )
        + _choice(
            "tenant-d/4/1/1",
            future_ineligible,
            6.0,
            "tenant-d/4/1/1/loser-d/0",
            5.0,
            "20260716T020000Z",
            "2026-07-16",
        )
    )
    choice_bids = pd.DataFrame(
        [
            {"run_ts": "20260715T000000Z", "snapshot_height": 1000},
            {"run_ts": "20260715T010000Z", "snapshot_height": 1010},
            {"run_ts": "20260716T020000Z", "snapshot_height": 1100},
        ]
    )
    source_runs = pd.DataFrame(
        [
            {
                "run_ts": "20260716T013000Z",
                "source": "akash_choice_sets",
                "status": "success",
                "watermark": "1040",
            },
            {
                "run_ts": "20260716T020000Z",
                "source": "akash_choice_sets",
                "status": "success",
                "watermark": "1100",
            },
        ]
    )

    summary, linked, exploratory_risks, confirmatory_risks = analyze_frames(
        leases,
        close_events,
        bid_events,
        choice_bids,
        source_runs,
        now=pd.Timestamp("2026-07-20T00:00:00Z"),
    )

    assert len(linked) == 4
    assert summary["outcomes_released"] is False
    assert summary["exploratory_support"]["linked_multi_provider_leases"] == 2
    assert summary["exploratory_support"]["observed_on_chain_closes"] == 2
    assert summary["exploratory_support"]["exact_close_events"] == 2
    assert len(summary["exploratory_contrasts"]) == 3
    assert summary["confirmatory_support"]["linked_multi_provider_leases"] == 1
    assert summary["post_cutoff_ineligible"] == 1
    assert summary["confirmatory_contrasts"] is None
    assert not exploratory_risks.empty
    assert confirmatory_risks.empty
    by_id = linked.set_index("execution_id")
    assert bool(by_id.loc[future, "confirmatory"]) is True
    assert by_id.loc[future, "preceding_successful_snapshot_height"] == 1040
    assert by_id.loc[future, "post_cutoff_capture_ordinal"] == 2
    assert bool(by_id.loc[future_ineligible, "confirmatory"]) is False
    assert (
        by_id.loc[future_ineligible, "inception_eligibility_reason"]
        == "not_created_after_preceding_snapshot"
    )


def test_h90_never_admits_post_cutoff_lease_without_successful_capture_ledger():
    winner = "tenant-z/9/1/1/provider-z/0"
    leases = pd.DataFrame(
        [_lease(winner, "20260716T030000Z", 1200, 1150, 1180)]
    )
    bid_events = pd.DataFrame(
        _choice(
            "tenant-z/9/1/1",
            winner,
            6.0,
            "tenant-z/9/1/1/loser-z/0",
            5.0,
            "20260716T030000Z",
            "2026-07-16",
        )
    )
    choice_bids = pd.DataFrame(
        [{"run_ts": "20260716T030000Z", "snapshot_height": 1200}]
    )

    summary, linked, _, _ = analyze_frames(
        leases,
        pd.DataFrame(),
        bid_events,
        choice_bids,
        pd.DataFrame(),
        now=pd.Timestamp("2026-07-20T00:00:00Z"),
    )

    assert summary["confirmatory_support"]["linked_multi_provider_leases"] == 0
    assert summary["post_cutoff_ineligible"] == 1
    assert bool(linked.iloc[0]["confirmatory"]) is False
    assert (
        linked.iloc[0]["inception_eligibility_reason"]
        == "missing_successful_capture_ledger"
    )


def test_h90_treats_zero_closed_on_as_open_sentinel_not_observed_close():
    lease_id = "tenant-open/10/1/1/provider-open/0"
    lifecycle = lifecycle_panel(
        pd.DataFrame(
            [
                _lease(
                    lease_id,
                    "20260715T000000Z",
                    1000,
                    600,
                    0,
                    state="active",
                )
            ]
        ),
        pd.DataFrame(),
        pd.DataFrame(),
    )

    assert len(lifecycle) == 1
    assert pd.isna(lifecycle.iloc[0]["closed_on_block"])
    assert bool(lifecycle.iloc[0]["close_event_exact"]) is False
