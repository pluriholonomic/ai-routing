# Adaptive-router adversarial screening results

**Run:** GitHub Actions `29780088479`  
**Code:** `b7908e09e496a0714cef3a28a138739af6e8d44c`  
**Immutable HF input:** `0a7c6bef4acb87f81c9d22b1748e7a610107a03e`  
**Status:** complete screening; mixed result; not confirmatory

## Bottom line

The hardening works against one-shot quote manipulation, identity splitting, finite-grid
unilateral deviations, two-provider deviations, and sequential global best responses.
It does not yet pass the adaptive-learning screen. Independent UCB learners end in
profiles with larger remaining profitable deviations under the hardened rule than under
inverse-square routing. The strict quote commitment appears to trade mechanical
manipulation resistance for a harder nonstationary learning problem.

That is a conditional design result, not evidence that real providers use UCB, that the
market is collusive, or that welfare falls. The simulator does not identify provider
costs, realized market-wide demand, user value, or causal provider response.

## Support and integrity

- 4,878 eligible menus, 71 models, 14 dates;
- 652,680 historical quote-attack rows;
- 948 model-day clusters for paired historical intervals;
- 200 strategic menus and 7,200 cost-by-capacity-by-router cells;
- 32 sequential-best-response cells;
- 320 nominal UCB rows over eight menus and four routers;
- 40 bounded Q-learning runs;
- all three artifact components record the same immutable HF revision;
- JSON parses strictly; Parquet, CSV, PNG, and one-page PDF outputs are present;
- GitHub publication and the automatic private HF Space refresh both succeeded.

## Historical attack replay

Relative to inverse-square routing, the hardened policy produced:

| Quantity | Inverse-square | Hardened | Hardened / baseline |
|---|---:|---:|---:|
| Mean maximum allocation gain | 0.2262 | 0.0300 | 0.1326 |
| 95th-percentile maximum allocation gain | 0.2500 | 0.0526 | 0.2104 |
| Mean share captured by a 25% fading quote | 0.4638 | 0.2422 | 0.5222 |
| Mean two-identity combined-share gain | 0.1499 | 0.0000 | 0.0000 |
| Mean maximum profit gain, cost at 50% of quote | 1.54e-6 | approximately 0 | approximately 0 |

Model-day cluster bootstrap intervals exclude zero in the favorable direction:

- maximum allocation-gain difference: -0.1980, 95% CI [-0.2004, -0.1955];
- fading-quote captured-share difference: -0.2231, 95% CI [-0.2338, -0.2123];
- sybil combined-share-gain difference: -0.1511, 95% CI [-0.1529, -0.1494];
- mid-cost bounded-profit-gain difference: -1.63e-6, 95% CI [-1.84e-6, -1.43e-6].

These intervals support a mechanical statement on the public menus. They do not measure
actual provider profit because marginal costs are sensitivity bands.

## Static and scripted strategic attacks

| Quantity | Inverse-square | Hardened | Hardened / baseline |
|---|---:|---:|---:|
| Mean unilateral exploitability | 0.6664 | 0.0000 | 0.0000 |
| 95th-percentile unilateral exploitability | 1.7891 | 0.0000 | 0.0000 |
| Mean two-provider exploitability | 0.4976 | 0.0690 | 0.1387 |
| 95th-percentile two-provider exploitability | 1.2157 | 0.3633 | 0.2988 |

All eight hardened sequential global best-response cells converged with zero residual
finite-grid unilateral gain. The corresponding inverse-square mean residual normalized
gain was 0.3755. This is strong evidence inside the declared finite action class, not a
proof over unrestricted history-dependent policies.

## Adaptive-learning failure

After UCB learning, mean normalized residual exploitability was 3.9291 for the hardened
rule versus 0.4057 for inverse-square, a ratio of 9.6847. The 95th-percentile ratio was
20.9569. Normalization amplifies the contrast because the hardened mechanism also lowers
mean provider profit, but does not create the sign: mean absolute deviation gain was
5.89e-4 versus 3.64e-4, and median absolute gain was 2.39e-4 versus 1.84e-4.

At the menu level, hardened absolute residual gain was higher on five of eight menus.
The largest normalized cell was Mythomax at 26.65 because final mean profit was only
2.5e-5 while an expected deviation was worth 6.65e-4. Thus the screen identifies both a
small-denominator problem and a substantive path-dependence problem.

The v1 UCB seeds were not independent: all ten rows within a menu-policy cell were exact
duplicates. Provider actions were simultaneous, rewards were deterministic expected
profits, and permuting update order did nothing. The correct independent unit for v1 is
therefore the eight menus, not 80 rows. This invalidates seed-based precision claims but
not the observed menu-level warning.

## Q-learning diagnostic

Inverse-square Q-learning converged in 10/10 bounded runs; the hardened policy converged
in 0/10. The hardened mean Calvano delta was -0.0947. Because the screen did not establish
comparable convergence, this is a failed learning diagnostic rather than an economic
collusion estimate.

## Action taken

No mechanism parameter or acceptance threshold was relaxed after reading these results.
The version-2 future protocol was superseded before release because its UCB seeds would
have repeated the same deterministic path. Version 3 changes only the learning
observation process to seeded realized multinomial routed quantities with capacity
clipping, moves the untouched test window forward, and retains the post-UCB maximum
ratio of 0.60. A future failure will be published as a failure.

