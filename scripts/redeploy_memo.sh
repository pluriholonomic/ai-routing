#!/bin/zsh
# Helper for refreshing the claude.ai artifact copy of the memo from inside an
# interactive Claude Code session (the Artifact tool is not available headlessly,
# so this cannot be cron'd — the always-fresh copy lives at the private HF Space
# https://huggingface.co/spaces/t4run/openrouter-memo, updated nightly by CI).
#
# Usage: run this to fetch the latest CI-rendered memo to /tmp/orcap-memo.html,
# then ask Claude in-session to redeploy it to the canonical artifact URL:
#   https://claude.ai/code/artifact/e7e8f667-3534-4145-a6b9-6663a74c51e3
set -euo pipefail
cd "$(dirname "$0")/.."

uv run python - <<'EOF'
import shutil
from huggingface_hub import hf_hub_download
p = hf_hub_download(
    "t4run/openrouter-market-history", "reports/memo.html",
    repo_type="dataset", force_download=True,
)
shutil.copy(p, "/tmp/orcap-memo.html")
print("latest memo at /tmp/orcap-memo.html")
EOF
