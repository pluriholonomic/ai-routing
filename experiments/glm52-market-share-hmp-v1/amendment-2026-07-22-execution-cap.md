# Execution-cap clarification

Date: 2026-07-22 UTC.

This amendment was written after the first two hourly background blocks and
before any request-level or arm outcome was inspected. It does not change an
arm, event, support gate, estimand, analysis, or stopping rule.

The frozen assignments specified `max_output_tokens = 1`, and their aggregate
quote-cap field was computed with one output token. The shared paid-probe sender
nevertheless used the generic `short_chat` shape default of eight output tokens
for those first two blocks. Those 24 requests remain usable as matched routing
choices because all six arms used the same fixed prompt template, output limit,
temperature, and randomized order within each block. Their published
`planned_quote_cap_usd`, however, is an assignment-side planning cap and must
not be described as the true worst-case execution cap.

Before the next block, the sender was changed to honor the immutable
assignment's `max_output_tokens` field. All later requests therefore implement
the frozen one-token design. Analysis must flag the first 24 assignments as
`legacy_eight_token_cap`, report their inclusion and exclusion as a protocol
sensitivity, and never treat the amendment as outcome-driven. The neutral
prompt template is matched in semantics and length but includes a unique inert
nonce and fresh session identifier per task; paper prose should say “matched
fixed-template probes,” not “byte-identical prompts.”
