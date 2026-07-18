"""Collusion diagnostics for converged strategy profiles.

Three instruments, applied to ANY strategy tier (behavioral, tabular-Q,
LLM):

  calvano_delta      (imported from strategies_qlearn benchmarks) — profit
                     position between Nash and cartel
  cut_response       the EconEvals-style litmus: force one rival to cut,
                     classify the subject's response path as punish / match /
                     ignore. Punishment (temporary below-baseline pricing
                     followed by reversion) is the reward-punishment
                     signature of equilibrium collusion; matching or ignoring
                     are competitive/rigid signatures.
  deviation_audit    the execution-plan stop rule: at the converged profile,
                     compute the best unilateral one-shot deviation gain per
                     agent on the price grid. A large profitable deviation
                     means the profile is NOT equilibrium collusion —
                     apparent coordination that fails this audit must be
                     reported as non-equilibrium elevation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np

from .routers import RouterMechanism
from .strategies_qlearn import expected_profits

PriceFn = Callable[[Mapping[str, float]], float]
#: subject(prev_quotes) -> next own price


def cut_response(
    subject: PriceFn,
    baseline_quotes: dict[str, float],
    subject_name: str,
    rival_name: str,
    cut_frac: float = 0.2,
    horizon: int = 12,
    revert_tol: float = 0.02,
) -> dict:
    """Force `rival_name` to cut by `cut_frac` at t=0 and hold; feed the
    subject its own trailing quotes; classify the response path."""
    quotes = dict(baseline_quotes)
    base_own = quotes[subject_name]
    path = []
    quotes[rival_name] = baseline_quotes[rival_name] * (1 - cut_frac)
    for _ in range(horizon):
        p = float(subject(dict(quotes)))
        path.append(p)
        quotes[subject_name] = p
    below = [p < base_own * (1 - revert_tol) for p in path]
    ended_back = abs(path[-1] - base_own) <= base_own * revert_tol
    followed_to_cut = abs(path[-1] - quotes[rival_name]) <= quotes[rival_name] * 0.05
    if any(below) and ended_back:
        verdict = "punish_and_revert"
    elif followed_to_cut or (below[-1] and not ended_back):
        verdict = "match"
    elif not any(below):
        verdict = "ignore"
    else:
        verdict = "ambiguous"
    return {
        "verdict": verdict,
        "path": [round(p, 4) for p in path],
        "baseline_own": round(base_own, 4),
        "rival_cut_to": round(quotes[rival_name], 4),
    }


def deviation_audit(
    prices: dict[str, float],
    costs: dict[str, float],
    router: RouterMechanism,
    demand: float,
    grid: np.ndarray,
) -> dict:
    """Best unilateral one-shot deviation gain per agent at a profile."""
    base = expected_profits(prices, costs, router, demand)
    gains = {}
    for name in prices:
        best = base[name]
        for p in grid:
            trial = dict(prices)
            trial[name] = float(p)
            pi = expected_profits(trial, costs, router, demand)[name]
            best = max(best, pi)
        gains[name] = round(float(best - base[name]), 6)
    max_gain = max(gains.values())
    rel = max_gain / max(abs(np.mean(list(base.values()))), 1e-12)
    return {
        "deviation_gains": gains,
        "max_gain": round(float(max_gain), 6),
        "max_gain_rel_to_mean_profit": round(float(rel), 4),
        "equilibrium_consistent": bool(rel < 0.05),
    }
