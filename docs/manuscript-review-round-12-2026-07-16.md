# Independent-style review, round 12

Manuscript: *Administered Menus and Hidden Clearing: The Microstructure of the
Market for Machine Intelligence*

Target: ACM EC / WINE / a top operations or market-design venue

Recommendation: **6/10, borderline weak reject for the empirical paper.** The
paper now asks a coherent market-microstructure question, makes unusually clean
identification distinctions, and directly positions itself against the closest
provider-elasticity evidence. The remaining obstacle is prospective support,
not exposition.

## What improved

1. The paper no longer treats a cross-sectional elasticity near minus one as a
   provider revenue first-order condition. It preregisters the within-entity and
   price-event replication and keeps the current result out of the abstract.
2. The revenue-gap calculation is correctly parameterized to reproduce the
   estimated share elasticity locally and reports an elasticity/bootstrapping
   sensitivity envelope rather than a single spurious welfare number.
3. Demirer, Fradkin, Tadelis, and Peng (2025) are now treated as the closest
   empirical benchmark. The paper's distinct contribution is microstructure,
   quote firmness, and identification—not the first provider price elasticity.
4. The claim ledger now distinguishes gross-revenue stationarity, profit
   maximization, router revenue, and global welfare.
5. The appendix gives an executable promotion rule: 30 days, 200 moves, 25%
   varying entities, 2% within-price variance, and two equivalence tests.

## Current revenue evidence

The ten-day cross-section gives an effective-price/share elasticity of -1.027
(SE 0.093), equivalent to the zero-cost gross-revenue target of -1. Conditional
on interpreting this association causally, the observed-proxy-weighted bounded
revenue gap is 0.11%--0.14%; the combined H4-endpoint and day-bootstrap envelope
is 0.10%--2.17%.

The causal interpretation is not validated. The effective-price within estimate
is -0.325 (SE 0.359). The open-weight listed-prompt within estimate is +0.325
(SE 0.356), differs from the published -1.02 benchmark under an approximate
independent-sample comparison, and is supported by only 30 varying entities.
Only 0.18% of listed-price variation is within entity, and the price-event design
has 50 moves with a significant positive pretrend. These are falsification and
replication-discrepancy results, not an identified demand curve.

## Remaining reasons for rejection

1. **The revenue result is not promoted.** Ten days and 50 listed-price moves do
   not meet the paper's own 30-day/200-event threshold.
2. **The randomized firmness result remains secondary.** The first-position
   prefix is still far below 500 assignments per arm.
3. **The headline market description is short-panel.** Millions of snapshots do
   not substitute for calendar support when repricing is infrequent.
4. **Profit and welfare remain unidentified.** Provider billing, marginal cost,
   capacity opportunity cost, end-user value, and the router's applicable take
   rate are absent.
5. **The benchmark comparison is not yet an exact replication.** Calendar,
   controls, and data construction differ; the current p-value cannot by itself
   establish a structural break from the 2025 estimate.

## Acceptance threshold

Release the deterministic 30-day H91 replication regardless of sign; clear the
registered price-variation and event-support gates or report their failure; open
the first qualifying randomized firmness prefix; and rerun the frozen manuscript
vintage at one immutable dataset revision. A negative dynamic elasticity result
would be publishable if it survives those prospective gates and an exact
specification crosswalk to the 2025 benchmark.

## Decision

**Borderline weak reject, with a credible path to weak accept.** The new analysis
is valuable because it prevents a compelling but invalid revenue-maximization
claim. It does not yet replace that claim with a prospectively supported causal
result. The paper should retain its current restrained abstract while the remote
capture accumulates the remaining calendar and event support.
