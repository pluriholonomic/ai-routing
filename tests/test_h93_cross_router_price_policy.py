import pandas as pd

from orcap.analysis.h93_cross_router_price_policy import (
    attach_exact_model_matches,
    evidence_summary,
    prepare_public_quotes,
    wilson_interval,
)


def _quote(
    router: str,
    run_ts: str,
    model: str,
    provider: str,
    input_price: float,
    output_price: float,
):
    return {
        "run_ts": run_ts,
        "dt": "2026-07-16",
        "router": router,
        "source_model_id": f"{provider}/{model}",
        "source_model_key": model,
        "provider_name": provider,
        "price_input_usd_per_mtok": input_price,
        "price_output_usd_per_mtok": output_price,
    }


def test_exact_model_matching_fails_closed_on_ambiguous_official_suffix():
    quotes = pd.DataFrame(
        [
            _quote("requesty", "20260716T000000Z", "shared", "a", 1, 2),
            _quote("requesty", "20260716T000000Z", "unique", "a", 1, 2),
        ]
    )
    models = pd.DataFrame(
        {
            "id": ["org-a/shared", "org-b/shared", "org/unique"],
            "hugging_face_id": ["org-a/shared", "org-b/shared", "org/unique"],
        }
    )
    matched = attach_exact_model_matches(quotes, models)
    status = matched.set_index("source_model_key")["model_match_status"].to_dict()
    assert status["shared"] == "ambiguous_official_suffix"
    assert status["unique"] == "exact_unique_official_suffix"
    assert matched.loc[matched["source_model_key"].eq("shared"), "openrouter_model_id"].isna().all()


def test_longitudinal_panel_detects_price_events_and_simulated_route_switches():
    rows = [
        _quote("requesty", "20260716T000000Z", "model", "alpha", 1.0, 1.0),
        _quote("requesty", "20260716T000000Z", "model", "beta", 2.0, 2.0),
        _quote("requesty", "20260716T010000Z", "model", "alpha", 3.0, 3.0),
        _quote("requesty", "20260716T010000Z", "model", "beta", 2.0, 2.0),
        _quote("glama", "20260716T000500Z", "model", "alpha", 1.0, 1.0),
        _quote("glama", "20260716T010500Z", "model", "alpha", 3.0, 3.0),
    ]
    panel = prepare_public_quotes(
        pd.DataFrame(rows),
        pd.DataFrame({"id": ["org/model"], "hugging_face_id": ["org/model"]}),
    )
    summary, frames = evidence_summary(panel)
    assert len(frames["price_events"]) == 2
    assert len(frames["simulated_switches"]) == 1
    assert len(frames["coincident_shocks"]) == 1
    assert summary["evidence_status"] == "initial_cross_sectional_coverage_only"
    assert summary["gates"]["price_events"] is False


def test_same_provider_model_basis_requires_near_simultaneous_different_routers():
    rows = [
        _quote("requesty", "20260716T000000Z", "model", "same-provider", 1.0, 1.0),
        _quote("glama", "20260716T001500Z", "model", "same provider", 2.0, 2.0),
        _quote("nemorouter", "20260716T050000Z", "model", "same-provider", 4.0, 4.0),
    ]
    panel = prepare_public_quotes(
        pd.DataFrame(rows),
        pd.DataFrame({"id": ["org/model"], "hugging_face_id": ["org/model"]}),
    )
    summary, frames = evidence_summary(panel)
    basis = frames["simultaneous_basis"]
    assert len(basis) == 1
    assert {basis.iloc[0]["router_a"], basis.iloc[0]["router_b"]} == {"glama", "requesty"}
    assert basis.iloc[0]["absolute_percent_wedge"] == 100.0
    assert bool(basis.iloc[0]["exact_input_output_price_match"]) is False
    assert summary["posted_price_basis"]["simultaneous_same_provider_model_pairs"] == 1


def test_latest_coverage_counts_competitive_exact_models_without_calling_it_flow():
    rows = [
        _quote("requesty", "20260716T000000Z", "model", "alpha", 1.0, 1.0),
        _quote("requesty", "20260716T000000Z", "model", "beta", 2.0, 2.0),
    ]
    panel = prepare_public_quotes(
        pd.DataFrame(rows),
        pd.DataFrame({"id": ["org/model"], "hugging_face_id": ["org/model"]}),
    )
    summary, _ = evidence_summary(panel)
    coverage = summary["coverage"][0]
    assert coverage["multi_provider_models"] == 1
    assert coverage["exact_matched_competitive_models"] == 1
    assert coverage["hf_linked_exact_matched_competitive_models"] == 1
    assert "does not observe market-wide flow" in summary["claim_boundary"]


def test_wilson_interval_is_bounded_and_contains_the_observed_share():
    lower, upper = wilson_interval(28, 29)
    assert 0 < lower < 28 / 29 < upper < 1
