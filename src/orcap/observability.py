"""Source-run provenance and monitor configuration.

Collectors write one immutable ``source_runs`` row for every attempt.  This
is deliberately separate from raw HTTP capture: it lets the monitor tell a
valid zero-row response, an optional skipped source, and a failed collector
apart without interpreting a vendor payload.
"""

import json
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .config import CURATED_DIR, dt_partition, run_timestamp

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "config" / "sources.toml"


@dataclass(frozen=True)
class SourceSpec:
    name: str
    required: bool
    cadence_minutes: int
    min_rows: int


def registry() -> tuple[dict[str, SourceSpec], dict[str, list[str]]]:
    """Load the checked-in source registry without a third-party YAML parser."""
    with REGISTRY_PATH.open("rb") as f:
        data = tomllib.load(f)
    specs = {
        name: SourceSpec(
            name=name,
            required=bool(raw.get("required", False)),
            cadence_minutes=int(raw["cadence_minutes"]),
            min_rows=int(raw.get("min_rows", 0)),
        )
        for name, raw in data["sources"].items()
    }
    profiles = {name: list(sources) for name, sources in data["profiles"].items()}
    return specs, profiles


def source_spec(name: str) -> SourceSpec:
    specs, _ = registry()
    if name not in specs:
        raise KeyError(f"source {name!r} is not registered in {REGISTRY_PATH}")
    return specs[name]


def utc_now() -> datetime:
    return datetime.now(UTC)


def write_source_run(
    source: str,
    *,
    status: str,
    rows: int = 0,
    watermark: str | None = None,
    detail: dict[str, Any] | None = None,
    run_ts: str | None = None,
    dt: str | None = None,
    curated_dir: Path = CURATED_DIR,
) -> Path:
    """Write one source-attempt record to a collision-safe parquet partition."""
    if status not in {"success", "degraded", "failed", "skipped"}:
        raise ValueError(f"unsupported source-run status: {status}")
    spec = source_spec(source)
    run_ts = run_ts or run_timestamp()
    dt = dt or dt_partition()
    row = {
        "run_ts": run_ts,
        "dt": dt,
        "source": source,
        "required": spec.required,
        "status": status,
        "rows": int(rows),
        "watermark": watermark or run_ts,
        "detail_json": json.dumps(detail or {}, separators=(",", ":"), sort_keys=True),
        "registry_path": str(REGISTRY_PATH.relative_to(REPO_ROOT)),
    }
    out_dir = curated_dir / "source_runs" / f"dt={dt}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{run_ts}-{source}.parquet"
    pq.write_table(pa.Table.from_pylist([row]), out, compression="zstd")
    return out


def summary_rows(summary: Any) -> int:
    """Extract a conservative row count from existing collector summaries."""
    if isinstance(summary, list):
        return sum(summary_rows(item) for item in summary)
    if not isinstance(summary, dict):
        return 0
    keys = (
        "rows",
        "endpoints",
        "gpu_offers",
        "hf_models",
        "deepinfra_models",
        "combos",
        "models",
    )
    return max((int(summary[k] or 0) for k in keys if k in summary), default=0)
