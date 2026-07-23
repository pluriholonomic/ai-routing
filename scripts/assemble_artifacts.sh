#!/bin/bash
# Merge buffered capture/gpu workflow artifacts into a local data dir.
# CI-only (GNU date, gh CLI with GH_TOKEN). Usage: assemble_artifacts.sh [hours-back] [dest]
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=gh_retry.sh
source "$SCRIPT_DIR/gh_retry.sh"
HOURS=${1:-26}
DEST=${2:-data}
SINCE=$(date -u -d "-${HOURS} hours" +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$DEST"
count=0
artifact_run_index=$(mktemp)
artifact_index_available=false
trap 'rm -f "$artifact_run_index" "${artifact_run_index}.unsorted"' EXIT
if gh_build_artifact_run_index "$artifact_run_index" "$SINCE"; then
  artifact_index_available=true
  echo "indexed $(wc -l <"$artifact_run_index") artifact-bearing runs since $SINCE"
else
  echo "repository artifact index unavailable; falling back to per-run probes" >&2
fi
for wf in capture.yml capture-backstop.yml capacity-policy-probes.yml enforcement-policy-probes.yml decomposition-probes.yml decomposition-replication.yml route-calibration.yml paid-price-response.yml price-event-probes.yml market-measurement.yml glm52-routing.yml glm52-market-share-hmp.yml information-congestion.yml information-congestion-quality.yml score-memory-routing.yml score-memory-quality.yml adaptive-router.yml evals.yml gpu.yml hf-router.yml hf-policy-probes.yml livepeer.yml probes.yml router-catalogs.yml watchers.yml; do
  limit=40
  # The GLM panel produces four immutable runs per hour; 120 covers the full
  # 26-hour assembly window without silently dropping pre-compaction blocks.
  if [ "$wf" = "glm52-routing.yml" ] || [ "$wf" = "score-memory-routing.yml" ] || [ "$wf" = "glm52-market-share-hmp.yml" ] || [ "$wf" = "information-congestion.yml" ]; then
    limit=120
  fi
  # The HMP detector follows every five-minute public capture (up to 12/hour),
  # so a 26-hour compaction window needs more than the GLM hourly campaigns.
  if [ "$wf" = "glm52-market-share-hmp.yml" ] || [ "$wf" = "information-congestion.yml" ]; then
    limit=400
  fi
  if [ "$wf" = "glm52-market-share-hmp.yml" ] || [ "$wf" = "information-congestion.yml" ]; then
    # A failed paid runner still contains its outcome-free immutable assignment.
    # Request-level outcomes go directly to private HF, never a public artifact.
    run_ids=$(gh_retry run list --workflow "$wf" --limit "$limit" \
      --json databaseId,createdAt \
      --jq ".[] | select(.createdAt > \"$SINCE\") | .databaseId")
  else
    run_ids=$(gh_retry run list --workflow "$wf" --status success --limit "$limit" \
      --json databaseId,createdAt \
      --jq ".[] | select(.createdAt > \"$SINCE\") | .databaseId")
  fi
  for id in $run_ids; do
    if [ "$artifact_index_available" = true ] &&
      ! gh_run_has_indexed_artifact "$artifact_run_index" "$id"; then
      continue
    fi
    tmp="/tmp/art-$id"
    if gh_retry run download "$id" --dir "$tmp"; then
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
