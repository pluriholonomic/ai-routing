# How the open AI inference market will evolve

*2026-07-12. Short version. Depth lives in `marketplace-comparison-plan.md`
(literature), `compute-brokerage-hypothesis.md` (pre-registered predictions),
and the nightly memo (all results).*

## The thesis

**The AI inference market is becoming a brokerage business sitting on a
commodity business — like retail stock trading, not like a crypto exchange.**

The money settles into the layer that *owns the customer* (coding agents,
chat apps — the "brokers"), while everything below them commoditizes: routing
fees compete to zero, providers become interchangeable dealers earning thin
spreads on identical open models, and GPU capacity trades like electricity —
a raw input with its own emerging futures and capacity contracts. Prices in
this market don't behave like a ticker: they are posted menus that change
rarely and strategically, while minute-to-minute imbalances are absorbed by
queues and rate limits instead of price moves.

## Five measured facts that anchor it

1. **Users don't shop; the router shops for them — 20× more aggressively.**
   Demand barely responds to price (−0.05 elasticity), but the router
   reallocates hard (−1.15). That gap is why customer-owning apps, not
   infrastructure, will capture the margin.
2. **Prices are menus, not tickers.** Under 3% of provider-model pairs
   reprice on a given day, and when they do, the median move is 25%. In a
   6-day window only 7% of busy endpoints ever changed price — while 80% hit
   rate limits. Congestion is managed with throttling, not surge pricing.
3. **There is no hidden spread.** The router displays provider prices
   verbatim (97% exactly zero markup vs. going direct). Its 5.5% fee is a
   visible convenience charge — which history says gets competed away, while
   app-layer fees historically don't (MetaMask still charges 0.875% five
   years after free alternatives appeared).
4. **Providers price-match instead of undercutting.** On half of
   multi-provider model-days the two cheapest quotes are *identical to the
   cent*; otherwise the gap is large (~8%). And providers that reprice
   frequently sit ~14% *below* slow ones on the same model — slow, sticky
   pricing is subsidized by customers who don't switch.
5. **The GPU layer already shows electricity-market behavior.** Providers get
   paid only per token while holding ~ED-hospital levels of spare capacity —
   the classic setup that historically forces capacity contracts into
   existence. Provisioned-throughput products (Azure PTUs, priority tiers)
   are that prediction already coming true.

## What each layer becomes

| Layer | Today | Becomes | Because |
|---|---|---|---|
| Apps/agents (own the user) | Markups, subscriptions | **Keep 15%+ margins; get paid for order flow** | Captive users don't price-shop (fact 1) |
| Routers | 5.5% fee | **~Free utility; 2–4 survivors; auctions replace posted menus** | Zero-markup rivals already live; fees at this layer always compress |
| Providers | 70 quoting firms | **Two-speed dealers: fast algorithmic repricers vs. slow premium ones; consolidation per model to 2–5** | Identical models = commodity dealing (facts 2, 4) |
| Open models | Free assets | **Commodity specs; authors monetize by serving or certifying, not licensing** | The asset earns nothing; the service does |
| GPUs | Hourly rentals | **Electricity-style market: capacity contracts + futures + peak pricing** | Non-storable output, bursty demand, missing money (fact 5) |

Plus one wildcard: **a quality-fraud scandal** (providers silently serving
degraded/quantized models — ~⅓ of third-party endpoints already diverge from
reference weights in outside audits) forces an attestation standard, the way
ad fraud forced ads.txt.

## Predictions with dates (hold us to these)

- Router effective take <3% **or** 15+ points of share to zero-fee routers — by end-2027.
- Explicit pay-for-order-flow deals between providers/routers and apps — within 18 months.
- A major router introduces per-request provider bidding — within 24 months.
- A major provider adopts time-of-day pricing — within 24 months.
- Provisioned/priority capacity becomes a mid-double-digit share of provider revenue — by 2028.
- GPU futures live or die by a stated test: cross-index basis under 5% with both hedgers present.
- App-layer margins do **not** compress below 15% through 2027.

## Score so far

17 pre-registered predictions graded nightly: **5 consistent, 0 wrong**, 12
accumulating or awaiting their window. One flag worth watching: after a price
cut, rivals usually cut and then *drift back up* (72% of typed events) — the
textbook algorithmic-collusion signature — but the sample is 18 events and
it's tangled with launch experimentation. If it survives at 100+ events, that
becomes the headline result.

## What would prove us wrong

- Router fees hold at 5%+ for years while app margins compress → margins live
  at the routing layer and the brokerage frame is inverted.
- Prices start moving with load at high frequency → this is a spot exchange
  after all.
- The 20× shopping gap closes → no captive-customer rent exists to sustain
  the app layer.
