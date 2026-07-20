# Adaptive-router future-only adversarial validation

**Frozen:** 2026-07-20, before the first eligible UTC test date  
**Study ID:** `adaptive-router-adversarial-v2`  
**Configuration:** `config/adaptive_adversarial_v2.toml`

## Design boundary

Version 1 was an outcome-informed screening exercise. Its attack results were used to
repair dimensional price response, operator caps, one-sided trust regions, and the
within-commitment quote lock. No version-1 menu or simulation result is confirmatory.

Version 2 freezes that implementation and evaluates it only on endpoint menus dated
2026-07-21 through 2026-08-03 UTC. The release is forbidden before 2026-08-04 UTC.
The exact Hugging Face dataset revision is written to an immutable marker before the
analysis reads the eligible menu rows. A revision can be released at most once.

The eligible population, deterministic sampling rule, four router treatments, quote
and capacity grids, cost bands, learner horizons, seeds, and thresholds are all fixed
in the versioned TOML configuration. The release must contain all 14 dates and at least
5,000 eligible historical menus. Failure of either support gate is an incomplete study,
not a negative result, and cannot be repaired by including earlier dates.

## Primary gate family

Relative to inverse-square routing, the hardened router must meet every declared
materiality threshold for:

- mean and 95th-percentile mechanical allocation gain;
- share captured by a 25% fading quote;
- absolute combined-share gain from a two-endpoint identity split;
- mean and 95th-percentile unilateral finite-grid exploitability;
- mean and 95th-percentile two-provider finite-grid exploitability; and
- mean post-UCB unilateral exploitability.

All ratios use the inverse-square quantity as denominator. Undefined ratios fail rather
than disappearing. Q-learning convergence and Calvano deltas remain diagnostics because
the screening runs did not establish a stable convergence gate.

## Interpretation

Passing establishes robustness only within the observed future menu population, stated
cost/capacity bands, finite deviation grids, two-provider coalition class, and UCB
learner family. It does not establish strategy-proofness, equilibrium, welfare, causal
provider response, absence of collusion, or robustness to unrestricted history-dependent
policies. The paid owned-traffic study remains a separate service-feasibility layer.

