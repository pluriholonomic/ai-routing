"""Shared configuration for capture jobs. Everything is env-overridable so the
same code runs locally and in GitHub Actions."""

import os
from datetime import UTC, datetime
from pathlib import Path

BASE_URL = "https://openrouter.ai"
API_V1 = f"{BASE_URL}/api/v1"

USER_AGENT = os.environ.get(
    "ORCAP_USER_AGENT",
    "orcap/0.1 (OpenRouter market-history archiver; contact: tarun@gauntlet.xyz)",
)

# Local staging directory; workflows push its contents to the HF dataset repo.
DATA_DIR = Path(os.environ.get("ORCAP_DATA_DIR", "data"))
RAW_DIR = DATA_DIR / "raw"
CURATED_DIR = DATA_DIR / "curated"

HF_DATASET_REPO = os.environ.get("ORCAP_HF_REPO", "t4run/openrouter-market-history")

MAX_CONCURRENCY = int(os.environ.get("ORCAP_MAX_CONCURRENCY", "8"))
REQUESTS_PER_SECOND = float(os.environ.get("ORCAP_RPS", "5"))


def run_timestamp(now: datetime | None = None) -> str:
    """Compact UTC run id used in filenames, e.g. 20260706T221500Z."""
    now = now or datetime.now(UTC)
    return now.strftime("%Y%m%dT%H%M%SZ")


def dt_partition(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return now.strftime("%Y-%m-%d")
