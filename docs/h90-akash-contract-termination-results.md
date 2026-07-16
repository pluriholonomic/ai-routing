# H90 Akash contract-termination study: launch audit

**Study:** `akash-contract-termination-v1`

**Preregistration:** `docs/h90-akash-contract-termination-preregistration.md`

**Data snapshot:** 2026-07-16 04:10 UTC

**Confirmatory release:** 2026-08-15 01:15 UTC

## What was executed

The remote backfill replayed 2,815 immutable Akash close blocks spanning
heights 27,650,430 through 27,736,718. It requested 2,929 retained lease IDs,
recovered 2,929 exact `EventLeaseClosed` rows, and achieved a 100% ID match
rate. Each normalized event points to its raw compressed block-result capture.

The analyzer then joined four independently retained objects: lease snapshots,
complete bounded bid-create event choice sets, accepted bid IDs, and exact close
events. Akash's zero `closed_on` sentinel was detected during the launch audit
and corrected before any H90 artifact was published; zero now means open, not
an observed close. The corrected behavior has a regression test.

## Exploratory pre-preregistration calibration

The immutable pre-cutoff sample contains 36 exactly linked multi-provider
leases across ten selected providers and three source days. The selected bid
was above the lowest retained bid in 20 cases and tied for lowest in 16. All 36
have 300-block follow-up. Twenty have an observed on-chain close and all twenty
replay to an exact close event.

The close-reason calibration contains 19 owner closes and one
insufficient-funds close. There are no provider-initiated, escrow-driven, or
combined non-owner closes within 300 blocks in either price-rank arm. The three
pre-registered exploratory risk differences are therefore exactly zero with
permutation p-values of one. This is a support failure, not evidence that price
rank has no durability effect: the sample contains no primary event with which
to estimate that effect.

## Confirmatory cohort status

No lease is currently in the confirmatory cohort. One linked lease first
appeared after the preregistration time, but it appeared in the first successful
post-cutoff capture and is excluded by the frozen prospective-inception rule.
The second successful post-cutoff capture establishes the first admissible
preceding snapshot; newly created leases observed after that point may enter.

No confirmatory close reason, incidence estimate, coefficient, interval, or
p-value has been released. The analyzer publishes only cohort construction,
price-arm counts, exact-linkage coverage, and follow-up completeness until the
fixed release date.

## Interpretation

The launch validates the event bridge but does not yet validate the economic
hypothesis that accepting a bid above the lowest price purchases latent quality.
The transparent-market comparator should remain outside the manuscript's core
findings until the fixed cohort is released. It is currently useful as a
measurement control: public procurement supplies exact choice and termination
objects, while neither workload start nor compute delivery is public.
