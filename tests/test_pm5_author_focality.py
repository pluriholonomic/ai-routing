import pandas as pd
import pytest

from orcap.analysis.pm5_tie_microstructure import (
    attach_global_price_menu_null,
    attach_historical_model_menu_null,
    author_anchor_randomization_audit,
    author_anchor_symmetry_panel,
    author_cluster_inference,
    author_focality_audit,
    author_price_match_panel,
    focality,
    isolated_quote_change_events,
    reference_price_landing_inference,
    selected_tie_random_label_audit,
)
from orcap.analysis.pm9_author_anchor import is_author_provider


def _quotes() -> pd.DataFrame:
    rows = [
        ("anthropic/m1", "Anthropic", 1.0),
        ("anthropic/m1", "Third A", 1.0),
        ("anthropic/m1", "Third B", 2.0),
        ("qwen/m2", "Alibaba", 2.0),
        ("qwen/m2", "Third C", 2.0),
        ("openai/m3", "OpenAI", 3.0),
        ("openai/m3", "Third D", 4.0),
    ]
    return pd.DataFrame(
        [
            {
                "run_ts": "20260716T000000Z",
                "model_id": model,
                "provider_name": provider,
                "price": price / 1_000_000,
            }
            for model, provider, price in rows
        ]
    )


def test_author_price_panel_uses_all_markets_and_aliases() -> None:
    panel = author_price_match_panel(_quotes(), placebo_tick_mtok=0.1)
    assert set(panel["model_id"]) == {"anthropic/m1", "qwen/m2", "openai/m3"}
    assert panel.set_index("model_id").loc["qwen/m2", "exact_third_party_match"] == 1
    assert panel["exact_third_party_match"].sum() == 2
    assert panel["exact_minus_placebo"].mean() > 0.5


def test_selected_tie_random_label_benchmark_detects_mechanical_match() -> None:
    audit = selected_tie_random_label_audit(_quotes())
    assert audit["n_selected_tied_models"] == 2
    assert audit["observed_author_at_tied_min"] == 2
    assert audit["random_label_expected_count"] == pytest.approx(5 / 3)
    assert audit["poisson_binomial_upper_tail_p"] > 0.5

    summary = focality(_quotes())
    assert summary["n_tied_models_with_first_party_quote"] == 2
    assert summary["selected_tie_identity_status"] == (
        "non_discriminating_against_random_label"
    )


def test_random_endpoint_anchor_preserves_realized_price_multiplicity() -> None:
    panel = author_anchor_symmetry_panel(_quotes()).set_index("model_id")
    assert panel.loc["anthropic/m1", "author_shared_price"] == 1
    assert panel.loc[
        "anthropic/m1", "random_anchor_shared_probability"
    ] == pytest.approx(2 / 3)
    assert panel.loc["qwen/m2", "random_anchor_shared_probability"] == 1
    assert panel.loc["openai/m3", "random_anchor_shared_probability"] == 0

    audit = author_anchor_randomization_audit(_quotes())
    assert audit["observed_author_shared_count"] == 2
    assert audit["random_anchor_expected_count"] == pytest.approx(5 / 3)
    assert audit["poisson_binomial_upper_tail_p"] > 0.5


def test_author_provider_crosswalk_is_shared_with_dynamic_audit() -> None:
    assert is_author_provider("qwen/model", "Alibaba") is True
    assert is_author_provider("z-ai/model", "Z.AI") is True
    assert is_author_provider("qwen/model", "DeepInfra") is False


def test_author_cluster_inference_and_full_audit_are_deterministic() -> None:
    panel = author_price_match_panel(_quotes(), placebo_tick_mtok=0.1)
    first = author_cluster_inference(panel, bootstrap_draws=500, seed=7)
    second = author_cluster_inference(panel, bootstrap_draws=500, seed=7)
    assert first == second
    assert first["n_author_clusters"] == 3
    assert first["exact_minus_placebo"] > 0
    assert first["author_cluster_bootstrap_ci95"][0] < first["author_cluster_bootstrap_ci95"][1]

    full = author_focality_audit(_quotes())
    assert full["all_market_author_price_atom"]["n_models"] == 3
    assert full["author_anchor_randomization_benchmark"]["n_models"] == 3
    assert set(full["placebo_grid_sensitivity"]) == {"0.01", "0.1", "0.5", "1"}


def _dynamic_quotes() -> pd.DataFrame:
    rows = []
    snapshots = {
        "2026-07-16T00:00:00Z": {
            "model/a": {"P1": 1.0, "P2": 2.0},
            "model/b": {"P3": 2.0, "P4": 3.0},
        },
        "2026-07-16T00:05:00Z": {
            "model/a": {"P1": 2.0, "P2": 2.0},
            "model/b": {"P3": 2.0, "P4": 3.0},
        },
        "2026-07-16T00:10:00Z": {
            "model/a": {"P1": 2.0, "P2": 3.0},
            "model/b": {"P3": 2.0, "P4": 3.0},
        },
        # This revision is excluded by the 15-minute continuity requirement.
        "2026-07-16T01:00:00Z": {
            "model/a": {"P1": 4.0, "P2": 3.0},
            "model/b": {"P3": 2.0, "P4": 3.0},
        },
    }
    for timestamp, models in snapshots.items():
        for model_id, providers in models.items():
            for provider_name, price in providers.items():
                rows.append(
                    {
                        "run_ts": timestamp,
                        "model_id": model_id,
                        "provider_name": provider_name,
                        "price": price / 1_000_000,
                    }
                )
    return pd.DataFrame(rows)


def test_lagged_price_landing_uses_continuous_single_mover_events() -> None:
    events = isolated_quote_change_events(_dynamic_quotes(), max_gap_minutes=15)
    assert len(events) == 2
    assert events["exact_lagged_rival_match"].tolist() == [1, 0]
    assert events["gap_minutes"].max() == 5

    panel = attach_global_price_menu_null(events, _dynamic_quotes(), band_factor=2)
    assert panel["global_menu_match_probability"].notna().all()
    assert panel["global_menu_pool_size"].min() >= 2
    assert panel["global_menu_match_probability"].tolist() == pytest.approx([0.5, 0.5])
    inference = reference_price_landing_inference(panel)
    assert inference["n_events"] == 2
    assert inference["exact_lagged_rival_match_share"] == pytest.approx(0.5)

    historical = attach_historical_model_menu_null(
        panel,
        _dynamic_quotes(),
        washout_hours=0,
    )
    assert historical["historical_menu_snapshots"].min() >= 1
    assert historical["historical_menu_match_probability"].tolist() == pytest.approx(
        [1.0, 0.0]
    )
    historical_inference = reference_price_landing_inference(historical)
    assert historical_inference["n_historical_menu_comparable_events"] == 2


def test_author_focality_empty_panel_fails_closed() -> None:
    empty = pd.DataFrame(columns=["run_ts", "model_id", "provider_name", "price"])
    panel = author_price_match_panel(empty)
    assert panel.empty
    audit = author_focality_audit(empty)
    assert audit["all_market_author_price_atom"]["exact_minus_placebo"] is None
    assert audit["author_anchor_randomization_benchmark"]["n_models"] == 0
    assert audit["selected_tie_random_label_benchmark"]["n_selected_tied_models"] == 0
