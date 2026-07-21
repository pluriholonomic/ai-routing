# Strategic routing environment

StrategicRoutingParallelEnv is the smallest supported API for training or
auditing inference-provider strategies against a router. It wraps exact
request-level settlement while keeping provider-private technology out of agent
observations.

## Run the deterministic example

    uv sync --group dev
    PYTHONPATH=src uv run python examples/strategic_routing_demo.py

The example creates an owned-capacity provider and a spot-dependent provider,
runs four simultaneous quote epochs under inverse-price routing, and prints
provider rewards, user utility, social welfare, and the reconciliation error.
Running it twice with the same seed produces byte-equivalent JSON.

## API

    observations = env.reset(seed=17)
    transition = env.step(
        {
            "owned": ProviderAction(quote=0.80),
            "spot": ProviderAction(quote=0.95),
        },
        demand=6,
    )

The transition contains:

- observations: public quotes plus each provider's own previous settlement;
- rewards: provider profit after attempt and installed-capacity cost;
- terminations and truncations: parallel-agent episode state;
- infos: own attempts, completions, technical failures, and capacity rejects;
- market_result: evaluator-only request and aggregate accounting.

The provider observation never contains rival marginal cost, physical capacity,
or reliability. Evaluators may inspect market_result; learning policies should
not.

## Replace the router or provider policies

Construct MarketKernel with any router implementing the repository's router
protocol. The built-in mechanisms include random, inverse-price,
quality-adjusted, cut-memory, menu-projected, and hardened adaptive rules.
Provider actions jointly set quote, admitted-capacity fraction, and availability
state. Static, calibrated-species, UCB, epsilon-greedy, Q-learning, and scripted
adversarial policies use the same action surface.

For paired mechanism comparisons, reset each arm with the same base seed.
Reliability, routing, and fallback use stable event-specific random substreams,
so a router change does not silently redraw technical outcomes.

## What a passing run means

The kernel can establish exact accounting, deterministic replay, capacity
conservation, and conditional performance under declared costs and user values.
It cannot turn public menus into observed market-wide routing, identify private
provider algorithms, or establish live welfare. Use the property ladder in
papers/neurips/price-of-softmax.tex: invariants, intervention fidelity, held-out
properties, adversarial robustness, then prospective transport.

## Focused validation

    uv run pytest -q tests/market_env/test_rl_env.py tests/test_strategic_routing_demo.py

The tests enforce deterministic replay, information boundaries, episode
termination, reward reconciliation, and the example's public contract.
