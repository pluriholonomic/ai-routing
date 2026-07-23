#!/bin/bash
# Overlay only the small inputs needed by paid price planning.
# Usage: assemble_price_artifacts.sh [hours-back] [dest] [paid|event|glm52|hmp|ic|score-memory-routing|score-memory-quality|score-memory]
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=gh_retry.sh
source "$SCRIPT_DIR/gh_retry.sh"

HOURS=${1:-26}
DEST=${2:-input-data}
MODE=${3:-paid}
SINCE=$(date -u -d "-${HOURS} hours" +%Y-%m-%dT%H:%M:%SZ)
WORKFLOWS="paid-price-response.yml price-event-probes.yml market-measurement.yml adaptive-router.yml"
LIMIT=40
if [ "$MODE" = "event" ]; then
  WORKFLOWS="$WORKFLOWS capture.yml capture-backstop.yml"
elif [ "$MODE" = "glm52" ]; then
  # This study runs every 15 minutes. Read enough immutable checkpoints to
  # reconstruct two rolling days of spend before nightly HF compaction.
  WORKFLOWS="glm52-routing.yml"
  LIMIT=220
elif [ "$MODE" = "hmp" ]; then
  # Public captures discover events; prior HMP plan artifacts are the
  # uncompacted queue and assignment reservations. Request-level attempts and
  # spend are checkpointed directly to the private HF dataset.
  WORKFLOWS="capture.yml capture-backstop.yml glm52-market-share-hmp.yml"
  LIMIT=650
elif [ "$MODE" = "ic" ]; then
  # Public captures define the ex-ante role panel. Prior information-congestion
  # plans reserve task IDs; request outcomes are checkpointed only to private HF.
  WORKFLOWS="capture.yml capture-backstop.yml information-congestion.yml information-congestion-quality.yml"
  LIMIT=650
elif [ "$MODE" = "score-memory-quality" ]; then
  WORKFLOWS="score-memory-quality.yml"
  LIMIT=40
elif [ "$MODE" = "score-memory-routing" ]; then
  WORKFLOWS="score-memory-routing.yml"
  LIMIT=220
elif [ "$MODE" = "score-memory" ]; then
  # The analysis overlays both high-frequency owned choices and the separate
  # six-hour fidelity bank before nightly Hugging Face compaction.
  WORKFLOWS="glm52-routing.yml score-memory-routing.yml score-memory-quality.yml"
  LIMIT=220
elif [ "$MODE" != "paid" ]; then
  echo "mode must be paid, event, glm52, hmp, ic, score-memory-routing, score-memory-quality, or score-memory" >&2
  exit 2
fi

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
for wf in $WORKFLOWS; do
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    if [ "$artifact_index_available" = true ] &&
      ! gh_run_has_indexed_artifact "$artifact_run_index" "$id"; then
      continue
    fi
    tmp="/tmp/price-art-$id"
    if gh_retry run download "$id" --dir "$tmp"; then
      for directory in "$tmp"/*/; do
        [ -d "$directory" ] || continue
        if [ -d "${directory}plan-data" ]; then
          cp -R "${directory}plan-data"/. "$DEST"/ 2>/dev/null || true
        else
          cp -R "$directory". "$DEST"/ 2>/dev/null || true
        fi
      done
      rm -rf "$tmp"
      count=$((count + 1))
    fi
  done < <(
    if { [ "$MODE" = "hmp" ] && [ "$wf" = "glm52-market-share-hmp.yml" ]; } ||
      { [ "$MODE" = "ic" ] && [ "$wf" = "information-congestion.yml" ]; } ||
      { [ "$MODE" = "event" ] && [ "$wf" = "price-event-probes.yml" ]; }; then
      # All statuses retain the outcome-free pre-request assignment artifact.
      # Ingest it as an at-most-once reservation; request-level execution
      # artifacts are never published by the HMP/IC workflows. Event workflows
      # also expose redacted execution checkpoints before the full delayed-wave
      # run completes, closing the gap between serialized execute jobs.
      gh_retry run list --workflow "$wf" --limit "$LIMIT" \
        --json databaseId,createdAt \
        --jq ".[] | select(.createdAt > \"$SINCE\") | .databaseId"
    else
      gh_retry run list --workflow "$wf" --status success --limit "$LIMIT" \
        --json databaseId,createdAt \
        --jq ".[] | select(.createdAt > \"$SINCE\") | .databaseId"
    fi
  )
done
echo "assembled $count price-planning artifacts into $DEST"
