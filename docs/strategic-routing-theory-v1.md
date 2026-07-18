# Strategic routing theory v1: smooth allocation and residual market power

**Status:** analytical result with numerical best-response validation
**Experiment:** SM1
**Protocol:** experiments/strategic-routing-simulation-v1/preregistration.md

## Result

Smooth price-weighted routing does not generally reproduce Bertrand
competition. If route share is proportional to price to the minus eta, entry
leaves residual market power even when providers are identical and capacity is
unlimited.

For inverse-square routing, two providers are a knife edge: the symmetric
equilibrium binds any finite price cap. With three providers the unconstrained
symmetric price is four times marginal cost; with four it is three times cost.
As provider count tends to infinity, price tends to twice cost rather than to
cost.

This is a unilateral pricing result. It requires neither collusion nor
front-running.

## Model

There are n >= 2 providers with common marginal cost c > 0 and identical
quality. One inelastic request arrives. Provider i posts a price p_i in [c, P],
where P is a common exogenous price cap. The router assigns first-route share

    s_i(p) = p_i^(-eta) / sum_j p_j^(-eta)

for eta > 0. Provider profit is

    pi_i(p) = (p_i - c) s_i(p).

The price is a per-request transfer. There are no capacity, latency,
reliability, or quality differences in this benchmark.

## Lemma 1: the best response

Fix positive rival prices and write

    A = sum_{j != i} p_j^(-eta).

Provider i solves

    max_p (p - c) / (1 + A p^eta).

Its derivative has the sign of

    1 + A p^(eta-1) [eta c - (eta - 1)p].

When eta <= 1 this expression is positive, so profit is increasing and the
bounded best response is P. When eta > 1, the derivative is positive at c and
crosses zero at most once: after p exceeds eta c/(eta-1), the absolute value of
the negative term is strictly increasing. The unconstrained best response is
therefore unique, and the bounded best response is its projection onto [c, P].

## Proposition 1: symmetric equilibrium

The unique symmetric price is

    p_sym =
      P,                                            if eta <= n/(n-1);
      min{P, eta(n-1)c / [eta(n-1)-n]},             otherwise.

### Proof

At a symmetric price p, share is 1/n and

    ds_i/dp_i = -eta s_i(1-s_i)/p.

The own-price first-order condition is

    1 - eta (1 - 1/n)(p-c)/p = 0.

Solving gives

    p* = eta(n-1)c / [eta(n-1)-n].

A positive finite solution exists exactly when eta > n/(n-1). Lemma 1 makes
this stationary point the unique best response to rivals charging p*. If the
condition fails, the derivative at every symmetric finite price is positive,
so the common cap is the symmetric equilibrium. If the condition holds but
p* >= P, the unique unconstrained best response to rivals at P lies weakly
above P, so the bounded best response is P. Otherwise p* is feasible and is
the unique symmetric equilibrium. QED.

## Corollary 1: inverse-square routing

For eta = 2:

    p_sym = P,                         n = 2;
    p_sym = min{P, 2(n-1)c/(n-2)},     n >= 3.

The duopoly result is not a numerical instability. At any common finite price,
each provider has a positive local incentive to raise its price.

## Corollary 2: free entry has a noncompetitive limit

When the cap does not bind and eta > 1,

    lim_{n -> infinity} p_sym/c = eta/(eta-1),

and the Lerner index converges to 1/eta. For inverse-square routing the limiting
price is 2c and the limiting Lerner index is one half.

The reason is local rather than collusive. Even with many rivals, a provider's
smooth route share has finite elasticity eta(1-s_i), which converges to eta
rather than infinity.

## Proposition 2: the benchmark has no allocative welfare ranking

Let delivered user value be v and treat payments as internal transfers. At a
symmetric profile, aggregate provider profit is p-c and user utility is v-p.
Their sum is

    v-c,

independent of price, eta, and provider count.

Therefore SM1 supports claims about markups, consumer payments, profit, and
router-created market power. It does not support a welfare-maximization claim.
Welfare comparisons require at least one real allocation margin: elastic
demand, heterogeneous marginal cost, quality, capacity, reliability, latency,
or entry cost.

## Local condition 3: elastic demand and a global-deviation caveat

Let aggregate demand depend on the route-share-weighted expected price:

    Q(p_bar) = A p_bar^(-epsilon).

At a symmetric price, a unilateral price change moves expected price by 1/n.
Combining this aggregate-demand effect with the route-share effect gives

    (p-c)/p = n / [eta(n-1)+epsilon].

The symmetric first-order candidate is therefore

    p* = c[eta(n-1)+epsilon] / [eta(n-1)+epsilon-n],

when the denominator is positive. At eta = epsilon = n = 2, the candidate is
p* = 2c.

However, for any finite epsilon,

    lim_{n -> infinity} p*/c = eta/(eta-1).

As each provider becomes small, it internalizes a vanishing 1/n share of the
aggregate-demand effect while retaining finite route-share elasticity eta.
Thus the local stationary formula retains the smooth router's residual market
power under free entry.

For epsilon > 1, isoelastic gross surplus is finite and welfare at symmetric
price p is

    W(p) = [epsilon p/(epsilon-1) - c] A p^(-epsilon).

At eta = epsilon = 2, the frozen numerical global best-response audit supports
the candidate over n = 2 through 20. If global incentive compatibility extends
to the limit, welfare converges to 75% of competitive welfare. This is the
candidate welfare result to prove, not yet an unrestricted theorem.

High-elasticity duopoly profit is not globally quasiconcave: it contains
secondary high-price local maxima. A single bounded optimizer incorrectly
selected those peaks in the first audit. A dense global search plus local
refinement finds that they have lower profit and that all 304 frozen cells pass
the numerical best-response gate. A first-order calculation alone still does
not prove global equilibrium; the relevant global inequality remains a theory
task.

## Proposition 4: entry has a sign-reversal at matched elasticities

For any interior symmetric stationary candidate, write

    m(n) = p*/c
         = [eta n + (epsilon-eta)]
           / [(eta-1)n + (epsilon-eta)].

Holding eta and epsilon fixed and treating provider count continuously,

    dm/dn = (epsilon-eta)
            / [(eta-1)n + (epsilon-eta)]^2.

Therefore entry lowers the stationary markup when epsilon < eta, leaves it
unchanged when epsilon = eta, and raises it when epsilon > eta. At the matched
elasticity, the stationary markup is exactly

    m(n) = eta/(eta-1)

for every n for which the interior expression is defined.

For p >= c, symmetric welfare satisfies

    dW/dp = A epsilon p^(-epsilon) (c/p - 1) <= 0.

Thus the welfare comparative static has the opposite sign: within this
stationary family, entry improves welfare if epsilon < eta, is welfare-neutral
if epsilon = eta, and lowers welfare if epsilon > eta.

This proposition is algebra about stationary candidates, not a general global
equilibrium theorem. Its substantive implication is nevertheless important:
provider count alone is not a sufficient statistic for competitive pressure.
The sign depends on whether end-user demand is more or less elastic than the
router's within-market allocation rule.

## Proposition 5: inverse-square routing is exactly entry-neutral at elasticity two

Let eta = epsilon = 2 and suppose the common price cap is at least 2c. For
every n >= 2, p_i = 2c for all i is a symmetric pure-strategy equilibrium and
each provider's global best response is unique.

### Proof

Fix n-1 rivals at 2c and write the deviating provider's price as q = 2cx,
where x >= 1/2. Its route share and the route-share-weighted expected price are

    s(x) = 1 / [1+(n-1)x^2],

    p_bar(x) = 2c [x+(n-1)x^2] / [1+(n-1)x^2].

After dropping positive constants, deviation profit is proportional to

    f_n(x) =
      (2x-1)[1+(n-1)x^2] /
      {x^2[1+(n-1)x]^2}.

At x=1, f_n(1)=1/n. The inequality f_n(x) <= 1/n is equivalent to

    x^2[1+(n-1)x]^2
      - n(2x-1)[1+(n-1)x^2] >= 0.

The left side factors exactly as

    (x-1)^2 [(n-1)^2 x^2+n],

which is nonnegative and equals zero only at x=1. Thus q=2c is the unique
global best response to rivals charging 2c. QED.

With epsilon=2, welfare is

    W(p) = (2p-c) A p^(-2).

Therefore

    W(2c)/W(c) = 3/4.

The equilibrium price and the 25% deadweight loss are identical for every
provider count. In this benchmark, free entry has literally zero effect on
price because the shrinking aggregate-demand effect exactly offsets the entry
change in smooth route-share elasticity.

## Empirical predictions

The theorem gives four falsifiable patterns for the public panels:

1. two-provider inverse-square markets should be unusually sensitive to price
   caps, anchors, or menu ceilings;
2. the price response to a change in eligible-provider count should switch sign
   according to whether aggregate demand elasticity is below or above the
   router exponent;
3. when aggregate demand elasticity approximately equals the router exponent,
   eligible-provider entry should change shares without materially changing
   the market price level;
4. deterministic lowest-price routing should have different pricing dynamics
   because the smooth-share elasticity argument no longer applies.

The public data do not reveal the live eligible set, marginal cost, or actual
allocation perfectly. Tests must therefore use public-candidate versions as
reduced-form predictions and owned/executable routing for mechanism
validation.

## Reviewer assessment

This is a clean EC-style lemma, not yet a paper-level contribution by itself.
Its strongest role is as the theoretical backbone for:

- a heterogeneous-cost and capacity extension;
- optimal router-exponent design with elastic demand;
- entry with fixed capacity/cache costs;
- executable-router validation;
- empirical tests around changes in eligible-provider count.

A publishable result must add at least one of those margins and show that the
result survives calibrated heterogeneity. The simulation should be used to
explore and validate extensions, not to replace proof where proof is possible.

## Prior-art and novelty boundary

The stationary markup formula is a nested-CES oligopoly formula in router
notation. Atkeson and Burstein's variable-markup nested-CES model and later
oligopolistic CES work already contain the same economic force: the relevant
elasticity is a share-weighted combination of within-nest substitution and
aggregate demand. The matched-elasticity entry-neutrality result is therefore
not, by itself, a publishable theory contribution.

The potentially new object is the interaction of that pricing game with an
executable inference router: request-level fallback, reliability and capacity,
public repricing, stateful demand steering, and heterogeneous provider learning.
The paper must make its contribution there. In particular, it should ask
whether a router can choose an allocation or steering rule that preserves
reliability while eliminating learned supracompetitive pricing, and test that
rule in a calibrated environment plus at least one executable open-source
router.

## Proposition 6: a cut penalty creates a downward-adjustment wedge

Fix rivals' quotes and let `u(p)` be the subject provider's one-period profit
under the ordinary router. Let `u_theta(p)` be profit when its allocation
weight is multiplied by `theta < 1`. Suppose the provider currently charges
`H`, the router penalizes a cut for `L` periods, and the provider discounts by
`gamma`. Staying forever has value

    V_stay(H) = u(H)/(1-gamma).

A permanent cut to `l < H` has value

    V_cut(l) = [(1-gamma^L) u_theta(l)
                + gamma^L u(l)]/(1-gamma).

Hence staying at `H` defeats every permanent cut if and only if

    u(H) >= (1-gamma^L)u_theta(l) + gamma^L u(l)

for all `l < H`. This condition is exact for the restricted permanent-cut
class. Failure at any `l` is sufficient to reject equilibrium at `H`, though
success against this class is not sufficient to prove equilibrium against all
history-dependent deviations.

In the calibrated five-provider screen (`theta=0.17`, `L=7`, `gamma=0.95`),
the learned price reaches the grid cap, but a permanent cut is profitable.
Therefore the observed high-price policy is a path-dependent Q-learning trap,
not equilibrium collusion. This distinction is central: the steering rule can
create a one-way ratchet for bounded learners even when a fully optimizing
provider would pay the temporary penalty and escape it.

## Proposition 7: the delayed-credit region and its exact boundary

Restrict the provider to a high quote `H` and a low quote `l < H`, hold rivals
fixed, and write one-period profits as

    u_H       = u(H),
    u_L       = u(l),
    u_theta_L = u_theta(l).

Assume `u_L > u_H > u_theta_L`: low pricing is best after the penalty expires,
high pricing is best during the penalty, and a high quote resets the `L`-period
cut history. From the all-high history, the optimal discounted policy is either
stay high forever or cut immediately and remain low forever. The cut is optimal
if and only if

    gamma^L > (u_H - u_theta_L) / (u_L - u_theta_L).              (DC)

Equivalently, with

    L* = log[(u_H-u_theta_L)/(u_L-u_theta_L)] / log(gamma),

the rational provider cuts exactly when `L < L*` (with indifference at
equality).

**Proof.** Once the last high quote exits memory, low forever yields `u_L` each
period and strictly dominates inserting a high quote, which yields the lower
current payoff `u_H` and restarts the penalty. Before that state, a high quote
resets all progress. Hence any policy that eventually cuts is weakly dominated
by waiting `k` high periods and then cutting permanently. Its value is

    u_H (1-gamma^k)/(1-gamma) + gamma^k V_cut.

If `V_cut > V_stay`, this expression is decreasing in `k`, so immediate cut is
best; if `V_cut < V_stay`, never cutting is best. Substitution of Proposition
6's `V_cut` and `V_stay` gives (DC). QED.

There is a strict delayed-credit region whenever (DC) holds. A receding-horizon
controller that compares `h <= L` consecutive low quotes with `h` high quotes
sees only `u_theta_L < u_H` and stays high, while the infinite-horizon optimizer
cuts. This is a mechanism-design wedge between the router's rational incentive
effect and its effect on a bounded provider algorithm; it is not an equilibrium
or collusion statement.

For the E-SIM4 profile,

    u_H       = 0.1067535,
    u_theta_L = 0.0351280,
    u_L       = 0.1501829,
    gamma     = 0.95.

The ratio in (DC) is `0.622533`, so `L*=9.240`. The exact optimizer therefore
cuts for integer memories through nine and stays high from ten onward. The
frozen E-SIM6 sweep checks `L=1,3,5,7,9,12` and reproduces this boundary.

## Proposition 8: a feasible commitment option preserves optimal provider value

Take any discounted Markov pricing problem and add a macro action whose reward,
duration, and successor are obtained by executing a finite sequence of existing
primitive actions. If the agent may still choose every primitive action, the
augmented semi-Markov problem has the same optimal value as the primitive
problem at every state.

**Proof.** The augmented action set contains the primitive actions, so its
optimal value is weakly higher. Conversely, unroll every selected macro action
into its defining primitive sequence. This produces a feasible primitive,
history-dependent policy with exactly the same discounted reward path and
state path. Thus the augmented value is weakly lower. QED.

This proposition separates opportunity from learning. E-SIM6's `commit_low`
action executes `L+1` low quotes; it creates no new feasible price trajectory,
and the enumerated primitive and augmented values agree at all states to
`1e-10`. At `L=7`, the option nevertheless changes which policy tabular
Q-learning discovers. At `L=12`, it can induce overcommitment even though the
exact optimizer stays high. The economically relevant result is therefore a
nonmonotone implementation gap, not a universal claim that commitment improves
social welfare.
