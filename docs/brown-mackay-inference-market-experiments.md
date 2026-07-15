# Brown-MacKay experiments for inference-provider pricing

## Question and null

Brown and MacKay show that heterogeneous pricing technologies can generate
high prices and dispersion in a competitive Markov equilibrium: fast firms
react to slow firms, while slow repricing acts as a commitment technology. In
this market the provider's observable pricing technology is

`A_i = (update cadence, reaction rule, attention/technology cost proxy)`.

This is the first competitive null to clear before interpreting rigidity,
restoration after cuts, or correlated moves as collusion. The retail magnitudes
in Brown-MacKay are benchmarks, not transferable estimates.

## Executed sequence

| ID | Estimand | Artifact | Promotion gate |
|---|---|---|---|
| BM1 | provider cadence class, timing concentration and entropy | `bm1_provider_cadence.parquet` | 30 panel days |
| BM2 | fast-provider response after a slow rival move, minus an equal pre-event placebo | `bm2_reaction_panel.parquet` | 80 independent waves and 30 focal risk pairs |
| BM3 | fast-provider log-price coefficient within model-day, before and after public quality controls | `bm3_premium_coefficients.parquet` | 30 panel days; mixed cadence markets |
| BM4 | temporal holdout error of state-only versus cadence/reaction-rule models | `bm4_reaction_rules.parquet` | 100 linked reactions |
| BM5 | competitive-null horse race before Edgeworth or collusion language | `bm5_model_comparison.parquet` | BM2-BM4 jointly survive |

BM2 thins same-model quote clusters into initiating waves separated by six
hours. After the 2026-07-15 refresh showed that one additional NextBit price
change moved the provider from weekly to daily and reduced the focal risk set
from 15 to 3, we identified outcome look-ahead in using full-panel cadence
classes. The promoted BM2 screen now freezes cadence classes on the first 70%
of events, evaluates only later waves, and drops waves without a complete
24-hour response window. The original full-panel result remains in the output
as an explicitly outcome-adaptive sensitivity. BM4 uses the same frozen
training-period cadence classes in its temporal holdout. This is a disclosed
bias correction after seeing aggregate BM2 results, not an original
preregistration claim.

BM3 absorbs model-day price levels and controls for public throughput,
latency, and uptime. BM4 trains on the first 70 percent of time and evaluates
on the final 30 percent. These choices are fixed in
`config/welfare_conjecture_gates.toml`.

## Interpretation rule

Call Brown-MacKay the *preferred competitive null* only when:

1. fast repricers have a stable quality-adjusted within-product price
   difference;
2. fast repricers move more after slow rivals than in their own pre-event
   placebo window; and
3. cadence/reaction variables improve temporal holdout prediction over the
   state-dependent menu-cost baseline.

Even all three do not prove the Brown-MacKay mechanism. Common cost or demand
news, endogenous pricing-stack adoption, author anchors, and hidden fidelity
can reproduce parts of the pattern. Collusion additionally requires evidence
that competitive twins cannot explain: costs/margins, persistent causal IRFs,
common-vendor adoption, or threat-free calibrated regret.

## Reproduction

```bash
uv run orcap analyze --hypothesis bm1
uv run orcap analyze --hypothesis bm2
uv run orcap analyze --hypothesis bm3
uv run orcap analyze --hypothesis bm4
uv run orcap analyze --hypothesis bm5
```

The public reference is Brown and MacKay, “Competition in Pricing Algorithms,”
*AEJ: Microeconomics* 15(2), 2023, DOI 10.1257/mic.20210158.
