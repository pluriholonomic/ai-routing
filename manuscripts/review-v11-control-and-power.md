# Independent panel review — v11 negative control and power

Artifacts reviewed: the 22-page LaTeX manuscript; preregistration commit
`adc09cd`; the 175-event same-provider control; the 163-event own-menu-novel
subpanel; 5,000 conditional-design simulation replications; 1,250 complete
known-clock quote panels; the detection-threshold proposition; machine-readable
replication tables; and the still-masked H80 assignment ledger.

## Referee A — ACM EC / empirical IO

This revision fixes an important interpretive problem in v10. The paper no longer
treats a failure to reject a deliberately hard menu null as evidence against
strategic response. It separates three questions:

1. Can asynchronous menus reproduce the observation? Yes, by constructive
   observational equivalence.
2. Does the declared restricted-menu test control false positives? Yes: 3.5%
   one-sided promotion on the frozen conditional design and 0% in the known-clock
   mechanism.
3. Does that test have power against economically moderate response? Often not:
   approximately 43% at the observed-equivalent effect and 0% throughout the
   structural grid through 50% replacement.

The same-provider control is well chosen and was genuinely timestamped before
estimation. It does not support the most obvious provider-template confound:
own-menu reuse is 5.3% among rival landings and 7.3% otherwise. Removing those
events raises the strategic residual from 7.0 to 13.4 points and makes every
leave-one-model-out estimate positive. But the model-cluster interval
[-11.5, 18.5] remains too wide, largely because one model supplies 77% of events.
The paper correctly retains nonpromotion.

The detection-threshold proposition is algebraically elementary, but useful in
this setting. A benchmark that dominates the focal rival-set hit probability is
conservative under no response and requires a strictly positive response rate
before the statistic even has the correct sign. Combined with the prior
observational-equivalence proposition, it creates a coherent falsification
ladder: weak atoms overinterpret; hard nulls can underinterpret; identification
requires declaring both the null class and its detection region.

My main reservation is external calibration of SIM2. Its menu is intentionally
discrete and its global control pool is much denser than focal rival sets. The
simulation proves that zero power is possible under the declared family, not
that the real market lies near that family. A convincing final version should
compare the simulated distributions of endpoint count, exact-point multiplicity,
control-pool hit share, and event concentration with the empirical frozen panel.
That calibration must be declared without tuning the already-frozen primary
test. A held-out posterior-predictive diagnostic would be appropriate.

**Recommendation: REVISE AND RESUBMIT.** The identification and test-calibration
contribution is now novel enough to merit serious EC consideration. The positive
empirical mechanism result is still absent.

## Referee B — operations research / platform systems

The implementation quality is high. The control uses a strictly prior timestamp,
requires a contemporaneous same-provider quote on another model, treats missing
controls as missing rather than novel, and preserves the factor-1.25 band. The
simulation uses the production event extractor and hypergeometric null rather
than a surrogate. Seeds, grids, replication counts, and promotion rules were
committed before estimation. The immutable HF revision and artifact hashes make
the release auditable.

Two technical limitations remain. First, the percentile model-cluster interval
has only 91.5% null coverage in SIM1, although its one-sided false-promotion rate
is acceptable. With only 18 clusters, a wild-cluster or randomization-based
robustness check would be useful, but it must not replace the registered primary
after the fact. Second, SIM2's reactive replacement operates only at scheduled
refreshes and forces exact landing. Real reactions may change refresh timing or
undercut by a grid step; the reported power curve is mechanism-specific.

H80 remains the only randomized route to a causal operational claim and is still
far below its 500-per-arm gate. No amount of additional simulation substitutes
for that experiment.

**Recommendation: WEAK REJECT / ENCOURAGE RESUBMISSION.** The artifact and
methodology are publishable; the decisive randomized and confirmatory samples are
not mature.

## Meta-review

### Decision

**REVISE AND RESUBMIT — not accepted yet.** Relative to v10, the manuscript gains
a real methodological result: a preregistered demonstration that the same test
can be valid in size yet weak in power, with an explicit response-detection
threshold. This materially improves novelty and prevents a misleading negative
claim. It does not solve the missing positive identification.

The strongest current contribution is now:

> Inference-provider price atoms lie between two inferential failures. Adjacent
> price placebos falsely attribute common menu mass to strategic anchors, while a
> dominating public-menu benchmark can control false positives yet mask moderate
> rival response. Exact endpoint-label nulls, own-provider controls, detection
> thresholds, and realized randomized routing are jointly required.

### Mechanical gates

- Quote panel: 10/30 outcome-free calendar dates; 20 additional dates remain.
- H80: 33, 37, 34, and 36 of 500 first-position assignments per arm at the last
  outcome-free audit; all 140 replayed exactly and outcomes remain masked.
- PM5 confirmatory rule: endpoint-label, factor-1.25, same-provider, and
  own-menu-novel estimands must run unchanged on the earliest 30-date revision.
- Simulation result: SIM1 one-sided null promotion 3.5%; observed-effect power
  43.4%; SIM2 promotion 0% at every registered response level.

### Current readiness score

| Dimension | Readiness | Reason |
|---|---:|---|
| Novel economic object | 94% | Dealer-and-dispatcher market remains distinctive. |
| Identification contribution | 97% | Equivalence plus detection-region results form a reusable framework. |
| Test calibration | 88% | Size and power are now measured; structural calibration remains stylized. |
| Positive empirical discrimination | 64% | Own-menu confound weakens, but cluster inference still crosses zero. |
| Manuscript completeness | 99% | Full paper, proofs, controls, simulations, and claim ledger. |
| Pipeline and release integrity | 99% | Preregistered, revision-pinned, deterministic release. |
| External validity | 67% | Effective dynamic support remains highly concentrated. |
| Firmness causal evidence | 40% | The randomized outcome gate remains immature. |
| Submission readiness | 82% | Methodologically novel; decisive empirical gates still pending. |

The user-defined acceptance stop rule is not met. Keep the goal active. The next
useful non-outcome work is an empirical-vs-SIM2 calibration table and a declared
wild-cluster robustness check. Neither may replace or retune the locked primary
estimands.
