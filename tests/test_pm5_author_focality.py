import pandas as pd
import pytest

from orcap.analysis.pm5_tie_microstructure import (
    author_cluster_inference,
    author_focality_audit,
    author_price_match_panel,
    focality,
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
    assert set(full["placebo_grid_sensitivity"]) == {"0.01", "0.1", "0.5", "1"}


def test_author_focality_empty_panel_fails_closed() -> None:
    empty = pd.DataFrame(columns=["run_ts", "model_id", "provider_name", "price"])
    panel = author_price_match_panel(empty)
    assert panel.empty
    audit = author_focality_audit(empty)
    assert audit["all_market_author_price_atom"]["exact_minus_placebo"] is None
    assert audit["selected_tie_random_label_benchmark"]["n_selected_tied_models"] == 0
