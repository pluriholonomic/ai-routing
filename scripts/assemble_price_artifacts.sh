#!/bin/bash
# Overlay only the small inputs needed by paid price planning.
# Usage: assemble_price_artifacts.sh [hours-back] [dest] [paid|event|glm52|hmp|score-memory-routing|score-memory-quality|score-memory]
set -euo pipefail

HOURS=${1:-26}
DEST=${2:-input-data}
MODE=${3:-paid}
SINCE=$(date -u -d "-${HOURS} hours" +%Y-%m-%dT%H:%M:%SZ)
WORKFLOWS="paid-price-response.yml price-event-probes.yml market-measurement.yml adaptive-router.yml"
LIMIT=40
if [ "$MODE" = "event" ]; then
  WORKFLOWS="$WORKFLOWS capture.yml"
elif [ "$MODE" = "glm52" ]; then
  # This study runs every 15 minutes. Read enough immutable checkpoints to
  # reconstruct two rolling days of spend before nightly HF compaction.
  WORKFLOWS="glm52-routing.yml"
  LIMIT=220
elif [ "$MODE" = "hmp" ]; then
  # Public captures discover events; prior HMP plan artifacts are the
  # uncompacted queue and assignment reservations. Request-level attempts and
  # spend are checkpointed directly to the private HF dataset.
  WORKFLOWS="capture.yml glm52-market-share-hmp.yml"
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
  echo "mode must be paid, event, glm52, hmp, score-memory-routing, score-memory-quality, or score-memory" >&2
  exit 2
fi

mkdir -p "$DEST"
count=0
for wf in $WORKFLOWS; do
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    tmp="/tmp/price-art-$id"
    if gh run download "$id" --dir "$tmp" 2>/dev/null; then
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
    if [ "$MODE" = "hmp" ] && [ "$wf" = "glm52-market-share-hmp.yml" ]; then
      # All statuses retain the outcome-free pre-request assignment artifact.
      # Ingest it as an at-most-once reservation; request-level execution
      # artifacts are never published by this public repository.
      gh run list --workflow "$wf" --limit "$LIMIT" \
        --json databaseId,createdAt \
        --jq ".[] | select(.createdAt > \"$SINCE\") | .databaseId"
    else
      gh run list --workflow "$wf" --status success --limit "$LIMIT" \
        --json databaseId,createdAt \
        --jq ".[] | select(.createdAt > \"$SINCE\") | .databaseId"
    fi
  )
done
echo "assembled $count price-planning artifacts into $DEST"
