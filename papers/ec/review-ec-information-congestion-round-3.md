# Adversarial ACM EC review: information-congestion revision

## Summary

The paper studies an AI inference marketplace in which harnesses originate
requests, a router aggregates demand, and heterogeneous providers sell execution
for the same open-weight model. It separates public quotes, latent router scores,
private eligibility, and realized execution. The theoretical components include
inverse-power share elasticity, score-price equivalence, a reduced-form
information-congestion threshold, a hidden-capacity impossibility result, and
objective-specific router design. The empirical section uses 3.18 million public
endpoint observations, an accruing owned-routing intervention, and registered
negative tests. A structural game compares 108 rules over ten declared provider
technologies.

The paper is unusually disciplined about what public prices do not identify.
However, at ACM EC the principal positive theorem is currently too close to
differentiating an assumed concave objective, and the proposed exposure cap is
not yet derived as an equilibrium mechanism. I view the work as promising but
not yet a sufficiently complete mechanism-design contribution.

## Strengths

1. **The market abstraction is economically useful.** The router is correctly
   modeled as a scoring and reliability intermediary rather than a passive DEX
   aggregator. The distinction among harness, router, provider, and user is
   sharper than in most discussions of inference markets.
2. **Claim boundaries are excellent.** Shadow shares are never called realized
   flow; pair deviations are not called collusion; provider regimes are not
   called structural types; and simulator welfare is not called live welfare.
3. **The score-price equivalence is operational.** Expressing a latent score as
   an effective-price wedge gives a clear estimand and a useful decomposition of
   how quality scoring can attenuate or amplify undercutting.
4. **The empirical negatives improve the mechanism argument.** GLM-5.2 has an
   18.62 point public-rule transfer, but its rank slope is linear-compatible;
   non-GLM adaptation is sparse. The paper does not force these facts into the
   desired asymptotic story.
5. **Objective conflict is demonstrated rather than asserted.** The structural
   game produces distinct welfare-, revenue-, quality-, user-, viability-, and
   provider-profit selections and reports both unilateral and pair deviations.
6. **The hidden-capacity result and execution-contingent recommendation are
   conceptually important.** They explain why fundraising, provider identity,
   and displayed price are inadequate substitutes for capacity commitments.

## Main weaknesses

1. **The critical-set theorem is reduced-form and mathematically thin.** Once
   the loss
   \(c(k/n)^2(k/r_n)^\alpha\) is assumed, the scaling result follows from one
   first-order condition. Effective rank does not itself imply this loss, its
   exponent, or its welfare interpretation. The numerical recovery in SM3 only
   validates the same algebra.
2. **There is no strategic implementation theorem.** The router proposes a
   covariance-aware cap, but providers choose identities, price processes,
   capacity, and entry. The paper does not characterize the free-entry
   equilibrium, show whether private adaptation exceeds the planner's \(k^*\),
   or derive a fee that decentralizes the target.
3. **The central empirical bridge remains partial.** GLM rank uses only two
   nested active-set points. The non-GLM comparison is cross-market and mostly
   zero. The direct price-sort estimate is large but has not crossed its frozen
   duration or sample-size gate. The data identify a mechanism surface, not the
   congestion loss.
4. **The structural objective frontier is illustrative rather than calibrated.**
   Ten technologies are declared scenarios, prices are bounded to a grid, and
   104 of 108 rules converge. The levels 208.44 and 83.99 have no external unit;
   they should not carry the argumentative burden of a welfare theorem.
5. **The relationship among score dynamics, signal rank, and capacity is not
   closed.** A provider can share a price signal with a rival while having
   independent capacity or quality shocks. It is unclear which covariance the
   cap should use and whether price innovations are sufficient statistics.

## Questions for the authors

1. Can the congestion loss be derived from a primitive model of estimation
   error, capacity externality, or correlated best-response noise rather than
   assumed?
2. Under anonymous free entry, what is the equilibrium number of adaptive
   providers, and how does it compare with the planner's \(k^*\)?
3. Can an exposure fee or allocation tax decentralize \(k^*\) while preserving
   entry by independent-information providers?
4. How does a provider prove that its signal is independent without revealing
   proprietary information or creating an identity-splitting attack?
5. Which live randomized outcome would identify the coefficient \(c\), rather
   than only the price rule's elasticity?

## Changes required for acceptance

- Provide a microfoundation in which correlated learner errors or capacity
  responses generate the congestion loss, with explicit assumptions connecting
  covariance to welfare.
- Add a provider entry game. Characterize the laissez-faire adaptive count,
  prove when it over- or under-shoots \(k^*\), and derive an implementable
  Pigouvian exposure price or allocation rule.
- State an incentive or welfare guarantee for the proposed mechanism under
  identity splitting and noisy covariance estimation.
- Relegate absolute SM4 welfare levels to a design screen unless calibrated;
  lead with invariant rankings and stress failures.
- Preserve the current empirical claim boundary. A larger paid panel would help,
  but it should not be used to compensate for the missing strategic theorem.

## Scores

- Technical quality: 6/10
- Novelty: 6/10
- Empirical discipline: 8/10
- Mechanism completeness: 5/10
- Reproducibility: 9/10
- Overall: **5/10, Weak Reject**

## Decision

**Weak Reject.** The paper has an excellent market definition, unusually honest
evidence discipline, and a promising information-externality direction. For ACM
EC, the main congestion result still needs a primitive strategic derivation and
an implementation theorem. The empirical negatives should remain; they are a
strength rather than the reason for rejection.
