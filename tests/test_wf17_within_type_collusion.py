from __future__ import annotations

import pandas as pd

from orcap.analysis import wf17_within_type_collusion as wf17


def _labels() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model_id": "author/model",
                "provider_name": "A",
                "provider_type": "active_undercutter",
            },
            {
                "model_id": "author/model",
                "provider_name": "B",
                "provider_type": "active_undercutter",
            },
            {"model_id": "author/model", "provider_name": "C", "provider_type": "anchor_adopter"},
        ]
    )


def test_response_panel_conditions_on_same_type_and_pairs_placebo():
    changes = pd.DataFrame(
        [
            {
                "ts": pd.Timestamp("2026-01-02T00:00:00Z"),
                "model_id": "author/model",
                "provider_name": "A",
                "old_price": 0.8,
                "new_price": 0.7,
            },
            {
                "ts": pd.Timestamp("2026-01-02T02:00:00Z"),
                "model_id": "author/model",
                "provider_name": "B",
                "old_price": 0.75,
                "new_price": 0.7,
            },
            {
                "ts": pd.Timestamp("2026-01-06T00:00:00Z"),
                "model_id": "author/model",
                "provider_name": "C",
                "old_price": 1.0,
                "new_price": 1.1,
            },
        ]
    )
    author = pd.DataFrame(
        [
            {
                "model_id": "author/model",
                "dt": pd.Timestamp("2026-01-02", tz="UTC"),
                "author_price": 1.0,
            }
        ]
    )
    panel = wf17.build_within_type_response_panel(
        changes,
        _labels(),
        author,
        pd.Timestamp("2026-01-01", tz="UTC"),
        response_hours=12,
        placebo_shift_hours=48,
        anchor_rtol=1e-6,
    )
    assert set(panel.provider_type) == {"active_undercutter"}
    assert set(panel.arm) == {"observed", "shifted_placebo"}
    observed = panel[panel.arm == "observed"]
    assert observed.responded.any()


def test_price_clustering_permutation_detects_frozen_groups():
    rows = []
    for day in pd.date_range("2026-01-01", periods=4, tz="UTC"):
        for provider, _kind, wedge in (
            ("P1", "premium_differentiated", 0.50),
            ("P2", "premium_differentiated", 0.51),
            ("S1", "static_discounter", -0.50),
            ("S2", "static_discounter", -0.51),
        ):
            rows.append(
                {
                    "dt": day,
                    "model_id": "author/model",
                    "provider_name": provider,
                    "log_wedge": wedge,
                }
            )
    quotes = pd.DataFrame(rows)
    labels = quotes[["model_id", "provider_name"]].drop_duplicates()
    labels["provider_type"] = [
        "premium_differentiated",
        "premium_differentiated",
        "static_discounter",
        "static_discounter",
    ]
    cells, summary = wf17.price_clustering_test(
        quotes, labels, permutations=199, seed=7
    )
    assert len(cells) == 8
    assert summary["premium_differentiated"]["observed_mean_pair_distance"] < 0.02
    assert summary["premium_differentiated"]["one_sided_p_more_clustered"] <= 0.05


def test_punishment_panel_separates_competitive_following_and_reversion():
    changes = pd.DataFrame(
        [
            {
                "ts": pd.Timestamp("2026-01-01T00:00:00Z"),
                "model_id": "author/model",
                "provider_name": "A",
                "old_price": 0.8,
                "new_price": 0.7,
            },
            {
                "ts": pd.Timestamp("2026-01-01T02:00:00Z"),
                "model_id": "author/model",
                "provider_name": "B",
                "old_price": 0.75,
                "new_price": 0.69,
            },
            {
                "ts": pd.Timestamp("2026-01-02T00:00:00Z"),
                "model_id": "author/model",
                "provider_name": "B",
                "old_price": 0.69,
                "new_price": 0.75,
            },
            {
                "ts": pd.Timestamp("2026-01-08T00:00:00Z"),
                "model_id": "author/model",
                "provider_name": "C",
                "old_price": 1.0,
                "new_price": 1.1,
            },
        ]
    )
    panel = wf17.build_punishment_panel(
        changes,
        _labels(),
        pd.Timestamp("2026-01-01", tz="UTC"),
        response_hours=24,
        revert_hours=96,
        episode_gap_hours=96,
        reversion_fraction=0.99,
    )
    event = panel[panel.provider_name == "A"].iloc[0]
    assert event.classification == "punish_and_revert_candidate"
    assert event.followers == 1


def test_collusion_scorecard_never_identifies_collusion():
    response = {
        kind: {"cluster_bootstrap_95ci": [0.01, 0.2]} for kind in wf17.TYPE_ORDER
    }
    clustering = {
        kind: {"one_sided_p_more_clustered": 0.001} for kind in wf17.TYPE_ORDER
    }
    memory = {
        kind: {"model_cluster_bootstrap_95ci": [0.001, 0.01]}
        for kind in wf17.TYPE_ORDER
    }
    adjusted = {
        f"{kind}:response": {"holm_p": 0.01} for kind in wf17.TYPE_ORDER
    }
    adjusted.update(
        {f"{kind}:clustering": {"holm_p": 0.01} for kind in wf17.TYPE_ORDER}
    )
    score = wf17.collusion_scorecard(
        response, clustering, memory, pd.DataFrame(), adjusted
    )
    assert all(not row["collusion_identified"] for row in score.values())
    assert score["anchor_adopter"]["excess_clustering_leg"] is False
    assert score["active_undercutter"]["status"] == "multi_proxy_candidate_not_identified"
