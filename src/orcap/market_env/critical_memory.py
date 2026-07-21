"""Finite-time discovery bounds for a memory-window pricing penalty."""

from __future__ import annotations

import math


def expected_run_wait(memory: int, low_probability: float) -> float:
    """Expected trials to observe ``memory`` consecutive low actions.

    Actions are independent Bernoulli draws with low-action probability q.  The
    expression is exact and counts the final action in the first complete run.
    """
    if not isinstance(memory, int) or memory < 1:
        raise ValueError("memory must be a positive integer")
    q = float(low_probability)
    if not 0 < q <= 1:
        raise ValueError("low_probability must lie in (0, 1]")
    if q == 1:
        return float(memory)
    return float((1 - q**memory) / ((1 - q) * q**memory))


def discovery_probability_upper_bound(
    horizon: int,
    memory: int,
    low_probability_cap: float,
) -> float:
    """Union upper bound under any adaptive pre-discovery policy.

    Before discovery, the conditional probability of choosing low at every step
    may depend on history but must be at most ``low_probability_cap``.
    """
    if not isinstance(horizon, int) or horizon < 0:
        raise ValueError("horizon must be a non-negative integer")
    if not isinstance(memory, int) or memory < 1:
        raise ValueError("memory must be a positive integer")
    q = float(low_probability_cap)
    if not 0 <= q <= 1:
        raise ValueError("low_probability_cap must lie in [0, 1]")
    windows = max(horizon - memory + 1, 0)
    return min(1.0, float(windows * q**memory))


def necessary_horizon(
    memory: int,
    low_probability_cap: float,
    target_success_probability: float,
) -> int:
    """Necessary horizon for the requested discovery probability.

    This inverts the looser bound ``P(discovery by T) <= T q**memory`` and is
    therefore a lower bound on the horizon, not a sufficiency guarantee.
    """
    if not isinstance(memory, int) or memory < 1:
        raise ValueError("memory must be a positive integer")
    q = float(low_probability_cap)
    target = float(target_success_probability)
    if not 0 < q <= 1:
        raise ValueError("low_probability_cap must lie in (0, 1]")
    if not 0 < target <= 1:
        raise ValueError("target_success_probability must lie in (0, 1]")
    return int(math.ceil(target / q**memory))


def critical_memory(
    horizon: int,
    low_probability_cap: float,
    target_success_probability: float,
) -> int:
    """Largest memory not ruled out by the union discovery bound."""
    if not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    q = float(low_probability_cap)
    target = float(target_success_probability)
    if not 0 < q < 1:
        raise ValueError("low_probability_cap must lie in (0, 1)")
    if not 0 < target <= 1:
        raise ValueError("target_success_probability must lie in (0, 1]")
    value = math.log(horizon / target) / math.log(1 / q)
    return max(0, int(math.floor(value)))


def expected_option_transitions(memory: int, option_probability: float) -> float:
    """Expected primitive transitions until a length-(memory+1) option completes.

    At each decision epoch the option is selected with probability ``q``.  A
    non-option decision consumes one primitive transition, whereas the first
    selected option consumes ``memory + 1``.  Hence the expected duration is
    ``(1-q)/q + memory + 1 = memory + 1/q``.
    """
    if not isinstance(memory, int) or memory < 1:
        raise ValueError("memory must be a positive integer")
    q = float(option_probability)
    if not 0 < q <= 1:
        raise ValueError("option_probability must lie in (0, 1]")
    return float(memory + 1 / q)
