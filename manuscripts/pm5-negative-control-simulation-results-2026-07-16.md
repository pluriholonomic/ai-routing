# PM5 negative-control and simulation results — 2026-07-16

## Contract

The specification, thresholds, seeds, and promotion rules were committed and
pushed as `adc09cd` before these estimates were computed. The empirical input is
the frozen 2026-07-07--2026-07-15 panel at Hugging Face dataset revision
`600bb41fd15189c70f8f78fce8cf0a519fb8dd61`. No H80 outcome was read.

## NC1: same-provider/across-model control

Of 196 isolated revisions, 175 have the same provider quoting another model in
the preregistered factor-1.25 band at the strictly prior timestamp. Only 12/175,
or 6.86%, set the new focal-model price exactly equal to one of those own-provider
cross-model prices.

| Same-model rival landing | Own-menu absent | Own-menu exact | Total |
|---|---:|---:|---:|
| No | 127 | 10 | 137 |
| Yes | 36 | 2 | 38 |

Own-menu support is 5.26% among exact rival landings and 7.30% otherwise. The
landing-minus-nonlanding difference is -2.04 points, with model-cluster interval
[-31.03, 0.93] points and provider-cluster interval [-27.78, 6.22]. Thus the
declared negative control does not support the simple explanation that movers are
merely copying their own cross-model price template.

Removing all 12 own-menu-supported events leaves 163 own-menu-novel revisions.
Their exact lagged-rival landing rate is 22.09%, the matched global-menu benchmark
is 8.65%, and the excess is 13.44 points. Every leave-one-model-out point estimate
is positive [1.41, 15.19] points, but the model-cluster interval is
[-11.50, 18.51] and the provider-cluster interval is [-13.83, 23.03]. The frozen
promotion rule therefore fails. One model still supplies 77.3% of novel events
and 83.3% of novel exact landings.

This result weakens the own-provider-template explanation but does not promote
strategic following: removing a measured confound raises the point estimate while
leaving cluster-level identification too weak.

## SIM1: conditional-design size and power

SIM1 ran 1,000 replications at each response probability with 2,000
model-cluster bootstrap draws per replication.

| Response probability rho | Target excess | Mean estimate | 95% interval coverage | Joint promotion rate |
|---:|---:|---:|---:|---:|
| 0.00 | 0.000 | -0.001 | 91.5% | 3.5% |
| 0.05 | 0.043 | 0.043 | 92.3% | 29.7% |
| 0.10 | 0.087 | 0.086 | 91.4% | 51.9% |
| 0.25 | 0.216 | 0.218 | 89.8% | 94.7% |
| 0.50 | 0.433 | 0.433 | 91.1% | 100.0% |

The one-sided promotion size is controlled at 3.5%, although the percentile
interval undercovers relative to nominal two-sided 95% coverage. The observed
7.00-point frozen excess is equivalent to `rho=0.0809` under SIM1's conditional
mixture. Linear interpolation between the registered grid points gives only 43.4%
promotion power. Nonrejection in the frozen panel is therefore compatible with a
moderate response effect; it is not affirmative evidence of zero response.

## SIM2: known-clock panels

SIM2 ran 250 full 576-tick quote panels at each response probability. The null
uses provider-specific clocks and a public discrete menu but never reads rivals.
Every panel was passed through the unchanged PM5 event extractor and matched-menu
null.

| rho | Median events | Exact landing | Menu benchmark | Mean excess | Promotion |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 2,150 | 59.9% | 90.4% | -30.6 pp | 0% |
| 0.05 | 2,275 | 61.6% | 90.3% | -28.8 pp | 0% |
| 0.10 | 2,205 | 63.0% | 90.3% | -27.3 pp | 0% |
| 0.25 | 2,305 | 66.0% | 90.0% | -24.0 pp | 0% |
| 0.50 | 2,347 | 71.6% | 89.2% | -17.6 pp | 0% |

The structural null has zero false promotions, satisfying the registered size
criterion. But it also has zero power throughout the registered response grid.
The other-model control pool is much denser at exact menu points than a focal
same-model rival set, so the hypergeometric benchmark dominates the actual
landing probability. This is a conservative falsification test, not an estimator
of the strategic response share.

## RB1: exact model-cluster sign-flip robustness

The RB1/CAL1 addendum was committed and pushed as `dc90d02` before these
statistics were computed. Enumerating all `2^18=262,144` model-cluster sign
assignments for the full panel gives a one-sided p-value of 0.4250 (two-sided
0.8501). The own-menu-novel panel has 14 model clusters; enumerating all 16,384
assignments gives a one-sided p-value of 0.2139 (two-sided 0.4277).

These p-values agree with the wide cluster-bootstrap intervals: the positive
event-weighted estimates are not broadly supported across model clusters. The
sign-flip test assumes cluster-level symmetry and is an observational robustness
check, not randomization inference or a replacement for the frozen primary.

## CAL1: empirical calibration of SIM2

The empirical frozen panel lies outside the registered SIM2 null's 5th--95th
percentile range on every declared diagnostic.

| Statistic | Empirical | SIM2 p05 | SIM2 median | SIM2 p95 |
|---|---:|---:|---:|---:|
| Extracted events | 196 | 1,228 | 2,150 | 3,381 |
| Exact landing share | 20.4% | 49.0% | 58.8% | 73.2% |
| Matched-menu probability | 13.4% | 89.1% | 90.5% | 91.3% |
| Exact-minus-menu residual | +7.0 pp | -41.5 pp | -31.5 pp | -17.3 pp |

SIM2 is therefore a stress-test counterexample, not an empirically calibrated
data-generating process. It proves that a known-clock asynchronous menu can make
the declared hard null correctly sized yet powerless; it does not estimate the
market's latent response rate or show that this particular mechanism generated
the observed panel. The registered simulation was not retuned after this failure.

## Detection-threshold implication

For event `e`, let `p_e` be the nonreactive probability of exact landing and
`q_e` the matched-menu benchmark. If a reactive replacement forces exact landing
with probability `rho`, the exact-landing probability is

`p_e(rho) = p_e + rho(1-p_e)`.

The expected matched-menu residual is positive only when

`rho > (q_e-p_e)/(1-p_e)`.

When `q_e >= p_e`, the test is conservative under the nonreactive mechanism but
has a strictly positive detection threshold. Using SIM2's aggregate null means
gives an illustrative threshold of approximately 0.762. This explains why the
registered grid through `rho=0.50` never promotes. The statement is about the
test's detection region, not about the actual market's response probability.

## Verdict

- The own-provider cross-model negative control does not explain lagged rival
  landings.
- The own-menu-novel strategic point estimate is larger, but cluster support is
  still insufficient for promotion.
- SIM1 validates one-sided size but shows low power at the observed effect.
- SIM2 validates conservativeness under a known-clock menu mechanism and exposes
  a potentially severe power loss when the control menu is denser than the focal
  rival set, but CAL1 rejects it as an empirical calibration.
- Exact sign-flip p-values of 0.425 and 0.214 confirm that neither positive
  residual has broad model-cluster support.
- The correct empirical statement is **not identified and underpowered**, not
  **no strategic behavior**.

The 30-date replication, cross-model support distribution, and randomized
realized-routing experiment remain the legitimate promotion paths.
