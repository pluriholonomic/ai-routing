#!/bin/bash
# Overlay only the small inputs needed by paid price planning.
# Usage: assemble_price_artifacts.sh [hours-back] [dest] [paid|event]
set -euo pipefail

HOURS=${1:-26}
DEST=${2:-input-data}
MODE=${3:-paid}
SINCE=$(date -u -d "-${HOURS} hours" +%Y-%m-%dT%H:%M:%SZ)
WORKFLOWS="paid-price-response.yml price-event-probes.yml market-measurement.yml adaptive-router.yml"
if [ "$MODE" = "event" ]; then
  WORKFLOWS="$WORKFLOWS capture.yml"
elif [ "$MODE" != "paid" ]; then
  echo "mode must be paid or event" >&2
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
    gh run list --workflow "$wf" --status success --limit 40 \
      --json databaseId,createdAt \
      --jq ".[] | select(.createdAt > \"$SINCE\") | .databaseId"
  )
done
echo "assembled $count price-planning artifacts into $DEST"
