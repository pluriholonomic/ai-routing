from __future__ import annotations

import importlib.util

import pytest

from orcap.market_env.litellm_conformance import (
    _exclusion_reason,
    _expected_permutation_probabilities,
    _spec_map,
    frozen_fixtures,
    run_conformance,
)
from orcap.market_env.routers import InversePriceRouter


def test_frozen_litellm_fixtures_have_valid_probability_support() -> None:
    fixtures = frozen_fixtures()
    assert len(fixtures) == 5
    for fixture in fixtures:
        probabilities = InversePriceRouter(fixture.exponent).probabilities(
            _spec_map(fixture), fixture.actions
        )
        assert probabilities
        assert sum(probabilities.values()) == pytest.approx(1.0)
        for spec in fixture.specs:
            reason = _exclusion_reason(spec, fixture.actions[spec.provider])
            assert (spec.provider in probabilities) is (reason is None)


def test_fallback_permutation_probabilities_sum_to_one() -> None:
    probabilities = _expected_permutation_probabilities({"a": 0.5, "b": 0.3, "c": 0.2})
    assert len(probabilities) == 6
    assert sum(probabilities.values()) == pytest.approx(1.0)


def test_conformance_rejects_subregistered_sample_size() -> None:
    with pytest.raises(ValueError, match="at least 10,000"):
        run_conformance(trials_per_state=9_999)


@pytest.mark.slow
@pytest.mark.skipif(importlib.util.find_spec("litellm") is None, reason="optional LiteLLM extra")
def test_real_litellm_smoke_conformance() -> None:
    frame, summary = run_conformance(trials_per_state=10_000, fallback_trials=10_000)
    assert summary["litellm_version"] == "1.92.0"
    assert summary["all_rows_pass"]
    assert frame["passed"].all()
