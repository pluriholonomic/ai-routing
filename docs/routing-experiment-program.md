# Routing-mechanism experiment program

## What is active now

The repository continuously captures public endpoint quotes, quote-triggered
burst windows, congestion aggregates, public router-enforcement fields, and
decentralized-compute/DeFi controls.  The following analyses are live and
strictly public-surface measurements:

- H43/H66/H67: simulated routing response, rank changes, and quote-pulse/fade
  candidates;
- H68: public rate-limit incidence and contiguous derank-state transitions;
- H69: one readiness ledger covering all public, private, and comparator gates.

These components do not issue inference requests, change a router policy,
send a partner request, publish data, or imply an actual selected provider.

## Experiment sequence

| Stage | Test | Required data | Gate | Strongest permitted conclusion |
|---|---|---|---|---|
| 1 | Public quote pulse and enforcement | endpoint snapshots, burst samples, rate-limit/derank states | 168 continuous hours, 80 cuts, 50 derank onsets | public quote or enforcement dynamics |
| 2 | H43 simulator calibration | payload-free owned route attempts with selected provider | 2,000 selected attempts | simulation predicts owned selections |
| 3 | H14/H42 reliability and stale quote | quote-linked owned attempts, fallback/outcome metadata | 1,000 quote-linked attempts; 100 event opportunities | owned admission/fallback or stale-quote association |
| 4 | Residual-flow anticipation | fixed-interval provider-model selected-flow aggregates plus action timestamps | 28 complete days and 100 repricing episodes | public-state-adjusted aggregate flow association |
| 5 | H70 pre-selection access | timestamped router records and randomized visible, blinded, decoy signal arms | 200 events in each randomized arm | causal effect of provider visibility on in-window action |
| 6 | Observable controls | source-specific finalized/allocation or aggregate external panels | 30 common days and 50 observable allocation events per venue | cross-venue methodological control |

Coverage gates are stored in [`config/experiment_gates.toml`](../config/experiment_gates.toml);
the fixed H67 quote-event definition remains in
[`config/quote_pulse.toml`](../config/quote_pulse.toml).  They are activation
thresholds, not positive findings.

## Readiness ledger

Run against the hydrated dataset:

```bash
ORCAP_ANALYSIS_SOURCE=local uv run orcap analyze --hypothesis h69 --out analysis
```

The output `h69_experiment_readiness.parquet` reports every metric as
`not_collected`, `power_gated`, or `ready`.  The accompanying JSON keeps the
public and private claim boundary visible in dashboards and reports.

## Owned-routing activation

The controlled probe and policy experiments are intentionally inactive until
an operator supplies a study account, hard spend and rate caps, a pre-outcome
manifest, and explicit collection authorization.  When activated, each record
must use `router_route_attempts`; no prompt, completion, account, or credential
field is accepted.  H43/H14/H42 use blocked time/model inference and retain a
held-out tail of time blocks for confirmation.

## Aggregate-flow and private-ordering upgrades

H69 tracks two private contracts:

- `router_flow_aggregates`: fixed provider-model intervals with attempts,
  selections, completions, fallbacks, candidate-set version, quote snapshot
  reference, and action timestamp.  This supports the residual-flow test
  without exposing a request payload or an individual customer.
- `router_decision_events`: a payload-free event ledger with arrival, route
  commitment, candidate-set version, selected endpoint, retry outcome,
  provider signal, and quote/capacity action time.  H70 labels whether an
  action lies inside the selection window and whether it follows the recorded
  provider signal.

The direct test requires randomized `provider_visible`, `provider_blinded`,
and `decoy_signal` arms, each with an `assignment_id` that can be audited
against an immutable randomization manifest.  An observational timestamp
sequence is useful for auditing data quality but cannot establish intentional
front-running.

## Analysis discipline

All event studies use a frozen event definition, matched quiet windows,
provider/model/time controls, and blocked forward validation.  Hawkes or
Poisson--Dirichlet/Dirichlet-multinomial model comparisons are descriptive:
they distinguish timing clustering from allocation concentration, but neither
model proves private information.  A literal front-running label remains
reserved for a valid randomized private-signal study with verifiable ordering.
