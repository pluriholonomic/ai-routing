# ACM EC review: “Contestable Demand and Costly Entry in AI Inference Routing”

## Summary

The paper studies provider procurement for open-weight model inference. Its main conceptual move is to separate four objects that are often collapsed: costly provider entry, the subset of entrants that adapt public prices, the subset whose price effects can be statistically learned, and the planner's desired exposure to correlated adaptive flow. The theory combines an inverse-power allocation benchmark, group cut elasticities, a costly-entry/reliability model with bilateral contracts, an omitted-rival-price decomposition and learning bound, and multidimensional router scoring. The empirical section uses public menus, enforcement aggregates, shadow allocations, and owned paid requests as an identification ladder. Structural scenarios compare welfare, revenue, quality, and viability objectives.

## Strengths

1. **The economic timing is now coherent.** Entry, bilateral contracting, repricing, routing, fallback, and settlement are distinct stages. This is materially better than treating every listed endpoint as a costless bidder.
2. **The paper has a useful two-instrument conclusion.** Capacity-contingent entry credits or levies target real capacity creation; covariance-aware exposure charges target overlapping adaptive flow. The Sybil discussion correctly explains why per-label instruments are not sufficient.
3. **The group elasticity is the right object for the empirical motivation.** The identity \(Z_G=a(1-S_G)\) directly connects a set of active undercutters to the loss imposed on passive quotes, while distinguishing revenue from profit.
4. **The HMP bridge is substantially sharper.** Equation (15) exposes the rival-price term rather than appealing verbally to correlated learning. The residual-variation bound gives a falsifiable reason why common experiments increase the time needed to learn provider-specific returns.
5. **The claim boundaries are unusually disciplined.** Shadow share is not called realized share; owned choices are not called market-wide flow; public pricing regimes are not called provider types; the simulator is not called a welfare estimate.
6. **The empirical setting is novel and important.** The public panel is large, the paid intervention shows that router rule choice materially changes selection, and the cross-model exponent panel honestly reports both support and non-identification.

## Weaknesses

1. **Several theoretical ingredients are deliberately elementary.** The entry theorem is a transparent zero-profit benchmark, the group elasticity is an identity, and the learning bound is a standard partialling-out argument. The paper's novelty is their integration in this market and the mechanism separation, not any one theorem. The final version should state this plainly and avoid presenting Theorem 1 as a general entry result.
2. **The information-congestion cost remains reduced form.** The paper now labels this correctly, but a stronger EC version would derive the loss from a primitive queueing, correlated-capacity, or scoring-error game and show when the reduced form is a valid approximation.
3. **Entry is not empirically calibrated.** Fixed integration cost, bilateral contribution, independent failure probability, and capacity correlation are all missing. The provider-facing capacity trial is therefore essential before making a quantitative entry-policy recommendation.
4. **The covariance fee is a design proposal rather than an equilibrium implementation theorem.** The paper should eventually prove incentive and identity-splitting properties under endogenous price processes, and should specify who bears a false-positive covariance penalty.
5. **The owned-choice exponent evidence remains thin.** Only three cells pass the diagnostic gate, equality is not rejected, and only GLM has provisional within-provider price movement. This is useful feasibility evidence, not a stable cross-market elasticity estimate.
6. **The structural welfare frontier is scenario-dependent.** It usefully demonstrates objective conflict, but the numerical magnitudes should not be highlighted beyond their role as design screens.

## Correctness and presentation

The algebraic claims are internally consistent. The symmetric public-profit formula follows from the inverse-power pricing equilibrium; the entry levy implements the target under the stated monotonicity and tie convention; the bilateral separability result is a direct first-order-condition observation; and the learning bound has the appropriate residual-design variance. The manuscript compiles cleanly, figures are legible, and the evidence ledger makes the scope of every major empirical claim auditable.

One presentation issue remains: the public-panel Figure 1 is visually less informative than the new costly-entry figure. It should be simplified in a camera-ready version, ideally by replacing the two-point rank ladders with uncertainty-aware small multiples and moving unsupported non-GLM contrasts to an appendix.

## Questions for the author

1. Can capacity certificates be made portable across routers, or would router-specific certification itself become an entry barrier?
2. Under what primitive capacity-correlation model does the reduced-form congestion exponent arise?
3. Can the paid design randomize exploration credit or capacity bonding to identify the extensive-margin entry response without inducing unsafe traffic?
4. How would the covariance charge treat a common public cost shock that rationally moves every provider's price?

## Overall assessment

**Score: 6/10 — Weak Accept.**

The paper now clears the central mechanism-design bar that the previous version missed: it contains an explicit costly-entry game, separates private/bilateral returns from contestable public demand, derives the free-entry/planner wedge, proposes an implementing entry instrument, and treats identity splitting as a first-order constraint. The theory is intentionally stylized and the entry margin is not yet calibrated, which keeps this from a strong accept. Nevertheless, the combination of a new market, unusually careful identification, a coherent extensive-margin model, and concrete auditable mechanism proposals is sufficient for a weak accept at EC.

## What would make this a strong accept

- Derive the congestion/exposure loss from a primitive correlated-capacity or queueing model.
- Estimate at least bounds on \(F\), bilateral contribution, and incremental reliability from a partner or randomized capacity-entry trial.
- Prove incentive compatibility or regret guarantees for the covariance charge under endogenous learning and identity splitting.
- Expand the paid panel until model-specific price effects are identified from within-provider variation in several markets.
- Replace the weakest public-panel visualization and reduce scenario-number emphasis.
