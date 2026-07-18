# SM1b global-deviation audit

**Written:** 2026-07-18 immediately after the first SM1b numerical audit
**Status:** superseded by the global-search correction below

The first implementation appeared to show global best-response failures in two
frozen cells:

- n = 2, eta = 1.5, epsilon = 8;
- n = 2, eta = 2, epsilon = 8.

The scalar profit problem is not globally quasiconcave in those cells. A
provider can jump from the low symmetric stationary candidate to a high price,
retain a small smooth-routing share, and leave the route-share-weighted market
price—and therefore aggregate demand—close to the low rival price. The first
optimizer found that secondary local peak.

The analyzer was therefore amended to use a dense global log-price search
followed by local refinement, record deviation profit, and label every
candidate by a global best-response gate.

That audit showed that the secondary high-price peaks have lower profit than
the symmetric candidate. The apparent failures were numerical optimizer
failures, not profitable deviations. This file is retained to make the audit
trail explicit.
