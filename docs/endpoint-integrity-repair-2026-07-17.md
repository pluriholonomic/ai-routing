# Endpoint overlap and pricing-ledger repair

## Finding

The endpoint acquisition panel at immutable dataset revision
`9cbed9f25ddf05c26de8fbf91374e6dd6adc26f1` contained repeated copies of
source records. The overlap came from reassembling a stable buffered artifact
for a UTC date that already had a consolidated `part-0.parquet`, then
concatenating both objects without an identity check.

Across the ten completed UTC dates from 2026-07-07 through 2026-07-16:

- 3,510,492 physical rows represented 1,977,529 distinct source records;
- 1,532,963 rows were exact overlap copies;
- the distinct records represented 1,968,679 provider-model-tag-fingerprint
  listing observations;
- 8,850 additional raw variants shared a listing key and capture time.

The raw variants were not silently discarded. An explicit conflict audit found
8,388 listing-time groups with more than one raw payload. Every difference was
in router-published availability state. There were zero price conflicts and
zero capability conflicts. The repaired curated panel therefore removes only
rows with the same capture time, model, provider, tag, endpoint fingerprint,
and raw `record_json`; distinct raw variants remain available for an
availability-specific measurement model.

## Derived-event failure

The stored pricing ledger also failed chronological reproducibility. A clean
fold from the public endpoint snapshots produced 3,219 unique events, while the
stored ledger contained 4,015. Relative to the clean fold, the stored ledger
had 797 stale events and omitted one endpoint removal. The stale set included
347 additions, 232 removals, and 218 price-field changes.

The cause was separate from exact row overlap. Re-compacting an old day loaded
the global latest-price state, folded an earlier endpoint partition against
that future state, and merged the resulting events into the existing daily
partition. Those stale events could never be removed by later runs.

## Repair invariant

The new pipeline enforces two different units:

1. Curated storage is unique by source record. Exact artifact overlap is
   removed, but different raw payloads are preserved.
2. Pricing state is unique by listing and capture time. Availability variants
   collapse only after the pipeline verifies that every tracked price agrees;
   a price conflict fails the job.

Each completed UTC day now has an immutable end-of-day pricing state. A day is
folded only from the latest state strictly before that day, and its event
partition is replaced rather than merged. If earlier endpoint history exists
but no prior daily state is available, compaction fails closed and requests the
chronological rebuild.

The repair transaction pins one input revision, rewrites completed endpoint
partitions, rebuilds daily pricing states and event partitions in chronological
order, writes the terminal current state, hashes every output, and publishes a
machine-readable manifest in the same dataset commit. The local dry run removed
1,532,963 exact rows and reconstructed 3,219 events, including 1,506 tracked
price-field changes. All 527 repository tests pass after the change.

## Paper boundary

The manuscript's current physical-row count is not an empirical sample-size
claim and must be replaced by the corrected listing-observation count from the
published repair revision. Every paper analysis that reads
`derived/pricing_changes` must be rerun on that revision. Frozen hypotheses and
estimands remain frozen; this is a provenance correction, not a discretionary
specification change. Results will be reported whether they strengthen,
weaken, or reverse the existing conclusions.
