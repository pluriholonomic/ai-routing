# SM4 LiteLLM executable-router conformance

- LiteLLM release: `1.92.0`
- Source commit: `1e62de30d40e49ac6ee7904edb44b42a0be95ff9`
- Stochastic fixtures: 5 at 10,000 selections each
- Sequential fallback trials: 10,000
- Maximum absolute share error: 0.732 pp
- All registered conformance rows pass: **True**

## Interpretation

This validates LiteLLM 1.92.0 deployment filtering, weighted selection, sequential exclusion, and scalar lowest-cost selection on synthetic fixtures. Inverse-price scores are explicitly mapped into LiteLLM weights; this is not evidence that LiteLLM or OpenRouter natively uses inverse-price routing, and it does not validate live production state, queueing, latency, or provider conduct.

## Limitations

- LiteLLM exposes blocked status but not our economic exclusion reason; the adapter preserves the reason separately.
- LiteLLM cost-based routing sums configured input and output unit prices; fixtures split the scalar quote equally across them.
- No model request is sent, so fallback execution and service-system fidelity remain outside this experiment.
