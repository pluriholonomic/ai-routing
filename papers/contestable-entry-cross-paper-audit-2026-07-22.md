# Cross-paper audit: costly entry, adaptive pricing, and routed exposure

Date: 2026-07-22  
Branch: `codex/information-congestion-papers`

## Acceptance-loop result

| Venue | Manuscript | Round-4 recommendation | Role of costly entry |
|---|---|---:|---|
| ACM EC | `papers/ec/router-is-the-mechanism.pdf` | 6/10, Weak Accept | Main mechanism-design object: free entry, welfare entry, bilateral contribution, implementing levy/credit, and Sybil boundary |
| ICML | `papers/icml/phase-transitions-routing-games.pdf` | 7/10, Accept | Upstream conditioning object: the responsive-set and memory theorems apply to capacity-certified entrants, not potential firms or labels |
| NeurIPS | `papers/neurips/price-of-softmax.pdf` | 7/10, Accept | Separate outer-stage environment task: participation profiles are chosen before repeated pricing and settled by the same kernel |

The stopping rule requiring at least two accepts is met: all three latest reviews
recommend acceptance, with the EC review explicitly weak rather than strong.

## Shared economic objects

The papers now use a common decomposition:

- `n_FE`: capacity-certified free-entry providers;
- `k_AE`: entrants that pay to adapt public prices;
- `k_L`: provider-specific price effects learnable at a declared precision;
- `k_W`: welfare-optimal exposure to correlated adaptive flow.

The decomposition prevents three invalid substitutions: endpoint labels for
economic providers, adaptive-pricer count for provider entry, and simulated
inverse-price share for realized routed share.

The shared benchmark has public operating profit

`pi_R(n) = D_R c / [eta(n-1)-n]`

at the symmetric interior inverse-power equilibrium. Bilateral contribution can
finance public listing while leaving the public-price first-order condition
unchanged if contracts are separable and capacity is slack. Binding capacity
instead enters the pricing condition through a shadow marginal cost.

The planner values incremental delivery probability and pays real fixed cost.
Free entry and planner entry therefore have no universal ordering. A net levy
or credit evaluated at the planner count decentralizes that count in the
monotone symmetric benchmark. It must be attached to independently deliverable
capacity, not endpoint identities.

## Shared learning and elasticity objects

For a group receiving share `S_G` under inverse-power exponent `eta`, a common
proportional cut has path elasticity

`Z_G = eta (1 - S_G)`.

Group revenue rises locally only when `Z_G > 1`; group profit requires the
stronger margin-adjusted inequality. This is a mechanism identity, not evidence
that the proprietary router uses an inverse-power rule.

The local log-share change includes a weighted rival-price term. Omitting it
creates an exact covariance component in an own-price regression. Provider-
specific learning time scales inversely with residual price variation
`Var(X_i | X_-i)`, so common experiments can sharply slow identification without
communication or collusion.

## Empirical claim boundary

- The public panel identifies displayed quotes, price paths, menu composition,
  enforcement aggregates, and deterministic shadow-rule reallocations.
- Owned requests identify selected providers and outcomes for the sampled
  account, workload, and intervention.
- Neither source identifies market-wide flow, marginal cost, bilateral contract
  value, installed capacity, user value, or a free-entry equilibrium.
- The latest cross-model owned-choice panel has 429 observations and 423 covered
  choices. Three short-chat cells pass the diagnostic price-only support gate;
  exponent heterogeneity is not rejected (`p = 0.164`), and only GLM has
  provisional within-provider price movement.
- GLM's public shadow-transfer surface remains large, but effective-rank evidence
  is linear-compatible. The non-GLM active-pricer census is sparse rather than a
  supported linear-density regime.
- No paper claims collusion, dumping, literal front-running, a fitted entry cost,
  or a point-identified welfare loss.

## Mechanism recommendation boundary

The implementable stack has separate instruments:

1. capacity-contingent entry credit or levy for incremental delivered capacity;
2. covariance-aware charge or cap for correlated adaptive exposure;
3. out-of-sample quality and reliability scoring with explicit SLA settlement;
4. bounded exploration aggregated across shared failure domains;
5. router-fee separation and an explicit objective frontier.

The live next step is a provider-facing capacity-entry trial plus continued
owned routing randomization. Until fixed cost, bilateral contribution, capacity
correlation, and delivered value are bounded, policy results remain scenario
comparisons.

## Verification record

- EC: 13-page PDF, every page rendered and visually inspected; 21 focused tests.
- ICML: 9-page PDF, every page rendered and visually inspected; 15 focused tests.
- NeurIPS: 12-page PDF, every page rendered and visually inspected; 33 focused tests.
- Repository-wide verification: Ruff passes on all new theory/analysis modules;
  `pytest -q` reports 947 passed, 1 skipped. The remaining 12,325 messages are
  pre-existing NumPy/Pandas deprecation and future warnings, not test failures.
- Shared source and analysis artifacts are committed separately from each venue
  revision so the diff history remains auditable.
