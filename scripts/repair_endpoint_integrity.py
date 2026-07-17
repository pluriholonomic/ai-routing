#!/usr/bin/env python3
"""Repair exact endpoint overlap and rebuild pricing state chronologically."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from huggingface_hub import CommitOperationAdd, CommitOperationDelete, snapshot_download

from orcap.compact import (
    CHANGES_SCHEMA,
    canonicalize_pricing_endpoints,
    deduplicate_endpoint_records,
    fold_pricing_changes,
    save_state,
)
from orcap.config import HF_DATASET_REPO
from orcap.hf_store import get_api


def _yesterday_utc() -> str:
    return (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _code_commit() -> str | None:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_repair_bundle(
    source_dir: Path,
    output_dir: Path,
    *,
    dates: list[str],
    input_revision: str,
) -> dict[str, Any]:
    """Build repaired endpoint, event, daily-state, and current-state files."""
    if not dates:
        raise ValueError("at least one completed endpoint date is required")
    dates = sorted(set(dates))
    output_files: list[Path] = []
    daily: list[dict[str, Any]] = []
    event_fields: Counter[str] = Counter()
    state: dict[str, dict[str, Any]] = {}

    for dt in dates:
        partition = source_dir / "curated" / "endpoints_snapshots" / f"dt={dt}"
        files = sorted(partition.glob("*.parquet"))
        if not files:
            raise FileNotFoundError(f"no endpoint snapshots found for {dt}")
        tables = [pq.ParquetFile(path).read() for path in files]
        physical = pa.concat_tables(tables, promote_options="permissive")
        repaired, audit = deduplicate_endpoint_records(physical)
        pricing = canonicalize_pricing_endpoints(repaired)

        endpoint_out = (
            output_dir
            / "curated"
            / "endpoints_snapshots"
            / f"dt={dt}"
            / "part-0.parquet"
        )
        endpoint_out.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(repaired, endpoint_out, compression="zstd")
        output_files.append(endpoint_out)

        events, state = fold_pricing_changes(pricing, state)
        event_fields.update(event["field"] for event in events)
        changes_out = output_dir / "derived" / "pricing_changes" / f"dt={dt}" / "part-0.parquet"
        changes_out.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(
            pa.Table.from_pylist([{"dt": dt, **event} for event in events], schema=CHANGES_SCHEMA),
            changes_out,
            compression="zstd",
        )
        output_files.append(changes_out)

        state_out = output_dir / "derived" / "pricing_state" / f"dt={dt}" / "part-0.parquet"
        save_state(state, state_out)
        output_files.append(state_out)

        daily.append(
            {
                "dt": dt,
                "source_files": len(files),
                **audit,
                "listing_keys": pricing.num_rows,
                "same_listing_raw_variants": repaired.num_rows - pricing.num_rows,
                "pricing_events": len(events),
                "price_field_changes": sum(
                    1 for event in events if not event["field"].startswith("__")
                ),
            }
        )

    current_out = output_dir / "derived" / "pricing_current.parquet"
    save_state(state, current_out)
    output_files.append(current_out)

    manifest_path = output_dir / "quality" / "endpoint-integrity-repair-v1.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "input_revision": input_revision,
        "code_commit": _code_commit(),
        "dates": dates,
        "deduplication_unit": [
            "run_ts",
            "model_id",
            "provider_name",
            "tag",
            "endpoint_fingerprint",
            "record_json",
        ],
        "daily": daily,
        "totals": {
            "physical_rows": sum(row["physical_rows"] for row in daily),
            "distinct_source_records": sum(row["distinct_source_records"] for row in daily),
            "duplicate_rows_removed": sum(row["duplicate_rows_removed"] for row in daily),
            "listing_keys": sum(row["listing_keys"] for row in daily),
            "same_listing_raw_variants": sum(
                row["same_listing_raw_variants"] for row in daily
            ),
            "pricing_events": sum(row["pricing_events"] for row in daily),
            "price_field_changes": sum(row["price_field_changes"] for row in daily),
        },
        "event_fields": dict(sorted(event_fields.items())),
        "invariants": {
            "exact_source_records_unique": True,
            "same_listing_price_conflicts": 0,
            "chronological_daily_state_chain": True,
            "daily_event_partitions_replaced_not_merged": True,
        },
    }
    manifest["output_files"] = {
        str(path.relative_to(output_dir)): {
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in output_files
    }
    manifest["manifest_path"] = str(manifest_path.relative_to(output_dir))
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def publish_bundle(
    output_dir: Path,
    manifest: dict[str, Any],
    *,
    repo_id: str,
    input_revision: str,
    source_repo_files: list[str],
) -> str:
    dates = set(manifest["dates"])
    expected_paths = set(manifest["output_files"]) | {manifest["manifest_path"]}
    delete_paths: list[str] = []
    for path in source_repo_files:
        endpoint_prefix = "curated/endpoints_snapshots/dt="
        changes_prefix = "derived/pricing_changes/dt="
        state_prefix = "derived/pricing_state/dt="
        if path.startswith((endpoint_prefix, changes_prefix, state_prefix)):
            dt = path.split("/dt=", 1)[1].split("/", 1)[0]
            if dt in dates and path not in expected_paths:
                delete_paths.append(path)

    operations = [CommitOperationDelete(path_in_repo=path) for path in sorted(delete_paths)]
    operations.extend(
        CommitOperationAdd(path_in_repo=path, path_or_fileobj=str(output_dir / path))
        for path in sorted(expected_paths)
    )
    api = get_api()
    commit = api.create_commit(
        repo_id=repo_id,
        repo_type="dataset",
        operations=operations,
        commit_message=(
            "repair endpoint overlap and rebuild chronological pricing states "
            f"through {max(dates)}"
        ),
        parent_commit=input_revision,
    )
    return str(commit.oid)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=HF_DATASET_REPO)
    parser.add_argument("--revision")
    parser.add_argument("--through", default=_yesterday_utc())
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--output-manifest", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    api = get_api()
    revision = args.revision or str(api.dataset_info(args.repo).sha)
    repo_files = api.list_repo_files(
        repo_id=args.repo,
        repo_type="dataset",
        revision=revision,
    )
    dates = sorted(
        {
            path.split("/dt=", 1)[1].split("/", 1)[0]
            for path in repo_files
            if path.startswith("curated/endpoints_snapshots/dt=")
            and path.endswith(".parquet")
            and path.split("/dt=", 1)[1].split("/", 1)[0] <= args.through
        }
    )
    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="orcap-endpoint-repair-"))
    source_dir = workdir / "source"
    output_dir = workdir / "output"
    snapshot_download(
        repo_id=args.repo,
        repo_type="dataset",
        revision=revision,
        local_dir=source_dir,
        allow_patterns=[f"curated/endpoints_snapshots/dt={dt}/*" for dt in dates],
        token=api.token,
        max_workers=8,
    )
    manifest = build_repair_bundle(
        source_dir,
        output_dir,
        dates=dates,
        input_revision=revision,
    )
    if args.publish:
        manifest["published_revision"] = publish_bundle(
            output_dir,
            manifest,
            repo_id=args.repo,
            input_revision=revision,
            source_repo_files=repo_files,
        )
    if args.output_manifest:
        args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.output_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
