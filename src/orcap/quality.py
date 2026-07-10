"""Evaluate source-run freshness and failure semantics before publication."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .config import CURATED_DIR
from .observability import SourceSpec, registry


def load_runs(curated_dir: Path = CURATED_DIR) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in (curated_dir / "source_runs").glob("dt=*/*.parquet"):
        # ParquetDataset infers ``dt=`` again and conflicts with the explicit
        # string column written by the source-run schema.
        rows.extend(pq.ParquetFile(p).read().to_pylist())
    return rows


def _stamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def _latest(rows: list[dict[str, Any]], source: str) -> dict[str, Any] | None:
    candidates = [r for r in rows if r["source"] == source]
    return max(candidates, key=lambda r: r["run_ts"], default=None)


def _state(spec: SourceSpec, row: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
    severity = "red" if spec.required else "yellow"
    if row is None:
        return {"source": spec.name, "state": severity, "reason": "no source-run record"}
    age_minutes = (now - _stamp(row["run_ts"])).total_seconds() / 60
    if row["status"] == "failed":
        return {"source": spec.name, "state": severity, "reason": "collector failed", "row": row}
    if row["status"] in {"degraded", "skipped"}:
        return {"source": spec.name, "state": severity, "reason": row["status"], "row": row}
    if int(row["rows"]) < spec.min_rows:
        return {
            "source": spec.name,
            "state": severity,
            "reason": f"rows {row['rows']} below minimum {spec.min_rows}",
            "row": row,
        }
    if age_minutes > spec.cadence_minutes:
        return {
            "source": spec.name,
            "state": severity,
            "reason": f"stale by {age_minutes:.0f} minutes (SLO {spec.cadence_minutes})",
            "row": row,
        }
    return {"source": spec.name, "state": "green", "reason": "fresh", "row": row}


def check(
    profile: str = "core", *, curated_dir: Path = CURATED_DIR, now: datetime | None = None
) -> dict[str, Any]:
    specs, profiles = registry()
    if profile not in profiles:
        raise KeyError(f"unknown source-health profile {profile!r}")
    now = now or datetime.now(UTC)
    rows = load_runs(curated_dir)
    checks = [_state(specs[name], _latest(rows, name), now) for name in profiles[profile]]
    states = [item["state"] for item in checks]
    overall = "red" if "red" in states else "yellow" if "yellow" in states else "green"
    return {
        "profile": profile,
        "checked_at": now.isoformat(),
        "overall": overall,
        "sources": checks,
    }


def main(profile: str = "core", fail_on_degraded: bool = False) -> dict[str, Any]:
    result = check(profile)
    print(json.dumps(result, indent=2, default=str))
    if result["overall"] == "red" or (fail_on_degraded and result["overall"] == "yellow"):
        raise RuntimeError(f"source health for profile {profile} is {result['overall']}")
    return result
