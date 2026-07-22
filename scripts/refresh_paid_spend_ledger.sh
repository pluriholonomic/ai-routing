#!/bin/bash
# Refresh the authoritative at-most-once ledger after a paid job acquires its
# serialized execution lease. Usage: refresh_paid_spend_ledger.sh [hours] [dest] [mode]
set -euo pipefail

HOURS=${1:-3}
DEST=${2:-plan-data}
MODE=${3:-event}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

uv run python - "$TMP" <<'PY'
import shutil
import sys
from pathlib import Path

from orcap.hf_snapshot_retry import snapshot_download_retry

target = Path(sys.argv[1])
snapshot = snapshot_download_retry(
    "t4run/openrouter-market-history",
    repo_type="dataset",
    allow_patterns=["curated/paid_spend_ledger/*/*.parquet"],
    max_workers=8,
    stale_if_error=False,
)
shutil.copytree(snapshot, target, dirs_exist_ok=True)
PY

# A preceding serialized execution can have finished after this workflow's
# immutable plan was uploaded but before its own workflow run completed. Read
# all available event-run artifacts, including in-progress workflow runs.
./scripts/assemble_price_artifacts.sh "$HOURS" "$TMP" "$MODE"

LEDGER="$TMP/curated/paid_spend_ledger"
if [ ! -d "$LEDGER" ]; then
  echo "authoritative paid spend ledger is unavailable" >&2
  exit 1
fi
mkdir -p "$DEST/curated/paid_spend_ledger"
cp -R "$LEDGER"/. "$DEST/curated/paid_spend_ledger"/
