# Executable validation plan for the inference-routing welfare conjecture

This plan operationalizes C1-C10 in `docs/welfare-theory-framework.md`. It
separates tests of assumptions from estimates of outcomes. Public quote and
token panels can reject simple score sufficiency and bound sensitivities; only
owned randomized routing can identify policy welfare in the study domain.

## Pipeline

| Module | Role | Output |
|---|---|---|
| WCV0 | freeze HF table coverage and missing-data layers | `wcv0_data_inventory.parquet` |
| WCV1 | map C1-C10 to supported, inconsistent, gated, or unidentified evidence | `wcv1_condition_audit.parquet` |
| WCV2 | cadence-neutral allocation/price sensitivity over demand and cost scenarios | `wcv2_welfare_scenarios.parquet` |
| WCV3 | provider best-response regret and user price-only regret | `wcv3_*_regret.parquet` |
| WCV4 | aggregate owned attempts; refuse OPE without propensities and overlap | `wcv4_policy_panel.parquet` |
| WCV5 | conservative integrated claim verdict | `welfare_conjecture_verdict.json` |
| dashboard | script-free inspection panel | `welfare_validation_panel.html` |

## Identification ladder

1. **Public descriptive:** quotes, quality proxies, token allocations,
   congestion and enforcement. Permits association, competitive-null screens,
   and coverage statements.
2. **Calibrated sensitivity:** scenario costs and demand elasticities. Permits
   transparent directional bounds, never a structural welfare claim.
3. **Owned realized routing:** selected provider, cost, latency, fallback and
   quote link. Permits study-traffic calibration and descriptive policy
   outcomes.
4. **Registered randomized routing:** manifest, assignment probabilities,
   valid epochs and registered value. Permits a causal policy contrast in the
   study domain.
5. **Market welfare:** additionally needs representativeness, user value,
   provider cost/capacity curves, fidelity loss, retry externalities, and
   transfer treatment. This remains a separate promotion gate.

## Decision rule

The conjunction “selfish optimization approximately attains welfare” is not
licensed unless every critical C1-C10 condition is supported and the
registered routing experiment clears design and power gates. Missing
conditions remain `not_identified`; they are never imputed as true. An observed
failure such as unpriced retries or a fidelity/lemons association means the
decentralization conditions are not currently satisfied, but does not by
itself estimate the welfare loss or falsify the logical iff conjecture.

The primary false shortcut is a static price-only score. It is rejected when
the observed share-price elasticity differs from the advertised inverse-square
rule and delivered-quality evidence predicts price or endpoint failure. The
replacement is a capacity- and reliability-aware randomized policy contrast,
not another observational composite score.

## Reproduction

Run dependencies first, then the validation modules:

```bash
uv run orcap analyze --hypothesis h4
uv run orcap analyze --hypothesis h11
uv run orcap analyze --hypothesis h48
uv run orcap analyze --hypothesis h50
uv run orcap analyze --hypothesis h54
uv run orcap analyze --hypothesis h69
uv run orcap analyze --hypothesis wcv0
uv run orcap analyze --hypothesis wcv1
uv run orcap analyze --hypothesis wcv2
uv run orcap analyze --hypothesis wcv3
uv run orcap analyze --hypothesis wcv4
uv run orcap analyze --hypothesis wcv5
uv run orcap analyze --hypothesis wcv_dashboard
```
