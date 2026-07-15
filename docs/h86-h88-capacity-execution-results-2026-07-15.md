# H86--H88 results: public capacity support fails; enforcement trial enrolls

Frozen designs: `docs/h86-h87-capacity-state-execution-preregistration.md`

Evidence status: H86/H86b/H87 support audit complete; H88 prospective trial
running with all outcomes power-gated.

## Bottom line

The literal public-capacity experiment cannot currently be estimated. Exact
legacy request identifiers do not match the versioned public model slugs (H86).
The separately frozen official model-ID bridge resolves most of that naming
problem, matching 281 of 348 attempts to a prior public quote/provider state,
but none of those matched states contains a public capacity ceiling or recent
peak (H86b). A prospective H87 support run and a separate top-40 census likewise
find zero capacity-complete candidate pairs. This is missing treatment support,
not evidence of a zero capacity effect.

The preregistered replacement, H88, uses the public five-minute router
enforcement counts that remain populated. Its first remote run on
`2026-07-15T14:43:30Z` enrolls all eight evaluated hot models and sends eight
first-and-only randomized probes. The assignment split is one
`enforcement_safe`, three `enforcement_risky`, and four `openrouter_default`.
All arm outcomes remain masked.

## Support ladder

| Study | Candidate/support result | Outcome status | Permitted conclusion |
|---|---:|---|---|
| H86 exact-ID bridge | 348 legacy pinned attempts; 0 exact model/provider state matches | not estimable | API model IDs and versioned public slugs are not join-compatible |
| H86b official model-ID bridge | 348 mapped attempts; 281 exact backward quote/provider matches; 0 capacity-complete matches | not estimable | the official ID bridge works for quotes, but the capacity fields are absent |
| H87 prospective capacity policy | 8-model first run and 40-model public census; 0 eligible capacity pairs; 0 requests | no outcomes exist | current public capacity state cannot support the frozen trial |
| H88 prospective enforcement policy | 8/8 eligible models; 8 requests; 12 candidate providers | masked until release gates | public enforcement counts support randomized enrollment, not yet an effect |

H86b's 67 unmatched attempts consist of 45 with no exact provider match and 22
whose closest official model snapshot is older than the frozen seven-day
window. Among the 281 exact quote/provider matches, capacity ceilings, recent
peaks, and the derived capacity-risk score are missing in every row.

## First H88 candidate-state audit

H88 defines

`enforcement_stress = (rate_limited_5m + 1) / (success_5m + rate_limited_5m + 2)`

and requires at least ten public five-minute attempts, no derank, a positive
quote, and a pair price ratio no greater than 1.25. The first outcome-free
candidate panel has:

- eight candidate rows, all eligible and assigned;
- eight models and twelve distinct safe/risky candidate providers;
- median safe--risky stress gap 0.541 (range 0.031--0.948);
- median price ratio 1.000 (range 1.000--1.152);
- exact seed replay for all eight blocks;
- 100% pinned payload/selected-provider compliance in the isolated artifact;
- four pinned requests with maximum requested-provider share 25%; and
- $0.000229393 total public quoted-cost exposure for the pinned arms.

The artifact-local analyzer finds no overlapping request, but the authoritative
overlap check is rerun after the nightly merge includes every contemporaneous
study. No success, rejection, latency, selected-provider, or spend result is
released by arm.

## Why H88 is not H87 with a renamed variable

H87 remains frozen around displayed capacity ceiling and recent peak. Those
fields are currently null. H88 was separately committed before its first
request and acts on an observable router-side rejection rate. That score can
test whether a user can improve admission success by avoiding publicly stressed
providers. It is not a measure of physical capacity, marginal cost, strategic
repricing, or provider intent.

The distinction matters for the market analogy. H84 rejects the specified
DeFi-style stale-cheap-liquidity pickoff channel. H86--H87 then show that the
public surface does not expose a usable capacity commitment. H88 can identify
an account-level admission-risk policy, but even a positive result would not
show front-running or recover market-wide welfare.

## Release gates and current distance

H88 releases the earliest qualifying chronological prefix regardless of sign.
It requires:

| Gate | Required | First run |
|---|---:|---:|
| complete days | 28 | 0 |
| assignments per arm | 150 | 1 / 3 / 4 |
| models | 10 | 8 |
| candidate providers | 20 | 12 |
| requested-provider dominance | at most 20% | 25% |
| pinned compliance | at least 90% | 100% in isolated artifact |
| seed replay | exact | exact |
| cross-study overlap | none | pending authoritative merged audit |

The current sample therefore supports only feasibility and data-quality claims.
It contains no releasable causal effect or confidence interval.

## Remote operation and reproducibility

The hourly workflow is `.github/workflows/enforcement-policy-probes.yml`; its
first successful run is GitHub Actions run `29424821879`. It shares the
`randomized-routing-probes` lock with H80/H81/H87, buffers private attempts and
outcome-free candidates, enters the nightly artifact assembly, and is covered
by remote health monitoring. The first run used commit `471d420`.

After the artifact is merged into the local or Hugging Face panel, run:

```bash
MPLCONFIGDIR=/tmp/mpl uv run orcap analyze --hypothesis h88 --out /tmp/h88
```

Before the release gates, the analyzer writes only `h88_summary.json`, the
outcome-free assignment-support table, and the public candidate-state support
figure. It does not write released trial rows, arm contrasts, or the effect
figure.
