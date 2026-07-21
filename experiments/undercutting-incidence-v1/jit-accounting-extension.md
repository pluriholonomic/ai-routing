# Dated exploratory extension: JIT-like curve capture

**Specified:** 2026-07-21, after inspecting the initial WF-19 incidence result.

This extension is descriptive and cannot be represented as part of the original prospective
WF-19 test. It decomposes an active undercutter's post-cut inverse-square shadow share into:

1. the share it would have retained had its immediately preceding quote remained in force,
   holding the observed candidate set, rival quotes, request shape, and public-health screen
   fixed; and
2. the incremental share mechanically produced by its latest price cut.

The second quantity is called **dynamic capture**. The sum of nonmover share losses must equal
dynamic capture up to numerical error. This is analogous to just-in-time liquidity only in the
narrow sense that an active participant changes a control immediately while passive participants
leave standing terms on a known allocation curve.

The quote-revenue identity is

\[
p_1s_1-p_0s_0
=p_0(s_1-s_0)-(p_0-p_1)s_1.
\]

The first right-hand term values newly captured share at the old quote; the second is the price
concession paid on all post-cut shadow share. This is neither realized revenue nor profit because
market demand, realized selections, rebates, and marginal cost are not observed.

Primary summaries are the event-level dynamic share increment, its fraction of post-cut shadow
share, the relative lift over the frozen-quote counterfactual, and the volume-gain/concession-cost
ratio. Events remain equally weighted, and the largest-capture event is removed in a mandatory
sensitivity summary.

The shadow-curve numerical check reports both the exact finite inverse-square counterfactual and
the local approximation

\[
\eta_i=\frac{\Delta\log s_i}{\Delta\log p_i}
\quad\text{and}\quad
\frac{\partial\log s_i}{\partial\log p_i}=-2(1-s_i).
\]

We report their deviation separately. The exact finite rule should match scenario-level shadow
shares to numerical precision; deviation from the local derivative is expected curvature, not
evidence of a hidden routing mechanism. This check is not an empirical validation of OpenRouter's
realized router. Realized paid selections and the separate live-exponent analysis are required for
that test.
