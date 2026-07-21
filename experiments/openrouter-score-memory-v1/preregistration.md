# Prospective routed-share, quality, and score-memory study

Frozen protocol timestamp: `2026-07-22T00:00:00Z`.

Study ID: `openrouter-score-memory-v1`.

## Separation from existing campaigns

This study does not amend, re-randomize, stop, extend, or pool the H81 or H95
experiments. It also does not change the assignments or stopping rule of
`openrouter-glm52-routing-v1`. The existing GLM-5.2 campaign supplies exact
menus, fresh default choices, price-sort controls, and pinned operational
outcomes. This protocol adds a separately identified quality bank and a
prospective dynamic analysis beginning at the timestamp above.

The original GLM campaign ends on 4 August and therefore cannot by itself reach
the frozen 28-day duration gate. A separately identified successor,
`openrouter-score-memory-routing-v1`, starts at `2026-08-04T21:15:00Z` and ends
at `2026-08-19T00:00:00Z`. It repeats the same ten policies and 15-minute
assignment-first cadence under new task, block, manifest, spend, and study IDs.
It neither extends nor re-labels the original campaign. The dynamic analysis
concatenates only observations at or after the prospective start and treats the
study boundary as a mandatory sensitivity split.

The estimand is owned-account routing under frozen public menus. It is not
market-wide share, a proprietary router score, provider cost, intent, collusion,
or front-running.

## Dynamic object

For provider `i`, model `m`, and block `t`, the current choice model is

`Pr(i | M_mt) proportional to p_imt^(-eta) exp(a_imt)`.

The frozen exponent is `eta = 1.6482780609377246`. The no-memory model contains
the exact current menu and provider fixed effects. Dynamic models add only
strictly lagged price and quality state. Same-block pinned outcomes are applied
after that block's choices and can affect only later blocks.

The frozen model family is:

1. no memory;
2. geometric price, quality, and joint memory at 1, 4, 16, 48, 96, 288, and
   672 fifteen-minute blocks;
3. finite undercut-run memory at 1, 4, 16, and 48 blocks; and
4. a two-state price-regime filter with transition probability 0.95 and frozen
   undercut emissions 0.80 in the low-price state and 0.20 in the high-price
   state.

The primary comparison is expanding-window, whole-block future log loss. The
reported effect is held-out bits per owned choice relative to no memory. A
future-price lead and a within-provider circular history shift are negative
controls. Model selection is never based on an in-sample likelihood.

## Quality bank

Every six hours, the paid quality workflow freezes the public GLM-5.2 endpoint
menu and two outcome-free MMLU items before execution. Each item is sent to the
default route and to the three cheapest compatible providers under exact pins.
Temperature is zero, optional reasoning is excluded, fallback is disabled for
pins, and at least 64 output tokens are allowed. Only answer hashes, extracted
letters, correctness, provider identity, token counts, cost, and latency are
retained. Prompts, completions, request bodies, API keys, and session IDs are not
published.

The first item is also sent once through each of three disclosed owned-router
policies: current price only, a 24-hour geometric quality state, and a 24-hour
finite failure window. All three arms use the same pre-block quality history,
the same exact provider menu, and fresh sessions; their execution order is
seed-randomized within the block. Policy-arm outcomes never update the state,
preventing cross-arm leakage. This is a randomized complete-block comparison of
the router we control, not a claim about OpenRouter's hidden default rule.

Each eleven-task plan is uploaded before a paid request. Execution consumes that manifest
exactly once and stops on source, manifest, duplicate, privacy, campaign-window,
or spend failure. Caps are $0.25/run, $2/day, and $30/campaign. The account's
available credit is not a spending target.

## Hypotheses

- **M0:** lagged state does not improve future choice prediction beyond the
  current menu and provider effects.
- **M1:** a lagged failure, latency spike, or fidelity failure predicts a lower
  future relative score with a decaying response.
- **M2:** undercut run length or lagged relative price predicts future routing
  conditional on the current quote.
- **M3:** non-price scoring attenuates or amplifies the cumulative owned share
  gained from a price cut.
- **M4:** an identified memory interval overlaps a theoretically consequential
  critical-memory region.
- **M5:** a disclosed quality-memory policy improves fidelity-qualified
  completion per dollar in a controlled owned-router experiment.

M0--M3 are predictive until a randomized owned-router or partner-log transition
test passes. M4 cannot enter the ICML or EC evidence spine unless the theory-entry
gate in the implementation plan passes. M5 applies only to the disclosed router
we control.

## Gates and release

The dynamic result remains `accruing` until there are 800 covered default
choices, 100 blocks, 28 days, three selected providers, 90% exact-menu coverage,
30 independent price-history events, and 30 quality or enforcement shocks.
Quality-stratum claims require 100 completed scored tasks per supported
provider-model-task stratum. A causal designed-router claim requires 100
assignment-valid complete blocks per arm, randomized within-block order, and no
cross-arm state leakage.

GitHub Actions is the execution authority. Request-level rows remain in the
private Hugging Face dataset. Only support counts, coefficients, intervals,
future-fold losses, negative controls, and aggregate figures are published by
the monitor.
