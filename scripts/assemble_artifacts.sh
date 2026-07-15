#!/bin/bash
# Merge buffered capture/gpu workflow artifacts into a local data dir.
# CI-only (GNU date, gh CLI with GH_TOKEN). Usage: assemble_artifacts.sh [hours-back] [dest]
set -euo pipefail
HOURS=${1:-26}
DEST=${2:-data}
SINCE=$(date -u -d "-${HOURS} hours" +%Y-%m-%dT%H:%M:%SZ)
mkdir -p "$DEST"
count=0
for wf in capture.yml capacity-policy-probes.yml enforcement-policy-probes.yml decomposition-probes.yml gpu.yml hf-router.yml livepeer.yml probes.yml watchers.yml; do
  for id in $(gh run list --workflow "$wf" --status success --limit 40 \
      --json databaseId,createdAt \
      --jq ".[] | select(.createdAt > \"$SINCE\") | .databaseId"); do
    tmp="/tmp/art-$id"
    if gh run download "$id" --dir "$tmp" 2>/dev/null; then
      # each artifact root holds the contents of the job's data/ tree
      for d in "$tmp"/*/; do
        cp -R "$d". "$DEST"/ 2>/dev/null || true
      done
      rm -rf "$tmp"
      count=$((count + 1))
    fi
  done
done
echo "assembled $count artifacts into $DEST"
