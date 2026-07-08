#!/bin/zsh
# Daily local job: pull the CI-rendered memo from the private HF dataset and
# redeploy it to the canonical claude.ai artifact. Artifact publishing needs a
# user Claude session, which is why this runs locally (launchd) rather than CI.
set -euo pipefail
cd "$(dirname "$0")/.."

MEMO_URL="https://claude.ai/code/artifact/e7e8f667-3534-4145-a6b9-6663a74c51e3"
OUT=/tmp/orcap-memo.html

uv run python - <<'EOF'
import shutil
from huggingface_hub import hf_hub_download
p = hf_hub_download(
    "t4run/openrouter-market-history", "reports/memo.html",
    repo_type="dataset", force_download=True,
)
shutil.copy(p, "/tmp/orcap-memo.html")
print("downloaded", p)
EOF

claude -p "Call the Artifact tool exactly once with file_path=$OUT, favicon 🧮, \
url $MEMO_URL, label auto-$(date +%Y%m%d), description 'Empirical screening memo: \
inference-market/DeFi analogy — aggregated RFQ verdict, provider typology, live \
daily-refreshed statistics.' Then stop. Do not modify any files." \
  --allowedTools "Artifact" --max-turns 3
echo "redeployed $(date)"
