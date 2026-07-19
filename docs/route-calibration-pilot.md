# H96 route-calibration pilot: operator guide

H96 replaces the least realistic part of the dry run—a mechanically assumed
inverse-square allocation—with a small owned-request panel that measures which
provider OpenRouter actually selects under frozen public menus.

The scientific protocol is
`experiments/h96-route-calibration-v1/preregistration.md`. The reusable
simulation workflow is `skills/orcap-strategic-routing-simulation/SKILL.md`.

## What runs remotely

`.github/workflows/route-calibration.yml` has 12 intended scheduled starts:
01:37, 05:37, 09:37, 13:37, 17:37, and 21:37 UTC on July 19 and 20, 2026. It
shares `randomized-routing-probes` concurrency with H81/H95, so delayed jobs
serialize rather than overlapping owned routing experiments.

Each start freezes public candidate and assignment tables before paid calls,
then sends at most 192 requests. The request loop is deliberately slow enough
to avoid a concentrated burst. Generation metadata provides the selected
provider, latency, token counts, and cost.

Hard cost controls:

- `$0.35` maximum quote cap per run;
- `$4.20` maximum across 12 scheduled starts;
- paid execution rejected outside the two-day UTC window;
- manual dispatch always performs no-spend preflight only;
- prompts, completions, API keys, and raw session IDs are never stored.

The existing `OPENROUTER_API_KEY` GitHub secret is used. No workstation process
is required after the workflow is pushed.

## Local no-spend preflight

```bash
ORCAP_DATA_DIR=/tmp/h96-preflight \
  uv run python -m orcap.capture_route_calibration --preflight-only
```

Verify:

- 24 eligible model-shape blocks unless the live menu changed;
- 192 planned assignments for a fully eligible run;
- two distinct exact-tag pin providers per eligible block;
- one sticky pair hash and unique hashes for independent draws;
- planned quote cap below `$0.35`;
- candidate and assignment parquet files exist;
- no `router_route_attempts` file exists.

## Remote no-spend preflight

```bash
gh workflow run route-calibration.yml
gh run list --workflow route-calibration.yml --limit 3
```

Download the successful artifact and repeat the local parquet/privacy checks.
Do not pass an undocumented paid flag; none is exposed by the workflow.

## Assemble and analyze

The daily artifact assembler includes `route-calibration.yml`. After paid runs
have been compacted or downloaded:

```bash
ORCAP_ANALYSIS_SOURCE=local \
  uv run python -m orcap.analysis.h96_route_calibration \
  --out analysis/h96-route-calibration
```

Before four run timestamps, the summary labels scores in-sample. At four or
more, the final 30% of run timestamps form a chronological holdout. Fitting is
deferred until there are at least 20 covered independent default choices.

## Reading the outputs

- Candidate coverage below one means a realized provider was absent from the
  compatible public menu or could not be matched by display name. Investigate;
  do not silently drop it.
- `eta_hat` estimates price sensitivity only inside the bounded owned-probe
  choice sets. Compare its held-out loss with the documented `eta=2` rule under
  both the request-shape all-in quote and mean prompt/completion price index.
- Sort-price matches validate public price-order semantics at provider grain.
- Pin failures are eligibility/firmness diagnostics, not automatically phantom
  liquidity.
- Sticky repeat agreement measures session affinity. Exclude repeats from the
  independent choice fit.
- Cost regret is relative to public quoted token cost for the request shape,
  not a quality-adjusted welfare loss.

The panel cannot measure market-wide routed share, cross-user ordering,
provider intent, literal front-running, or exact endpoint variants when only a
provider name is returned.
