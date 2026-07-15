# H83 preregistration: the hidden-capacity overshoot cycle

Version: 1.0  
Frozen: 2026-07-15  
Discovery cutoff: 2026-07-15 12:00:00 UTC

## Discovery and separation from H82

H82 was designed as a conventional enforcement-onset event study. Its frozen
pretrend tests failed because focal successful share rose before a
high-intensity rate-limit onset, fell sharply at onset, and partially recovered
afterward. This **capacity-overshoot cycle** is an outcome-informed discovery,
not an H82 confirmatory result.

H83 freezes that shape as a new hypothesis and uses only events at or after
2026-07-15 12:30 UTC, ensuring that every -30-minute lead is strictly after the
discovery cutoff. No H83 outcome observed at or after the cutoff was inspected
before this document was committed.

## Mechanism hypothesis

Let `s_it` be endpoint or provider successful-request share within a model.
When posted price changes slowly and true deliverable capacity is hidden, flow
can load onto an attractive endpoint until capacity binds. Public rate-limit
enforcement then coincides with successful share falling, followed by partial
recovery as load or routing adapts. The short-run signature is:

1. **loading:** share rises before a high-intensity onset;
2. **break:** share drops across the onset;
3. **recovery:** share rises after the initial drop; and
4. **sticky price:** the focal completion price does not move over the cycle.

This is a mechanistic shape restriction, not a claim that a provider anticipated
flow, intentionally faded a quote, or front-ran a request. Rate-limit onsets
remain endogenous to demand and health.

## Event population

H83 inherits H82's source precedence, ten-minute contiguity rule, and fixed
high-intensity onset definition:

- preceding contiguous rate-limit count is zero;
- current rate-limit count is at least five;
- current rate-limit share is at least 20%;
- current success-plus-rate-limit count is at least ten;
- endpoint is not displayed as deranked;
- exactly one high onset occurs for the model at time zero; and
- no other high onset for the model lies within 60 minutes.

The low-intensity control has positive rate limits, share at most 5%, the same
attempt and state requirements, no high event within 60 minutes, and the same
deterministic greedy thinning. Event windows use the nearest snapshot within
2.5 minutes of each five-minute cell from -30 to +60. Every retained event has
at least four cells in each of the H82 pre and post windows.

## Frozen contrasts

For endpoint and provider successful share separately, define:

- loading `L = mean(s[-15,-5]) - mean(s[-30,-20])`;
- break `B = mean(s[+5,+10]) - mean(s[-10,-5])`;
- recovery `R = mean(s[+45,+60]) - mean(s[+5,+20])`; and
- level loss `D = mean(s[+5,+30]) - mean(s[-30,-5])`.

The overshoot cycle requires `L > 0`, `B < 0`, `R > 0`, and `D < 0` for provider
share. Endpoint share is a co-primary replication. The high-minus-low matched
contrast must have the same sign for every component. Matching is within model
and uses only pre-event log model attempts, UTC hour, and calendar distance,
exactly as in H82.

Each early, late, break-side, and recovery-side subwindow must contain at least
two observed share cells. Events lacking that support remain in the protocol
ledger but not the shape estimator.

Completion-price stickiness is the share of events with no price change beyond
relative numerical tolerance from -30 through +60. Its frozen requirement is
at least 95%.

Other-provider and model-total successful counts are secondary accounting
outcomes. H83 does not require rival recovery: a binding-capacity event may
destroy model-level throughput when alternatives are also constrained or the
public endpoint set is incomplete.

## Inference and support

Report event-weighted and model-equal-weighted means. Resample model-day
clusters with 10,000 deterministic bootstrap draws. The cycle is confirmed
only through an intersection-union rule:

- the one-sided 95% cluster interval for each provider-share component excludes
  zero in its predicted direction;
- all four matched high-minus-low components agree in sign, and the break and
  level-loss matched intervals exclude zero;
- endpoint-share components agree in sign and its break interval excludes
  zero;
- every leave-one-provider-out provider-share component retains its predicted
  sign; and
- at least 95% of focal prices are sticky.

No single component's p-value substitutes for the conjunction. No
significance-based stopping is permitted.

## Release gates

The first immutable future-only cut is confirmatory only after:

- at least 28 complete post-cutoff days;
- at least 300 complete isolated high events;
- at least 20 models and 20 providers;
- no provider contributes more than 20% of events;
- at least 250 matched high/low pairs;
- maximum additive flow-accounting residual below `1e-9`; and
- every shape, matching, support, and price condition above passes.

Until then H83 reports `future_holdout_power_gated` and reveals only sample,
support, protocol, and gate diagnostics. It does not reveal future shape
coefficients early. H82 remains visible as discovery evidence and must never be
pooled into H83.

Once the time, sample, support, matching, and accounting gates are met, the
earliest deterministic cut is released whether the shape restrictions pass or
fail. A failed shape verdict terminates that confirmatory cut; the analyzer may
not wait for later observations to turn it significant.

## Claim boundary after a successful gate

A successful H83 cut would establish a reproducible public
capacity-overshoot signature conditional on isolated rate-limit onsets. It
would still not identify a randomized causal effect, private router logic,
provider intent, front-running, user welfare, or the treatment effect of
capacity certification. Those require owned-traffic randomization or a real
commitment intervention.
