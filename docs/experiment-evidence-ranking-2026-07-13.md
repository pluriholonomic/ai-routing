# Experiment evidence ranking — 2026-07-13

This is a ranking of **conclusions**, not a league table of effect sizes or
paper claims.  It gives priority to direct measurement, repeated observations,
out-of-sample validation or a valid uncertainty estimate, and the extent to
which the conclusion bears on the central routing/market-design question.
No result below identifies provider intent, realized router selection,
front-running, adverse selection, profit, welfare, or a causal market effect
unless explicitly stated.  None currently clears that standard.

The ranking uses the checked-in local analysis artifacts and a fresh,
read-only local rerun of H43/H66--H70 on 2026-07-13.  The local H43 panel now
contains only one retained `routing_simulation` snapshot; the endpoint replay
in H67 has nearly five days of five-minute coverage.  A prior remote H43
artifact must not be treated as a current reproducible result until it is
rehydrated.

## Ranked conclusions

| Rank | Experiment(s) | Conclusion supported now | Evidence | Why it ranks here / boundary |
|---:|---|---|---|---|
| 1 | H4 | Aggregate **observed effective-provider token share** is price-sensitive, but materially less elastic than the documented inverse-square rule: elasticity `-1.19` (SE `0.17`; `746` provider observations, `147` model-day groups). | Clustered within-group regression; the `-2` benchmark is about 4.8 SE away. | Closest current evidence to price-sensitive allocation. It is aggregate provider token volume, not a request-level selected-provider event or a causal price experiment. |
| 2 | H18 | Historical listed-price changes are predictably state-dependent: exposure-stripped future AUC `0.817` (`13,666` held-out pairs; `1,069` changes overall). Direction conditional on a change is only moderate (AUC `0.656`). | Strict temporal holdout over `39,179` historical model-snapshot pairs. | Strong predictive evidence for repricing regularity, not a structural/casual price-setting model. Snapshot-gap features matter, so this is not an intraday forecast. |
| 3 | H1 + H17 | Repricing is lumpy and cut-heavy: `1,082` historical changes among `39,486` snapshot pairs; `57%` are cuts, median absolute log change `0.255`, and younger models cut more often than models older than one year. | Direct historical event accounting across `682` models. | High-confidence description of the captured price history. Irregular Wayback spacing makes the event rate a lower bound and does not identify strategic motive. |
| 4 | H11 | Cheap endpoints are disproportionately high-tool-error: `55.8%` bad among cheap versus `37.9%` among expensive within-model endpoints (`chi²=9.42`, `p=0.0021`, `n=410`). Delivered public performance fields explain about `31.9%` of remaining within-model price variation in the matched sample. | Cross-sectional endpoint match; `337` hedonic rows, `410` lemons rows. | A clear quality/price association, but public performance metrics are incomplete and contemporaneous. It is not a fill, outcome-quality, or adverse-selection result. |
| 5 | H5 + H71 | Visible app/harness order flow is concentrated yet multihomed; however, its **normalized allocation shape adds no reliable next-day demand prediction** beyond lagged model activity. | H5: `304` models, median observed app HHI `3197`, max app appears in `155` model top lists. H71: `495` model-days / `250` models; Δ OOS R² `+0.00019`, 95% cluster-bootstrap CI `[-0.00045, +0.00097]`. | This is a useful negative result. App lists are top-N and their counter window is undisclosed, so it does not describe total app routing or prove application irrelevance. |
| 6 | H38 + H39 | Routed demand is strongly overdispersed and persistent at observable intervals: median 30-minute Fano factor `1012`, daily median CV `0.459`, and median INGARCH persistence `0.746`. | `267` endpoints for intraday burstiness; `286` models for daily activity; `255` fitted endpoint series. | Strong descriptive operational finding. Counts are rolling/interval-censored; the Fano statistic is not a raw-arrival Hawkes estimate. |
| 7 | H3 | More listed suppliers coincide with materially lower minimum listed prices: relative to one provider, four- and five-plus-provider groups are roughly `64%` and `68%` lower in the cross-section. | `300` model rows; implied z-statistics are about `-2.55` and `-3.88` for the four and five-plus categories. | Direction is robust enough to be useful, but this is cross-sectional entry/quality selection, not an event-study estimate of entry causing a cut. Naive GPU markups are explicitly not interpretable levels. |
| 8 | H23 | The constructed high-cost/toxic-flow proxy is associated with more public rate limiting (`+0.0098`, SE `0.0045`, `p=0.029`, `579` matched model-days). | Day-fixed-effect association over 33 days. | Suggestive router-rationing evidence, but the index is constructed from activity and error proxies and omits model fixed effects; it should not be used as causal or as provider behavior. |
| 9 | H20 | Hotter models have more listed providers (Spearman `0.64`) and a higher repricing hazard conditional on level (OR `1.42`, `p=0.0002`). | `294` models; hazard panel `9,172` model-days. | The event count is only `16`, so the nominal significance is not sufficient for a strong demand-elasticity claim. Lagged growth has the opposite sign (OR `0.26`), reinforcing that this remains preliminary. |
| 10 | H2 | More-provider models have **greater**, not lower, listed-price dispersion (elasticity `1.65`, SE `0.81`, `p=0.042`), but the model explains only `2.4%` of dispersion. | `85` multi-provider model observations; median max/min price ratio `1.82`. | A weak but interesting rejection of a simple law-of-one-price story. Endpoint heterogeneity and a low R² make the economic magnitude uncertain. |
| 11 | H10 | There is no detected cross-sectional cheap-quote/rejection relationship: price slope `0.033` (SE `0.021`, `p=0.118`) across `1,832` endpoints. | Large one-snapshot public enforcement panel. | Best current *negative* screen against the simplest phantom-liquidity prediction. It cannot rule out quote-linked or intraday last look. |
| 12 | H6 | Effective input price is typically below listed input price (median ratio `0.930`; p10 `0.386`), consistent with cache effects rather than a uniform quoted-to-paid spread. | `525` provider-model pairs; median cache-hit rate `21.5%`. | Direct accounting fact but a single latest-day comparison; it does not measure execution cost, markups, or take-rate incidence. |
| 13 | H40 | The current operational decomposition puts a **lower bound** of `23.5%` of router tokens in either free-tier or no-first-party-API channels. | One complete activity day plus 52 weekly aggregate observations. | A useful market-structure lower bound, not demand caused by the router. The failover and price-response legs are gated. |
| 14 | H12 + H35 + H36 | Compute quotes show a large on-demand/interruptible basis (median `1.41×`), but duration/carry comparisons are sparse and cross-venue. | `11` current GPU runs; duration buckets contain 6--9 observations. | Descriptive price segmentation only. It is not an executable, matched-spec arbitrage result. |
| 15 | H37 | Router-estimated capacity ceilings scale roughly proportionally with measured load (slope `0.833`, SE `0.074`), while the public latency-load association is slightly negative. | `253`--`416` endpoints, depending on subtest. | The router's capacity ceiling is an estimate, not certified capacity; do not infer actual overcapacity or congestion technology. |
| 16 | H7 + H26 | No usable macro GPU-to-token-price relationship or historical entry pass-through is established. H7 has only 4--6 coarse segment periods; H26's `532` approximate LiteLLM entries do not show average incumbent cuts after entry. | Coarse period correlations and approximate base-name event matching. | The negative/small effects are too confounded for economic conclusions. They are retained mainly as diagnostics and a reason to prioritize a matched live panel. |
| 17 | H67 | Public quote replay finds `41` independent ≥5% cuts and `14` pulse candidates over `4.96` days, but no complete 1,440-minute follow-up. | `1,007` five-minute snapshots across 20 models. | Screening signal only: below both gates (7 days, 80 cuts), and simulated share is mechanically generated from the price rule. |
| 18 | H13 | Posted direct and OpenRouter prices match exactly for `96.6%` of `263` matched pairs. | Only 3 days; pair concentration in DeepInfra and several providers below the per-provider minimum. | Consistent with posted-quote passthrough, but explicitly power-gated; it says nothing about fills, router selection, fees, or latency. |
| 19 | H43 + H66 | The inverse-square simulator is a deterministic **public quote-surface calculation**, not empirical routing evidence. The current local `routing_simulation` import has one snapshot, so no temporal simulation result is reproducible in this audit. | Fresh local H43/H66 rerun: 1 snapshot, 0 transitions/events; 63.7% exact public operational-metric completeness in H66. | Do not rank a mechanically generated allocation as a finding about realized flow. Rehydrate the retained remote artifact before reporting even a public-surface sensitivity rate. |
| 20 | H68 | Public rate limits are observed, but no contiguous derank onset/release is observed in the current imported enforcement subset. | Fresh rerun: 89 positive rate-limit rows, 0 contiguous transitions. | No derank-hazard conclusion; public enforcement aggregates cannot identify ordering or intentional behavior. |
| 21 | H42 + H70 | No evidence on routing capture, stale-quote capture, or literal front-running. | H42 has 0 balanced intraday event windows; H70 has 0 decision events and no randomized arms. | Not a negative result—these claims are not identified without controlled/partner telemetry. |
| 22 | H41, H47, H51--H64 | No completed DeFi-versus-open-compute causal/execution comparison. | External panels have one or a few days/captures, incomplete observability, or no complete canonical book. | The collectors and claim boundaries are valuable infrastructure, but they do not yet support a cross-market empirical conclusion. |

## Bottom line

The strongest current story is **not MEV**. It is a price-sensitive but not
purely mechanical routing market with substantial quality heterogeneity,
predictable/lumpy repricing, concentrated observable app order flow, and
bursty demand.  The app-allocation test is currently a clean null: once past
model activity is included, visible allocation shape adds no measurable
next-day explanatory power.

The central unresolved question—whether providers strategically react to
private flow, use transient public quotes to capture realized routing, or
front-run—has **no identified result**.  The immediate empirical priority is
not another public cross-section: it is a controlled, payload-free
selected-provider/fallback/outcome panel, followed by a pre-registered
quote-event study.

## Explicitly gated or non-results inventory

| Group | Present status |
|---|---|
| H8, H21, H29, H32, H33 | Too few current live repricing events/windows for burst, reaction, elasticity, quantile-war, or provider-scorecard conclusions. |
| H14 | Variant shares are descriptive from one day; the planned interaction needs weeks. |
| H19/H19b | Provider clustering is descriptive and weakly separated (silhouette about `0.08`); it is not an economic taxonomy. |
| H34 | Synthetic/public quote-book metrics are descriptive, not firm order-book depth or execution impact. |
| H41, H47, H52, H55--H59, H61--H64 | Source/coverage gates have not cleared; no dynamic comparison, complete book, execution allocation, utilization, or market-wide demand claim. |
| H44--H46, H48--H54, H60, H62 | No local result suitable for ranking, or a theory/design artifact only. Their intended claims require the corresponding public panel or controlled telemetry. |
| H69 | Readiness audit: 0 ready gates, 2 power-gated public gates, and 10 not-collected private/comparator gates. |

## Reproduction sources

- Local summary artifacts: `analysis/h1_summary.json` through
  `analysis/h42_summary.json`, `analysis/h68_summary.json`, and
  `analysis/h71_summary.json`.
- Fresh local, temporary rerun on 2026-07-13: H43, H66, H67, H68, H69, and
  H70.  The rerun is intentionally not copied over the existing tracked
  analysis directory because H68 previously contains a different exploratory
  competition-factor artifact.
- Cross-market gates: [authoritative empirical audit](authoritative-empirical-audit-2026-07-10.md) and
  [routing experiment program](routing-experiment-program.md).
