# Adversarial NeurIPS review: property-tested strategic routing environment

## Summary

The submission presents a deterministic multi-agent environment for inference-
provider competition. Providers choose price, admitted capacity, and
availability; routers order attempts; request-level settlement tracks fallback,
latency, resource cost, transfers, provider profit, user utility, and welfare.
The paper proposes a five-level property ladder from software invariants to live
transport. Evaluation combines an immutable 3.18 million-row public panel, an
owned price-sort intervention, exact signal-order experiments, adversarial
router hardening, an information-congestion benchmark, and a heterogeneous-
provider objective frontier.

## Strengths

1. **The environment has a real information boundary.** Providers receive
   public actions and their own settlement, not rival technology or planner-only
   state. This avoids a common but serious multi-agent simulation error.
2. **Settlement and randomness are auditable.** Transfer reconciliation,
   capacity conservation, fallback semantics, exact reset replay, and stable
   event-specific substreams are tested.
3. **The property ladder is a useful methodological contribution.** It prevents
   simulator causality from silently becoming market causality and treats failed
   transport gates as publishable results.
4. **The benchmark suite is economically broad.** It includes quote fading,
   identity splitting, quality shading, capacity withdrawal, unilateral and
   pair deviations, sequential best responses, UCB, Q-learning, epsilon-greedy,
   static policies, and heterogeneous provider technologies.
5. **The paper reports several informative failures.** The focal HMP-style UCB
   effect disappears across learner mixtures; static hardening worsens normalized
   post-UCB exploitability; common signal order moves correlation but not active
   share; the desired public asymptotic split is rejected.
6. **The multiobjective frontier is valuable.** Welfare, revenue, quality, user,
   viability, and provider-profit rules select different equilibria. Pairwise
   susceptibility remains even when unilateral grid regret is zero.
7. **The public-data use is disciplined.** GLM shadow share is treated as a rule
   surface, the price-sort effect is labeled accruing, and latent scoring is not
   imputed from prices.
8. **The environment card is unusually complete.** Actions, observations,
   rewards, transitions, seeds, known failures, and minimum reporting are
   specified.

## Weaknesses

1. **The benchmark remains custom.** There is no independent implementation of
   settlement and no demonstrated PettingZoo/OpenSpiel interoperability test.
   Code and tests could share a correlated error.
2. **Learner coverage is finite.** The strongest adaptive results use UCB,
   epsilon-greedy, tabular Q, and static policies. Continuous-action policy
   gradients, recurrent agents, model-based planners, and population-based
   training are absent.
3. **The E1 focal factorial has limited independent seed support.** Exact pairing
   isolates the declared contrast, but two seeds per cell are weak evidence
   about optimization instability.
4. **The live score is not calibrated.** The owned campaign directly shows a
   price-sort effect, but the latent-score fit remains below its support gate.
5. **SM3 and SM4 are declared tasks rather than fitted replicas.** The congestion
   loss, provider technologies, demand, and value parameters are scenarios. The
   paper is careful, but some readers may still overread the objective levels.
6. **The suite is large enough to diffuse the main message.** E0--E3 include
   price-score decomposition, signal coupling, hardening, congestion, and
   multiobjective equilibrium. The property ladder should remain the organizing
   contribution.

## Questions for the authors

1. What is the minimal adapter needed to reproduce a frozen scenario in
   PettingZoo or OpenSpiel, and can the outputs be reconciled independently?
2. How would score uncertainty be represented once the owned panel passes its
   gate: posterior samples, an ambiguity set, or plug-in coefficients?
3. Can provider entry and capacity investment occur during training, rather than
   only through an outer immutable technology specification?
4. Which held-out deviation families are never used while selecting a router?
5. How sensitive are objective rankings to continuous price deviations beyond
   the bounded grid?

## Recommended revisions

- Add an independent reference settlement implementation for one frozen
  scenario and require tolerance-level reconciliation.
- Add recurrent and continuous-action adversaries as held-out deviation
  families.
- Increase independent training seeds for E1 and distinguish pairing precision
  from optimization uncertainty.
- When the latent-score gate passes, transport a distribution or ambiguity set,
  not a single fitted score.
- Keep the property ladder and refusal logic as the headline; place absolute
  scenario welfare levels behind the environment-validation story.

## Scores

- Technical quality: 8/10
- Novelty: 8/10
- Empirical grounding: 8/10
- Reproducibility: 9/10
- Overall: **7/10, Accept**

## Decision

**Accept.** The audited information boundary, exact market settlement, strategic
deviation suite, and executable transport refusal standard constitute a credible
NeurIPS systems-and-learning contribution. The paper earns acceptance because it
reports conditional failures as carefully as successes. Broader learner coverage
and independent cross-implementation would move it toward strong accept.
