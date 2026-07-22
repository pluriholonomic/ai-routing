# Informational congestion and a sublinear strategic-provider threshold

Status: proposed theorem and prospective identification design. Nothing in
this note is an empirical result, and it does not amend the frozen
`glm52-market-share-hmp-v1` protocol.

Date: 2026-07-22.

## 1. Why the static routing threshold is not enough

Let `n` providers have equal baseline price-only share and let `k` providers
make the same proportional price cut `r` under inverse-price exponent `eta`.
Write

\[
 A=r^{-\eta}>1,\qquad S=k/n.
\]

The active group receives post-cut share

\[
 S'=\frac{AS}{1+(A-1)S},
\]

so passive-to-active share transfer is

\[
 \Phi(S)=S'-S
 =\frac{(A-1)S(1-S)}{1+(A-1)S}.
\]

This function is strictly concave and has its unique interior maximum at

\[
 S^{\mathrm{mech}}=\frac{1}{1+\sqrt A}.
\]

Consequently, perfect-information price-only routing predicts
`k_mech = Theta(n)`. A claim that the economically relevant number of reactive
providers is `o(n)` cannot follow from the inverse-price curve alone. It needs
an additional force.

## 2. Signals, effective rank, and statistical congestion

Let `Sigma_k` be the covariance matrix of the innovations used by the `k`
reactive pricing rules after removing the frozen public controls. Define signal
effective rank and informational crowding by

\[
 r_k=\frac{\operatorname{tr}(\Sigma_k)^2}
 {\operatorname{tr}(\Sigma_k^2)},
 \qquad
 \chi_k=\frac{k}{r_k}.
\]

Independent signals have `r_k` proportional to `k` and bounded `chi_k`.
Providers repeatedly fitting against a small set of common demand, benchmark,
or routing signals can instead have `r_k << k`. Contemporaneous co-movement is
not sufficient: the object is residual, held-out signal rank and its associated
out-of-sample error.

Assume that the out-of-sample loss from implementing a noisy group response is,
locally,

\[
 R_n(k)=c\left(\frac{k}{n}\right)^2
             \left(\frac{k}{r_n}\right)^\alpha
       +o\!\left(
             \left(\frac{k}{n}\right)^2
             \left(\frac{k}{r_n}\right)^\alpha
           \right),
 \qquad c>0,\quad \alpha>0.
\]

The first factor is aggregate routing exposure. The second is a prospectively
testable overfit law: statistical error rises when `k` learned policies occupy
only `r_n` effective signal dimensions. This law is an assumption to derive or
estimate, not a consequence of correlation by itself.

## 3. Proposed restricted-active-entry result

**Proposition (informational minority threshold).** Suppose `r_n=o(n)`, the
local overfit law above holds uniformly in the relevant range, and
`k/n -> 0`. For net group value

\[
 V_n(k)=\Phi(k/n)-R_n(k),
\]

any interior local maximizer in that range satisfies

\[
 k_n^*=\Theta\!\left(
        (n r_n^\alpha)^{1/(1+\alpha)}
       \right),
 \qquad
 \frac{k_n^*}{n}
 =\Theta\!\left(
   \left(\frac{r_n}{n}\right)^{\alpha/(1+\alpha)}
  \right)=o(1).
\]

For linear variance inflation (`alpha=1`),

\[
 k_n^*=\Theta(\sqrt{n r_n}).
\]

Thus the strategic population can diverge while remaining a vanishing fraction
of the provider population. The result is analogous to restricted entry under
explicit congestion in intent markets, but the primitive here is finite signal
diversity rather than costly search effort.

**Proof sketch.** Around zero,

\[
 \Phi(k/n)=(A-1)\frac{k}{n}
 -A(A-1)\frac{k^2}{n^2}+O((k/n)^3).
\]

When `k/r_n` diverges, the leading informational loss is proportional to
`k^(2+alpha)/(n^2 r_n^alpha)`. Balancing its derivative against the first-order
share benefit gives

\[
 k^{1+\alpha}=\Theta(n r_n^\alpha).
\]

The stated density follows by division by `n`. A complete theorem must state
the response-error process that implies the overfit law and control the Taylor
remainder uniformly.

## 4. Finite-time HMP-style boundary

The same crowding object gives a separate learnability constraint. If the base
single-policy reward signal-to-noise ratio is `SNR_0`, posit

\[
 \operatorname{SNR}_{\mathrm{eff}}(k)
 =\operatorname{SNR}_0\left(\frac{r_n}{k}\right)^\alpha.
\]

Learning a reward gap within effective horizon `T_eff` and familywise error
`delta` requires approximately

\[
 T_{\mathrm{eff}}\operatorname{SNR}_{\mathrm{eff}}(k)
 \gtrsim \log(k/\delta).
\]

The resulting learnability ceiling is

\[
 k_{\mathrm{learn}}
 \lesssim r_n
 \left(
  \frac{T_{\mathrm{eff}}\operatorname{SNR}_0}
       {\log(n/\delta)}
 \right)^{1/\alpha}.
\]

The observed strategic threshold should therefore be treated as

\[
 k^*=\min\{k_{\mathrm{share}},k_{\mathrm{learn}}\}.
\]

This predicts a genuine minority region: a singleton has no cross-provider
signal-coupling channel; a small group can amplify a common market-share path;
and a sufficiently dense group becomes statistically redundant or too slow to
learn within the stationary market window.

## 5. Discriminating predictions

The proposed result is refutable.

1. If residual signals are conditionally independent, `r_k` should grow with
   `k`, the crowding term should remain bounded, and the sublinear threshold
   should disappear.
2. At fixed `n`, cut depth, and active share mass, held-out response error
   should increase with `k/r_k`; contemporaneous fit alone is not evidence.
3. Aggregate excess share should initially rise with `k`, but its incremental
   gain should flatten or reverse near the threshold predicted from the frozen
   rank and error-law estimates.
4. Markets with larger held-out effective signal rank should support a larger
   `k*`; markets with the same provider count but more overlapping signals
   should support a smaller `k*`.
5. Marginal-preserving provider-time shuffles should reduce measured crowding
   and move or remove the estimated threshold.
6. Longer usable reward histories or higher owned-probe SNR should raise the
   learnability ceiling. Stale memory can reverse that comparative static and
   must be modeled separately.

## 6. Prospective empirical design

The current v1 campaign does not identify this theorem because it was not
designed around fixed total menu size and signal effective rank. A separate v2
study should:

1. freeze total eligible menu size `n` and vary reactive count `k`, rather than
   changing both at once;
2. residualize provider price innovations on author price, benchmark price,
   time, demand proxies, enforcement state, and available QoS before estimating
   `Sigma_k`;
3. estimate `r_k` only on training windows and score response prediction,
   pricing regret, and routing outcomes on untouched future windows;
4. cross `k`, `n`, cut depth, router exponent, memory, SNR, and signal rank in a
   fixed-horizon simulation;
5. estimate `alpha` from held-out error against `log(k/r_k)` and freeze it
   before testing the implied `k*`;
6. use public shadow shares for the mechanical leg and owned paid probes for
   realized choice, cost, latency, fallback, and non-price-score legs;
7. report equal-mass comparisons so the number of cutters is not confounded
   with total cut exposure; and
8. require the threshold to transport beyond GLM-5.2 before making an
   asymptotic restricted-entry claim.

GLM-5.2 remains the primary calibration market because it has several active
undercutters. Cross-model variation is nevertheless essential for identifying
how the threshold scales with `n` and `r_n`.

## 7. Claim boundary

The exact transfer identity and its linear-density mechanical maximizer are
theorems. The sublinear result is conditional on the overfit law. The current
public quote panel can estimate signal overlap and shadow share but not market
share. Owned paid probes can identify routing choices only for the project's
requests. None of these objects, alone, establishes provider intent, tacit
collusion, market-wide realized share, or welfare.
