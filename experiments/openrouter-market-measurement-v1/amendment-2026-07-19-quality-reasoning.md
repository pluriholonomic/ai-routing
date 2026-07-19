# Prospective amendment: final-answer token preservation

Date: 2026-07-19

This amendment was frozen after the second paid calibration run
`github-29699876639` and before any subsequent paid assignment was planned.
That run executed all 45 frozen assignments: 35 requests succeeded at a total
realized cost of $0.00213864423. Six of eight paired-quality requests returned
HTTP 200, but every successful response consumed the 64-token output allowance
without returning final-answer content, so no MMLU answer could be graded.

The public OpenRouter model record at calibration time reported that
`deepseek/deepseek-v4-pro` had optional reasoning and supported `xhigh` and
`high` effort only. The prior `minimal` request could therefore be mapped to a
supported positive effort and exhaust the short answer allowance. OpenRouter's
public reasoning interface defines `effort: none` as disabling reasoning when
reasoning is not mandatory.

For all plans created after this amendment:

1. the paired-quality request uses `reasoning: {effort: none, exclude: true}`;
2. the 64-token output floor, benchmark-item selection, provider arms, price
   caps, temperature, privacy contract, and all non-quality assignments remain
   unchanged; and
3. a model for which reasoning is mandatory may reject the quality request;
   such a response is an explicit unsupported cell and is never imputed.

The two calibration runs, `github-29699310501` and `github-29699876639`, remain
immutable and labeled as pilots. They are excluded from confirmatory estimates
but retained for operational accounting and transparent failure analysis. No
provider outcome, answer, or cost from a subsequent run was inspected when this
amendment was written.
