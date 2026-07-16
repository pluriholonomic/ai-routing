from __future__ import annotations

import pandas as pd
import pytest

from orcap.analysis.bm_common import provider_cadence
from orcap.analysis.manuscript_vintages import (
    compare_precommitted_metrics,
    precommitted_metrics,
    registered_vintage_specs,
)
from orcap.analysis.vintage import clip_date_range


def test_registered_vintages_freeze_prefixes_without_partial_confirmatory_run():
    dates = pd.date_range("2026-07-07", periods=10, freq="D")
    specs = registered_vintage_specs(dates)

    assert specs["frozen_9d"]["ready"] is True
    assert specs["frozen_9d"]["start_date"] == "2026-07-07"
    assert specs["frozen_9d"]["end_date"] == "2026-07-15"
    assert specs["confirmatory_30d"]["ready"] is False
    assert specs["confirmatory_30d"]["dates"] == []
    assert specs["confirmatory_30d"]["remaining_days"] == 20


def test_date_clip_is_inclusive_and_rejects_reversed_bounds():
    frame = pd.DataFrame(
        {
            "dt": ["2026-07-07", "2026-07-08", "2026-07-09"],
            "value": [1, 2, 3],
        }
    )
    clipped = clip_date_range(
        frame, start_date="2026-07-08", end_date="2026-07-09"
    )
    assert clipped["value"].tolist() == [2, 3]
    with pytest.raises(ValueError, match="start_date"):
        clip_date_range(
            frame, start_date="2026-07-09", end_date="2026-07-08"
        )


def test_cadence_rate_uses_quote_exposure_not_first_to_last_event_span():
    events = pd.DataFrame(
        {
            "provider_name": ["provider", "provider"],
            "model_id": ["model", "model"],
            "ts": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-11T00:00:00Z"], utc=True
            ),
        }
    )

    event_span = provider_cadence(events).iloc[0]
    quote_exposure = provider_cadence(events, exposure_days=30).iloc[0]

    assert event_span["cadence_class"] == "weekly"
    assert quote_exposure["cadence_class"] == "episodic"
    assert quote_exposure["changes_per_day"] == pytest.approx(2 / 30)

    mapped = provider_cadence(events, exposure_days={"provider": 20}).iloc[0]
    assert mapped["exposure_days"] == 20
    assert mapped["changes_per_day"] == pytest.approx(0.1)


def _results(*, uplift: float, state_rmse: float, brown_rmse: float):
    return {
        "pm1_hazard_baseline": {
            "n_pair_days": 100,
            "n_events": 5,
            "base_daily_hazard": 0.05,
            "ladder": {"L3": {"key_coefs": {"abs_gap": 0.2}}},
        },
        "bm1_pricing_technology": {
            "n_price_changes": 5,
            "n_repricing_providers": 3,
            "cadence_counts": {"intraday": 1, "daily": 1, "episodic": 2},
        },
        "bm2_fast_slow_reactions": {
            "n_independent_waves": 4,
            "fast_response_after_slow_initiator": {
                "n": 9,
                "uplift": uplift,
                "ci95": [-0.1, 0.3],
            },
        },
        "bm3_quality_adjusted_premium": {
            "cadence_only": {"beta_fast": -0.1, "ci95": [-0.2, -0.01]},
            "quality_adjusted": {"beta_fast": -0.2, "ci95": [-0.4, 0.0]},
        },
        "bm4_reaction_rules": {
            "n_linked_reactions": 7,
            "paired_predictive_test": {
                "mse_improvement": 0.01,
                "model_cluster_bootstrap_ci95": [-0.02, 0.03],
                "exact_sign_flip_p_positive": 0.25,
                "verdict": "predictively_indistinguishable",
            },
            "state_only_holdout": {"rmse": state_rmse},
            "brown_mackay_holdout": {"rmse": brown_rmse},
        },
    }


def test_precommitted_metric_set_and_sign_comparison_are_fixed():
    frozen = precommitted_metrics(
        _results(uplift=0.2, state_rmse=0.5, brown_rmse=0.4)
    )
    confirmatory = precommitted_metrics(
        _results(uplift=-0.1, state_rmse=0.5, brown_rmse=0.3)
    )
    comparison = {
        row["metric"]: row
        for row in compare_precommitted_metrics(frozen, confirmatory)
    }

    assert frozen["bm1_fast_share_active"] == pytest.approx(0.5)
    assert frozen["bm4_brown_mackay_rmse_gain"] == pytest.approx(0.1)
    assert frozen["bm4_paired_mse_improvement"] == pytest.approx(0.01)
    assert frozen["bm4_exact_sign_flip_p_positive"] == pytest.approx(0.25)
    assert comparison["bm2_fast_after_slow_uplift"]["sign_preserved"] is False
    assert comparison["bm4_brown_mackay_rmse_gain"]["sign_preserved"] is True
