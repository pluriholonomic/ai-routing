# Information-congestion v1 data dictionary

All public tables set `payload_retained=false`. Request-level attempts are
private; only redacted aggregates cross the release boundary.

| Table | Grain | Important fields | Visibility |
|---|---|---|---|
| `ic_market_epochs` | model x frozen live menu | `market_epoch_id`, `model_id`, `eligible_n`, `menu_sha256`, source time | public |
| `ic_provider_roles` | epoch x provider | provider key, ex-ante responsiveness, price-change count, coverage, signal cluster | public |
| `ic_candidates` | epoch x endpoint | compatible quote fields and endpoint tag | private until aggregated |
| `ic_assignments` | randomized request | `n`, `k`, overlap arm, router rule, selected provider tags, protocol and manifest hashes | public assignment-only |
| `ic_attempts` | randomized request outcome | selected provider, success, latency, fallback, cost, redacted metadata | private |
| `ic_quality_assignments` | balanced benchmark request | frozen model, exact provider pin, public item ID and answer hash | public assignment-only |
| `ic_quality` | exact-pin benchmark grade | correctness, success, latency, token counts, hashes, no prompt or completion | private |
| `paid_spend_ledger` | attempted task | task ID, realized cost, manifest hash | private |
| `ic_common_shocks` | public event | type, event time, pre/post source runs, contamination flags | public |
| `ic_rank_panel` | model epoch x subset size | effective rank, factor transport, provider subset hash | public aggregate |
| `ic_outcome_surface` | `n x k x overlap x rule` | choices, success, cost, latency, fallback, operational surplus | public aggregate |
| `ic_kstar_scaling` | supported menu size | argmax confidence set, `k*/n`, tau estimates and gates | public aggregate |
| `ic_run_ledger` | workflow plan | source health, planned tasks, protocol hash, no outcomes | public |
| `ic_readiness` | audit run | capture, reconciliation, freshness, privacy, and budget gates | public |

`n` is ex-ante compatible provider count. `k` is the number of pre-period
responsive providers included in the randomized eligible menu. Neither is
redefined using paid outcomes.
