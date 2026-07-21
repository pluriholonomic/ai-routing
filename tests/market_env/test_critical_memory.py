from __future__ import annotations

import pytest

from orcap.market_env.critical_memory import (
    critical_memory,
    discovery_probability_upper_bound,
    expected_option_transitions,
    expected_run_wait,
    necessary_horizon,
)


def test_exact_expected_run_wait_has_known_fair_coin_values():
    assert expected_run_wait(1, 0.5) == pytest.approx(2.0)
    assert expected_run_wait(2, 0.5) == pytest.approx(6.0)
    assert expected_run_wait(3, 0.5) == pytest.approx(14.0)
    assert expected_run_wait(7, 1.0) == pytest.approx(7.0)


def test_discovery_bound_and_necessary_horizon_are_consistent():
    memory, q, target = 7, 0.1, 0.8
    horizon = necessary_horizon(memory, q, target)
    assert horizon == 8_000_000
    assert horizon * q**memory >= target
    assert (horizon - 1) * q**memory < target
    assert discovery_probability_upper_bound(1000, memory, q) < 0.001


def test_critical_memory_is_logarithmic_in_horizon():
    assert critical_memory(1_000_000, 0.1, 0.8) == 6
    assert critical_memory(10_000_000, 0.1, 0.8) == 7
    assert expected_option_transitions(7, 0.1) == pytest.approx(17.0)


@pytest.mark.parametrize(
    ("function", "args"),
    [
        (expected_run_wait, (0, 0.2)),
        (expected_run_wait, (2, 0.0)),
        (discovery_probability_upper_bound, (-1, 2, 0.2)),
        (necessary_horizon, (2, 0.2, 0.0)),
        (critical_memory, (0, 0.2, 0.8)),
        (expected_option_transitions, (2, 1.1)),
    ],
)
def test_critical_memory_helpers_reject_invalid_inputs(function, args):
    with pytest.raises(ValueError):
        function(*args)
