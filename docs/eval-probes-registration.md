# Pre-registration: eval probes (quality fingerprints, graded benchmarks, shape routing)

*Registered 2026-07-18, before any panel accrual (only two same-day smoke
runs exist). Capture: `src/orcap/capture_evals.py`, daily via
`.github/workflows/evals.yml`. Tables: `eval_fingerprints`, `eval_graded`,
`eval_shape_routing`.*

## Motivation

Routing depends on the prompt (eligibility and possibly load), and quality
is the unpriced attribute in every posted-price story we test. Three
pre-declared questions:

1. **I1-Q (quality shading):** do cheaper pinned providers serve degraded
   versions of the same model? Prediction under the premium-bundle story:
   YES — divergence/accuracy gaps increase with price discount. Prediction
   under pure menu-cost pricing with homogeneous serving: NO.
2. **Shape routing:** does the default policy's provider-selection
   distribution differ between a short prompt and a 2k-token padded prompt?
   If yes, all pong-probe firmness results are scoped to the short-shape
   point and must say so.
3. **Fingerprint regimes:** deterministic-prompt hash agreement partitions
   provider pairs into same-stack / different-stack clusters; the smoke run
   already shows open-ended prompts diverge under batching nondeterminism,
   so they are EXCLUDED from agreement statistics ex ante (noise floor
   only).

## Design constants (fixed now)

- Battery: `config/eval_battery.toml` v1-20260718 — 10 deterministic
  prompts in scope for agreement stats; `open1`/`open2` excluded ex ante.
- Graded pool: `data-static/eval_items.jsonl` — 400 MMLU + 100 GSM8K test
  items, seed 20260718. Daily rotating subset: 16 MMLU + 4 GSM8K, seeded
  `orcap-eval-{dt}`, IDENTICAL items across providers/models within a day
  (paired design; rotation defeats provider special-casing of famous
  prompts).
- Providers per model: cheapest, second-cheapest, median, most expensive
  quoted (spread across the book), pinned with `only`+`allow_fallbacks:false`.
- Models: top-4 by weekly volume (same selector as the routing probes).
- Grading: MMLU = first standalone A-D letter; GSM8K = last `####` number,
  fallback last number. Non-200 after 3 backoff retries → missing, not
  wrong. Missingness itself is retained (429s are congestion data).

## Estimands and tests (primary, in order)

- **E1 (accuracy gap):** per (model, provider): P(correct) minus the
  provider-median P(correct) for that model, paired by item-day; test =
  McNemar on discordant pairs vs the modal provider. Runs per source
  (MMLU / GSM8K) and pooled.
- **E2 (discount-degradation slope):** regression of E1's gap on
  log(price / model-median price), clustered by model. Sign test:
  premium-bundle predicts positive slope (cheaper → worse).
- **E3 (hash divergence vs discount):** per provider pair within model,
  share of in-scope deterministic prompts with differing
  `output_norm_sha256`; regression of provider-level divergence-from-modal
  on log relative price.
- **E4 (shape routing):** chi-square of selected-provider distribution
  short vs padded, per model, Fisher-combined across models.

## Gates (no claims before)

- E1/E2: ≥ 25 capture days (≈ 500 graded items per provider-model) AND
  ≥ 3 providers × ≥ 3 models with < 30% missingness.
- E3: ≥ 20 days.
- E4: ≥ 40 shape-probe days per model (n≈40 per cell; selection
  distributions are concentrated, so power is limited — descriptive until
  then).
- Before gates: descriptives only, labeled `provisional_descriptive`.
- Sign flips after the gate reopen the relevant manuscript section per the
  standing rule; no additional estimands without a dated addendum here.

## Claim boundaries (standing)

Single API key; pinned requests measure the provider's serving of OUR
traffic tier; MMLU/GSM8K contamination is constant within model across
providers (differences identify serving effects, not model quality);
accuracy ceilings/floors reduce power for very strong/weak models;
providers could in principle fingerprint the battery itself — the rotating
pool mitigates for graded items, and any suspicious battery-vs-pool
agreement discrepancy will be reported.
