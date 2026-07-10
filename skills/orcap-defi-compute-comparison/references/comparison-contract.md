# Comparison contract

For every metric, record the instrument cohort, execution size, timestamp and
finality, quality/reliability dimensions, gross price, explicit fee, gas or
operational friction, and success/fill condition.

Use `market_quotes` for quotes/depth, `market_executions` for completed flow,
and `market_capacity` for resource availability. Keep AMM, RFQ, inference, and
GPU-market mechanism labels in the output. The H41 panel is a coverage layer;
it does not by itself identify a common clearing price or causal pass-through.
