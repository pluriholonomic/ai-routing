import numpy as np
import pandas as pd

from orcap.analysis.h71_model_competition import (
    allocation_metrics,
    explanatory_value,
    latest_complete_app_rows,
)


def test_latest_complete_app_rows_ignores_later_partial_retry():
    rows = pd.DataFrame(
        [
            {"dt": "2026-07-01", "run_ts": "a", "scope": "model", "variant": "standard"}
            for _ in range(4)
        ]
        + [
            {"dt": "2026-07-01", "run_ts": "z", "scope": "model", "variant": "standard"}
        ]
    )
    assert set(latest_complete_app_rows(rows)["run_ts"]) == {"a"}


def test_allocation_metrics_are_normalized_within_observed_top_lists():
    rows = pd.DataFrame(
        [
            {
                "dt": "2026-07-01",
                "model_permaslug": "m1",
                "app_slug": "a",
                "app_title": "A",
                "total_tokens": 80,
                "total_requests": 8,
            },
            {
                "dt": "2026-07-01",
                "model_permaslug": "m1",
                "app_slug": "b",
                "app_title": "B",
                "total_tokens": 20,
                "total_requests": 2,
            },
            {
                "dt": "2026-07-01",
                "model_permaslug": "m2",
                "app_slug": "a",
                "app_title": "A",
                "total_tokens": 20,
                "total_requests": 2,
            },
        ]
    )
    allocations, metrics = allocation_metrics(rows)
    m1 = metrics.set_index("model_permaslug").loc["m1"]
    assert np.isclose(m1["top_app_share_observed"], 0.8)
    assert np.isclose(m1["app_hhi_observed"], 0.68)
    assert np.isclose(m1["app_effective_n_observed"], 1 / 0.68)
    app_a_m1 = allocations.set_index(["model_permaslug", "app_slug"]).loc[("m1", "a")]
    assert np.isclose(app_a_m1["app_model_share_observed"], 0.8)


def test_explanatory_value_uses_out_of_sample_clusters_and_returns_bootstrap_interval():
    rows = []
    for model in range(12):
        for day in range(2):
            lag = 1.0 + model / 10
            shape = (model % 3) / 2
            rows.append(
                {
                    "model_permaslug": f"m{model}",
                    "dt": f"2026-07-0{day + 1}",
                    "next_activity_day": f"2026-07-0{day + 2}",
                    "log_lag_activity_tokens": lag,
                    "app_day_index": float(day),
                    "app_effective_n_observed": 1 + shape,
                    "app_portfolio_competition_observed": shape,
                    "log_app_tokens_observed": lag + shape,
                    "log_next_activity_tokens": 0.4 * lag + 2.0 * shape + 0.1 * day,
                }
            )
    result = explanatory_value(pd.DataFrame(rows))
    assert result["n_models"] == 12
    assert result["n_cluster_bootstrap"] == 1000
    assert result["allocation_shape_oos_r2"] > result["baseline_persistence_oos_r2"]
