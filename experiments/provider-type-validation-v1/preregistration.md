# Provider-type validation v1

## Question

Can provider-model quote histories support a stable behavioral taxonomy, and
which independently measured mechanisms are consistent with each type?

The four labels are observable provider-model-period regimes, not immutable
provider traits or motives:

1. `premium_differentiated`: not an anchor adopter and median price is at or
   above the model-author price.
2. `anchor_adopter`: price equals the model-author price on at least 80% of
   common training days.
3. `static_discounter`: median price is below the author and the provider makes
   at most 0.05 completion-price changes per observed training day.
4. `active_undercutter`: median price is below the author and the provider
   makes more than 0.05 changes per observed training day.

## Frozen split and support

Dates are ordered and the first 60% form the training panel. Labels require at
least five training days. The remaining 40% is the holdout; a transition is
evaluable after three holdout days. The split, thresholds, event windows, cost
scenario, and source revision are recorded in the release bundle.

## Evidence legs

- Persistence: repeat the same classification in the holdout and report the
  full transition matrix plus Wilson intervals for aggregate persistence.
- Premium differentiation: compare throughput and latency within model-day in
  the holdout. Better delivered QoS is consistent with differentiation but
  does not identify proprietary hardware or kernels.
- Anchor pass-through: after an author price move, measure whether and how fast
  frozen training-period types quote the new anchor within 96 hours.
- Capacity pressure: compare utilization, rate limits, deranking, and a stated
  serving-cost sensitivity across frozen types.
- Active response: after a rival public quote move, compare 24-hour repricing
  incidence with the same calculation at a frozen +48-hour shifted placebo.
  This is a timing association, not proof that a provider observed or reacted
  to the rival.
- Quote fading: after a cut, measure whether the next quote rises within seven
  days.
- Realized execution: provider-targeted `openrouter-price-response*` attempts
  measure admission/quote firmness, while `openrouter-default-probes-v1`
  attempts measure delegated selection. These are never conflated. H81 and H95
  outcomes are excluded by construction.

## Dumping claim boundary

The release reports a `dumping_candidate` screen only when an active
undercutter also clears the stated x32 batching cost screen, later fades a cut,
and is selected in an owned delegated-routing probe. A provider-targeted fill
does not clear the routed-flow leg. This is deliberately a high bar for a
candidate. It is still not a finding of predatory dumping:
marginal cost, private rebates or subsidies, intent, and later recoupment are
not observed. `dumping_supported` is therefore frozen to false in v1.

## Outputs

All row-level outputs are provider-model aggregates or public quote events.
No prompts or payload-adjacent fields are published. The bundle includes
labels, transitions, QoS, pass-through, capacity, active-response, quote-fade,
owned-fill, candidate-score, summary, source revision, and a two-format figure.
