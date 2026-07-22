#!/bin/bash
# Merge buffered capture/gpu workflow artifacts into a local data dir.
# CI-only (GNU date, gh CLI with GH_TOKEN). Usage: assemble_artifacts.sh [hours-back] [dest]
set -euo pipefail
HOURS=${1:-26}
DEST=${2:-data}
SINCE=$(date -u -d "-${HOURS} hours" +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$DEST"
count=0
for wf in capture.yml capacity-policy-probes.yml enforcement-policy-probes.yml decomposition-probes.yml decomposition-replication.yml route-calibration.yml paid-price-response.yml price-event-probes.yml market-measurement.yml glm52-routing.yml glm52-market-share-hmp.yml score-memory-routing.yml score-memory-quality.yml adaptive-router.yml evals.yml gpu.yml hf-router.yml hf-policy-probes.yml livepeer.yml probes.yml router-catalogs.yml watchers.yml; do
  limit=40
  # The GLM panel produces four immutable runs per hour; 120 covers the full
  # 26-hour assembly window without silently dropping pre-compaction blocks.
  if [ "$wf" = "glm52-routing.yml" ] || [ "$wf" = "score-memory-routing.yml" ] || [ "$wf" = "glm52-market-share-hmp.yml" ]; then
    limit=120
  fi
  # The HMP detector follows every five-minute public capture (up to 12/hour),
  # so a 26-hour compaction window needs more than the GLM hourly campaigns.
  if [ "$wf" = "glm52-market-share-hmp.yml" ]; then
    limit=400
  fi
  if [ "$wf" = "glm52-market-share-hmp.yml" ]; then
    # A failed paid runner still contains the immutable assignment reservation.
    # Preserve all HMP statuses so compaction cannot later make that task eligible again.
    run_ids=$(gh run list --workflow "$wf" --limit "$limit" \
      --json databaseId,createdAt \
      --jq ".[] | select(.createdAt > \"$SINCE\") | .databaseId")
  else
    run_ids=$(gh run list --workflow "$wf" --status success --limit "$limit" \
      --json databaseId,createdAt \
      --jq ".[] | select(.createdAt > \"$SINCE\") | .databaseId")
  fi
  for id in $run_ids; do
    tmp="/tmp/art-$id"
    if gh run download "$id" --dir "$tmp" 2>/dev/null; then
      # Most artifact roots hold a data/ tree directly. Plan-first paid jobs
      # upload both a JSON bundle and plan-data/, so unwrap that directory into
      # the canonical data root instead of publishing plan-data/curated/*.
      for d in "$tmp"/*/; do
        if [ -d "${d}plan-data" ]; then
          cp -R "${d}plan-data"/. "$DEST"/ 2>/dev/null || true
        else
          cp -R "$d". "$DEST"/ 2>/dev/null || true
        fi
      done
      rm -rf "$tmp"
      count=$((count + 1))
    fi
  done
done
echo "assembled $count artifacts into $DEST"
