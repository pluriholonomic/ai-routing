# Price-score manuscript evidence audit

Freeze: 2026-07-21. Prospective score-analysis commit: `285523e`; comparative
time-series commit: `c5194ca`. This audit applies to the EC, ICML, and NeurIPS
venue drafts in this repository.

## Claim ledger

| Object | Evidence in the manuscripts | Status | Permitted interpretation |
|---|---:|---|---|
| Public price surface | 22,330 model-timestamp snapshots, seven non-free open-weight model panels, 2026-07-07 through 2026-07-21 | Descriptive, deterministic | Conditional share under the declared inverse-power rule |
| Point routing exponent | 1.6483; sensitivity range 1.26--2.04 | Frozen external estimate plus rule sensitivity | A price-rule parameter, not demand elasticity |
| Benchmark discounts | Model medians 13.0%--40.0% | Deterministic public-menu calculation | Distance from author or disclosed anchor benchmark |
| Excess active shadow share | Model medians 1.40--10.98 percentage points | Exact benchmark-reset counterfactual | Mechanical share transfer, not realized routing |
| GLM-5.2 transfer | 27.3% median discount, 10.98 excess active points, 5.40 anchor-loss points | Exact benchmark-reset counterfactual | The largest median transfer surface in this seven-model panel |
| Time variation | Hourly medians of discount, excess shadow share, and group arc elasticity | Descriptive time series | Menu regimes and price-rule sensitivity; no causal response |
| Latent non-price score | Prospective GLM-5.2 owned-choice estimator | Accruing; zero eligible choices at the manuscript freeze | No fitted live score, score-adjusted share, or cross-model score comparison yet |
| Price-sort contrast | Randomized explicit price-sort versus default owned requests | Accruing behind the same prospective support gate | Design only; no live rule-effect result yet |
| Provider quote regimes | Frozen WF16 labels, 94.4% overall holdout persistence | Descriptive behavioral taxonomy | Quote behavior, not cost type or intent |
| QoS premium | Current holdout tests have no detectable premium advantage | Negative/underpowered | No positive premium-quality claim; not equivalence |
| Signal coupling | Focal nominal statistic and positive UCB simulation; concentration and identity gates fail in live data | Mechanism-supported, transport-negative | Motivation for the mechanism, not evidence of provider collusion |
| Critical memory | Exact boundary, late-path bound, and frozen finite-MDP simulation | Theoretical plus simulator-validated | A mechanism result; not a live-provider memory estimate |
| Hardened router | One-step quote and identity gains fall, first post-UCB learning gate fails | Mixed simulator result | Mechanical robustness does not imply learning robustness |

## Cross-paper boundary

The manuscripts may say that displayed prices create a large *conditional
manipulation surface* and that hidden scoring can theoretically attenuate or
amplify it. They may not say that the public panel measures realized market
share, provider revenue, demand elasticity, dumping, front-running, tacit
collusion, or welfare. The prospective score cell is missing data, not a zero
effect. Cross-model score plots must wait for owned-choice support in more than
one model.

## Artifact checks

- `wf19_model_comparison_timeseries.{pdf,png}` is generated from the frozen
  WF19 parquet and excludes zero-priced endpoints.
- The EC and NeurIPS sources include the price-surface claim boundary in their
  captions. The ICML source intentionally excludes the price figures and states
  that the separate evidence ledger is not an input to its payoffs, memory law,
  or confirmatory gates.
- The EC, ICML, and NeurIPS PDFs build without missing references.
- The new figure and neighboring pages were rasterized and visually inspected;
  labels, legends, axes, and captions are readable with no clipping.
