# SM1b global-search correction

**Written:** 2026-07-18 after replacing the single bounded optimizer
**Scope:** numerical validation only; frozen analytical grid unchanged

The first SM1b implementation used one bounded scalar optimization for each
best response. Because elastic-demand profit can have more than one local
maximum, that routine converged to a secondary high-price peak in two
high-elasticity duopoly cells and incorrectly labeled it a profitable
deviation.

A dense 2,049-point log-price search followed by local refinement around the
twelve highest grid points shows that the secondary peaks have lower profit.
All 304 frozen cells pass the corrected global best-response audit with price
error below 1e-4.

The correction supports the symmetric candidate on the frozen grid. It is
still numerical evidence rather than a proof of the global best-response
inequality for every admissible parameter. The manuscript must not upgrade the
result to a general theorem until that inequality is established analytically.
