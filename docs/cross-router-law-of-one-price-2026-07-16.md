# Cross-router law of one posted price: initial capture

## Result

The first credential-free Glama, Requesty, and NemoRouter capture produced 784
normalized provider/model quote rows.  The main immediate result is a sharp
posted-price benchmark:

- 29 simultaneous pairs hold an exact Hugging-Face-linked model and a
  punctuation-normalized provider label fixed across two routers;
- 28 of 29 pairs have exactly the same posted input and output token price;
- the exact-match share is 96.6%, with a Wilson 95% interval of
  [82.8%, 99.4%]; and
- the sole material exception is `deepseek/deepseek-v4-pro` sold by the
  provider labelled `deepseek`: Glama posts $1.70 input / $3.50 output per
  million tokens, while Requesty posts $0.435 / $0.87.  For the registered
  1,000-input/500-output workload, the Glama quote is 296.6% above Requesty's
  quote (3.97 times the cost).

This is a one-snapshot result.  It supports a new hypothesis, not yet a
longitudinal conclusion: inference routers usually pass through an upstream
posted price, so the closest analogy may be a distribution channel or DEX
aggregator rather than a dealer that independently makes prices.  Rare channel
wedges may instead identify stale catalogs, differentiated contracts, or
router markups.

## Coverage

| Router | Quote rows | Models | Providers | Multi-provider models | HF-linked exact model matches | HF-linked multi-provider matches |
|---|---:|---:|---:|---:|---:|---:|
| Glama | 107 | 101 | 16 | 5 | 26 | 3 |
| Requesty | 563 | 403 | 31 | 89 | 100 | 51 |
| NemoRouter | 114 | 114 | 5 | 0 | 32 | 0 |

Requesty is therefore the main additional competitive quote surface.  Glama is
smaller but economically valuable because its public model pages expose a
genuine provider menu.  NemoRouter is useful as a managed-router price
pass-through control, not as a within-model provider-choice market in the
current snapshot.

## Longitudinal identification gate

H93 will not promote the posted-price result into a router-policy or stale-quote
claim until all of the following are observed:

1. at least seven elapsed days;
2. repeated observations from all three routers and at least 48 captures per
   router;
3. at least ten HF-linked competitive router-model cells;
4. at least 30 same-provider/model price events;
5. at least 15 price events seen on two routers within 90 minutes; and
6. at least 15 simulated cheapest-provider switches.

The common-shock design then estimates which router changes first, how quickly
the other surface follows, and whether the cheapest-provider identity changes.
Owned request probes are required to test whether those public changes affect
realized selection.

## Claim boundary

Matching provider labels do not prove identical commercial contracts,
capacity, eligibility, or execution quality.  A Hugging Face link is an
open-weight population proxy, not a license audit.  Posted prices are not firm
fills, and simulated cheapest-provider choices are not routed volume.

Artifacts:

- `analysis/h93_summary.json`
- `analysis/h93_simultaneous_basis.parquet`
- `analysis/h93_cross_router_price_policy_panel.png`
- `src/orcap/analysis/h93_cross_router_price_policy.py`
