# H82 results: public enforcement marks a price-invariant capacity event

Snapshot: authoritative Hugging Face panel through 2026-07-15 11:33 UTC

Design: `docs/h82-enforcement-substitution-preregistration.md`

Status: **descriptive and power-gated; not causal**

The discovery sample is now immutably capped at
`2026-07-15T11:33:02Z`. This cutoff was recorded after the first H82 result in
order to keep every later observation exclusive to H83; it does not convert
H82 into a preregistered confirmatory analysis.

## Result in one sentence

At isolated high-intensity rate-limit onsets, the constrained endpoint and its
provider lose about 2.1 percentage points of within-model successful-request
share while the posted completion price remains unchanged; the same share loss
is larger relative to pre-treatment-matched low-intensity onsets, but pretrend
placebos fail and rival-volume recovery is not robust enough to call the event
causal rerouting.

## Sample construction

The source panel contains 503,321 endpoint snapshots over 7.66 days. There are
2,228 high-intensity onset candidates. Requiring a single onset for the model
and no other high onset within 60 minutes leaves 342 eligible events. Fixed
event-window coverage leaves 231 complete high events, 1,203 complete
low-intensity controls, and 223 within-model pre-treatment matches.

The 231 high events span 22 models and 38 providers. The largest provider
contributes 15.6%, below the frozen 20% concentration gate. The release still
fails because only seven of 28 required complete days exist and every primary
pretrend placebo fails.

## Frozen primary estimates

Intervals resample 111 model-day clusters with the preregistered deterministic
cluster bootstrap. They measure clustered sampling variation, not hidden
confounding.

| Outcome | High-onset post minus pre | 95% interval | Matched high minus low | 95% interval |
|---|---:|---:|---:|---:|
| Endpoint successful share | -2.09 pp | [-3.17, -1.11] pp | -2.57 pp | [-4.14, -1.22] pp |
| Provider successful share | -2.08 pp | [-3.06, -1.13] pp | -2.56 pp | [-4.09, -1.21] pp |
| log1p other-provider successes | +0.0516 | [+0.0122, +0.0929] | +0.0285 | [-0.0191, +0.0842] |

Model-equal weighting strengthens the share result slightly: -2.41 pp for both
the endpoint and provider measures. Leave-one-provider-out endpoint estimates
range from -2.36 to -1.44 pp; no provider omission reverses the sign.

## Falsification and accounting

The early-versus-late pre-period placebo is +0.71 pp for endpoint share and
+0.72 pp for provider share, with both intervals excluding zero. Other-provider
volume also has a nonzero negative placebo. These failures matter: traffic is
already loading onto the soon-constrained endpoint before onset, so a simple
parallel-trends interpretation is invalid.

The normalized event path instead suggests an exploratory **capacity-overshoot
cycle**: successful share rises before time zero, drops sharply at the onset,
and only partially recovers over the next hour. The high-intensity path is
visibly different from the low-intensity control path. This pattern was not a
frozen H82 primary hypothesis and must be tested on a future-only holdout.

Posted completion price is constant in 100% of complete high-event windows.
The public market therefore adjusts on an operational margin, not through a
five-minute money-price response.

Raw successful-count accounting is exact on jointly observed cells:

| Component | Mean post-minus-pre count |
|---|---:|
| Focal endpoint | -456.59 |
| Same-provider other endpoints | -0.06 |
| Other providers | -55.54 |
| Model total | -512.19 |

The additive residual is `2.6e-13`, and the maximum snapshot residual is zero.
The raw mean does not show recovered flow: model-wide successes fall alongside
the focal endpoint. A 1%/99% winsorized sensitivity makes the rival component
positive, so the raw diversion ratio is tail-sensitive and is not promoted.

## What is supported

- High public rate-limit onsets mark an economically visible decline in the
  constrained endpoint's and provider's successful share.
- The decline survives low-intensity matching, model-equal weighting, and every
  leave-one-provider-out cut.
- Posted prices do not move over the event horizon.
- The operational path is consistent with hidden capacity becoming binding and
  router enforcement acting on a different timescale than price.

## What is not supported

- A causal effect of rate limiting: the onset is endogenous to demand and
  provider health, and the frozen pretrend tests fail.
- Complete within-model rerouting: the matched rival-volume interval includes
  zero and total model success declines.
- Front-running, intentional quote fading, private-score behavior, customer
  harm, welfare loss, or the welfare effect of a capacity certificate.

## Next confirmatory experiment

H83 should freeze the current panel as discovery data and test the
capacity-overshoot cycle only on later observations. Its primary shape
restrictions should be: positive focal-share loading before onset, a negative
provider-share discontinuity from -5 to +5 minutes relative to matched low
onsets, partial recovery by +60, and no focal price response. This treats the
H82 pretrend as the proposed mechanism rather than pretending it is absent.
