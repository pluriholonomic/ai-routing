# Information-congestion paper review loop

Date: 2026-07-22

## Round 3 decisions

| Venue | Current paper | Review | Decision | Overall |
|---|---|---|---|---:|
| ACM EC | `ec/router-is-the-mechanism.pdf` | `ec/review-ec-information-congestion-round-3.md` | Weak Reject | 5/10 |
| ICML | `icml/phase-transitions-routing-games.pdf` | `icml/review-icml-information-congestion-round-3.md` | Accept | 7/10 |
| NeurIPS | `neurips/price-of-softmax.pdf` | `neurips/review-neurips-property-tested-round-3.md` | Accept | 7/10 |

The loop stops after this round because two of three venue reviews recommend
acceptance. No review decision depends on promoting the rejected empirical
GLM-\(o(n)\)/non-GLM-\(\Omega(n)\) contrast. The accepted papers instead use
the public data as a property test and keep the information-congestion theorem
conditional on its declared loss.

## Venue commit history

- ACM EC manuscript revision: `0b72efa`.
- ICML manuscript revision: `e18d914`.
- NeurIPS manuscript revision: `29edc02`.

The analysis and simulation bundle is in `cc625a4`. Each venue manuscript was
committed separately after a successful LaTeX build and visual PDF inspection.

## Why ACM EC remains below acceptance

The EC review treats the current theorem as too reduced-form for the venue. A
future EC-only round should derive the congestion loss from provider learning or
capacity primitives, characterize anonymous adaptive entry, and prove an
implementable exposure fee or allocation rule that decentralizes the planner's
target under identity splitting and covariance estimation error. This remaining
venue-specific weakness does not invalidate the accepted ICML learning result
or NeurIPS environment contribution.

## Shared claim boundary after review

- GLM-5.2 has a small active set and a large inverse-price shadow-share transfer.
- Current GLM effective rank is linear-compatible; it does not establish
  \(k^*=o(n)\).
- Non-GLM active repricing is sparse; it does not establish \(k=\Omega(n)\).
- SM3 validates the conditional optimizer numerically and rejects its declared
  bandit allocation channel.
- SM4 shows objective conflict and bounded deviation susceptibility only under
  declared technologies and demand.
- Owned price sorting has a large current effect but has not passed its frozen
  confirmatory gates.
- No paper identifies collusion, dumping, provider intent, market-wide flow, or
  live welfare.
