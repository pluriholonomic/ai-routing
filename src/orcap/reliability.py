"""Statistical primitives for controlled provider-reliability audits.

These helpers intentionally certify only a lower bound for the declared audit
population.  They do not infer a provider's reliability on an arbitrary
router, workload, time period, or failure domain.
"""

from __future__ import annotations

from math import isfinite

from scipy.stats import beta


def exact_one_sided_binomial_lower_bound(
    successes: int,
    trials: int,
    *,
    confidence_level: float,
) -> float:
    """Return the exact Clopper--Pearson lower bound for a Bernoulli rate.

    Under independent identically distributed completed direct-audit attempts
    from the pre-registered population, the returned random bound covers the
    population success probability with at least ``confidence_level``.  The
    boundary cases use their exact closed forms rather than asking SciPy for a
    degenerate beta quantile.
    """
    if not isinstance(successes, int) or isinstance(successes, bool):
        raise ValueError("successes must be an integer")
    if not isinstance(trials, int) or isinstance(trials, bool) or trials <= 0:
        raise ValueError("trials must be a positive integer")
    if successes < 0 or successes > trials:
        raise ValueError("successes must lie between zero and trials")
    try:
        confidence = float(confidence_level)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence_level must be numeric") from exc
    if not isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("confidence_level must lie in (0, 1)")

    alpha = 1.0 - confidence
    if successes == 0:
        return 0.0
    if successes == trials:
        return float(alpha ** (1.0 / trials))
    return float(beta.ppf(alpha, successes, trials - successes + 1))


def meets_reliability_threshold(
    lower_bound: float | None, *, minimum_reliability: float
) -> bool:
    """Require a finite one-sided lower bound to clear an eligibility floor."""
    try:
        bound = float(lower_bound) if lower_bound is not None else float("nan")
        threshold = float(minimum_reliability)
    except (TypeError, ValueError) as exc:
        raise ValueError("reliability bound and threshold must be numeric") from exc
    if not isfinite(bound) or not 0 <= bound <= 1:
        raise ValueError("lower_bound must lie in [0, 1]")
    if not isfinite(threshold) or not 0 <= threshold < 1:
        raise ValueError("minimum_reliability must lie in [0, 1)")
    return bound >= threshold
