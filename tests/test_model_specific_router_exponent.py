import numpy as np
import pandas as pd

from orcap.analysis.model_specific_router_exponent import (
    _read_owned_attempts,
    fit_cells,
    heterogeneity_test,
    partial_pool,
    price_support,
)
from orcap.analysis.router_exponent import probabilities


def _synthetic_models(seed: int = 19):
    rng = np.random.default_rng(seed)
    rows = []
    for model, eta in (("model-a", 1.0), ("model-b", 2.8)):
        for index in range(900):
            spread = 1.1 + 0.9 * ((index % 31) / 30)
            costs = np.array([1.0, spread, spread**2])
            selected = int(rng.choice(3, p=probabilities(costs, eta)))
            rows.append(
                {
                    "task_id": f"{model}-{index}",
                    "block_id": f"{model}-block-{index // 3}",
                    "model_id": model,
                    "shape_id": "short_chat",
                    "providers": ["p0", "p1", "p2"],
                    "costs": costs,
                    "selected_provider": f"p{selected}",
                    "selected_index": selected,
                }
            )
    return rows


def test_model_specific_slopes_recover_heterogeneity_and_partial_pool():
    rows = _synthetic_models()
    estimates = fit_cells(rows, bootstrap_draws=0)
    values = estimates.set_index("model_id")["eta_price_only"]
    assert abs(values["model-a"] - 1.0) < 0.25
    assert abs(values["model-b"] - 2.8) < 0.30
    pooled, summary = partial_pool(estimates)
    assert summary["cells"] == 2
    assert pooled["eta_partially_pooled"].notna().all()
    test = heterogeneity_test(rows, pooled)
    assert test["p_value"] < 0.01


def test_equal_price_menu_is_flagged_as_unidentified():
    rows = []
    for index in range(30):
        rows.append(
            {
                "task_id": f"task-{index}",
                "block_id": f"block-{index}",
                "model_id": "flat",
                "shape_id": "short_chat",
                "providers": ["a", "b", "c"],
                "costs": np.ones(3),
                "selected_provider": "a",
                "selected_index": 0,
            }
        )
    diagnostics = price_support(rows)
    assert diagnostics["median_within_menu_log_price_sd"] == 0
    estimates = fit_cells(rows, bootstrap_draws=0)
    assert "within_menu_price_contrast" in estimates.iloc[0]["price_only_failures"]
    assert estimates.iloc[0]["score_adjusted_status"] == (
        "not_identified_from_provider_fixed_effects"
    )


def test_attempt_reader_excludes_unrelated_blinded_studies(tmp_path):
    path = tmp_path / "curated" / "router_route_attempts" / "dt=2026-07-22"
    path.mkdir(parents=True)
    pd.DataFrame(
        {
            "study_id": ["openrouter-market-measurement-v1", "blinded-other-study"],
            "selected_provider": ["A", "SECRET"],
        }
    ).to_parquet(path / "part.parquet", index=False)
    loaded = _read_owned_attempts(tmp_path)
    assert loaded["study_id"].tolist() == ["openrouter-market-measurement-v1"]
    assert loaded["selected_provider"].tolist() == ["A"]
