# Prospective pilot-calibration amendment

Date: 2026-07-19

Applies after paid pilot run `29699310501`. The pilot artifact, assignments,
outcomes, and original preregistration remain unchanged.

## Evidence that triggered the amendment

The first run attempted all 36 frozen assignments and cost `$0.001466854`.
Twenty-six requests succeeded. The cheapest public endpoint, the model-author
`DeepSeek` endpoint for `deepseek/deepseek-v4-pro`, returned HTTP 404 for every
exactly pinned request. The second endpoint, `StreamLake`, succeeded at
concurrency 1, 2, and 4. This makes the author endpoint useful as a phantom-
liquidity diagnostic but leaves only one operational endpoint in the original
liquidity comparison.

All four successful quality requests consumed the six-token output cap without
emitting an extractable answer. They remain valid success/latency/cost records,
but not graded quality observations.

## Prospective changes

Starting with the first immutable plan produced after this amendment:

1. retain the cheapest and second-cheapest endpoint arms exactly as specified;
2. add the third-cheapest endpoint to the pinned liquidity batches at concurrency
   1, 2, and 4;
3. add the third-cheapest endpoint to the paired MMLU block;
4. set the quality output floor to 64 tokens; and
5. request minimal reasoning effort and exclude reasoning text from the response.

The assignment total rises from 36 to at most 45: up to 14 competition, 2 memory,
21 liquidity, and 8 quality requests. As in the original protocol, the two
`capped_top2` assignments are omitted when the cheapest pair is not separable by
OpenRouter's rectangular prompt/completion price cap. The same hard
run/day/campaign quote-cap gates apply. No pilot outcome is pooled into a
confirmatory cell without an explicit vintage indicator, and no provider ranking
is reported below 20 realized observations per cell.
