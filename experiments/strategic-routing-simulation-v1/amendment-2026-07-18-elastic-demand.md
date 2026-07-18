# SM1b elastic-demand welfare extension

**Written:** 2026-07-18 before running SM1b
**Parent result:** SM1 fixed-demand theorem
**Reason:** add a real welfare margin without changing SM1

SM1 correctly finds that price is an internal transfer and welfare is constant
under identical cost, quality, and inelastic unit demand. SM1b adds an
isoelastic aggregate-demand margin while preserving the same inverse-power
provider routing game.

Aggregate demand is

    Q(p_bar) = A p_bar^(-epsilon),

where p_bar is the route-share-weighted expected provider price and epsilon is
strictly greater than one for the welfare calculations. Provider i profit is

    (p_i-c) s_i Q(p_bar).

The extension freezes:

- n in {2, ..., 20};
- eta in {1.5, 2, 3, 4};
- epsilon in {1.25, 2, 4, 8};
- c = A = 1;
- price cap P = 100.

The primary theorem candidate is:

    p* = c [eta(n-1)+epsilon] / [eta(n-1)+epsilon-n]

when the denominator is positive, with the cap binding otherwise. As n tends
to infinity, p*/c still tends to eta/(eta-1); finite aggregate-demand
elasticity does not eliminate smooth-router market power because one small
provider internalizes only its 1/n effect on the expected market price.

Primary outputs are price, quantity, welfare, competitive welfare, welfare
ratio, and numerical best-response error. The result remains a symmetric
benchmark, not a calibrated market estimate.
