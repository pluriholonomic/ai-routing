#!/usr/bin/env python3
"""Rerun the public-data manuscript panel on one corrected immutable revision."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from huggingface_hub import get_token, snapshot_download

from orcap.analysis import data

# Prospective owned-outcome studies are intentionally absent. Their only valid
# path is the marker-first confirmatory release transaction.
PAPER_PUBLIC_MODULES = [
    "pm1_hazard_baseline",
    "pm1_temporal_validation",
    "pm2_sufficient_stats",
    "pm5_tie_microstructure",
    "pm6_event_reclassification",
    "pm9_author_anchor",
    "bm1_pricing_technology",
    "bm2_fast_slow_reactions",
    "bm3_quality_adjusted_premium",
    "bm4_reaction_rules",
    "bm5_competitive_null",
    "pm5_menu_simulation",
    "h13_venue_basis",
    "h17_events",
    "h19_provider_types",
    "h21_reactions",
    "h42_routing_mev",
    "h68_competition",
    "h82_enforcement_substitution",
    "h84_stale_quote_hazard",
    "h91_revenue_stationarity",
    "h92_revenue_share_identity",
    "h93_cross_router_price_policy",
    "h94_cross_router_pass_through",
    "wcv0_data_audit",
    "wcv6_revenue_gap",
    "wf20_informational_congestion",
    "scorecard",
    "manuscript_vintages",
]

PUBLIC_INPUT_PATTERNS = [
    "curated/endpoints_snapshots/*/*.parquet",
    "derived/pricing_changes/*/*.parquet",
    "curated/models_snapshots/*/*.parquet",
    "curated/gpu_offers_snapshots/*/*.parquet",
    "curated/congestion_intraday/*/*.parquet",
    "curated/event_bursts_congestion/*/*.parquet",
    "curated/direct_prices_daily/*/*.parquet",
    "curated/endpoint_stats_daily/*/*.parquet",
    "curated/perf_comparisons_daily/*/*.parquet",
    "curated/effective_pricing_daily/*/*.parquet",
    "curated/router_public_quote_snapshots/*/*.parquet",
    "curated/routing_simulation/*/*.parquet",
    "curated/model_activity_daily/*/*.parquet",
    "backfill/models_snapshots_wayback/*/*.parquet",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> set[Path]:
    return {path for path in root.rglob("*") if path.is_file()}


def run(
    revision: str,
    out_dir: Path,
    *,
    snapshot_dir: Path | None = None,
    modules: list[str] | None = None,
    allow_partial: bool = False,
) -> dict[str, Any]:
    os.environ["ORCAP_HF_REVISION"] = revision
    snapshot_dir = snapshot_dir or Path(tempfile.mkdtemp(prefix="orcap-paper-rerun-"))
    snapshot_download(
        repo_id=data.HF_DATASET_REPO,
        repo_type="dataset",
        revision=revision,
        local_dir=snapshot_dir,
        allow_patterns=PUBLIC_INPUT_PATTERNS,
        token=get_token(),
        max_workers=8,
    )
    data.reset_connection()
    os.environ["ORCAP_ANALYSIS_SOURCE"] = "local"
    data.DATA_DIR = snapshot_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    failures: list[str] = []

    selected_modules = modules or PAPER_PUBLIC_MODULES
    unknown = sorted(set(selected_modules) - set(PAPER_PUBLIC_MODULES))
    if unknown:
        raise ValueError(f"unknown paper modules: {unknown}")

    for module_name in selected_modules:
        data.reset_connection()
        before = _files(out_dir)
        module = importlib.import_module(f"orcap.analysis.{module_name}")
        try:
            result = module.run(out_dir)
            status = "ok"
            error = None
        except Exception as exc:
            result = {}
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            failures.append(module_name)
        produced = sorted(_files(out_dir) - before)
        records.append(
            {
                "module": module_name,
                "status": status,
                "error": error,
                "evidence_status": result.get("evidence_status")
                if isinstance(result, dict)
                else None,
                "claim_boundary": result.get("claim_boundary")
                if isinstance(result, dict)
                else None,
                "artifacts": [str(path.relative_to(out_dir)) for path in produced],
            }
        )

    manifest_path = out_dir / "paper_integrity_rerun_manifest.json"
    output_files = sorted(_files(out_dir) - {manifest_path})
    manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "input_revision": revision,
        "analysis_source": {
            "kind": "local_snapshot_of_huggingface_revision",
            "path": str(snapshot_dir.resolve()),
            "patterns": PUBLIC_INPUT_PATTERNS,
        },
        "prospective_owned_outcomes_queried": False,
        "selected_modules": selected_modules,
        "modules": records,
        "failures": failures,
        "output_files": {
            str(path.relative_to(out_dir)): {
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in output_files
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    if failures and not allow_partial:
        raise RuntimeError(f"paper integrity rerun failed: {', '.join(failures)}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path)
    parser.add_argument("--module", action="append", choices=PAPER_PUBLIC_MODULES)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.revision,
                args.out,
                snapshot_dir=args.snapshot_dir,
                modules=args.module,
                allow_partial=args.allow_partial,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
