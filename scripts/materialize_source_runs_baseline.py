#!/usr/bin/env python3
"""Publish one verified baseline for the high-cardinality legacy source ledger."""

import argparse
import json
import os
from pathlib import Path

from huggingface_hub import HfApi

from orcap.compact import build_source_runs_baseline

DEFAULT_DATES = ("2026-07-10", "2026-07-11", "2026-07-12")
BASELINE_PATH = "curated/source_runs/dt=legacy/baseline.parquet"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="t4run/openrouter-market-history")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--date", action="append", dest="dates")
    parser.add_argument("--path-in-repo", default=BASELINE_PATH)
    parser.add_argument("--expect-source-files", type=int)
    parser.add_argument("--expect-rows", type=int)
    args = parser.parse_args()

    output = Path(".hf-baseline") / "source-runs-legacy.parquet"
    summary = build_source_runs_baseline(
        args.data_dir,
        tuple(args.dates or DEFAULT_DATES),
        output,
    )
    if args.expect_source_files is not None and summary["source_files"] != args.expect_source_files:
        raise RuntimeError(
            f"expected {args.expect_source_files} legacy files, got {summary['source_files']}"
        )
    if args.expect_rows is not None and summary["rows"] != args.expect_rows:
        raise RuntimeError(f"expected {args.expect_rows} legacy rows, got {summary['rows']}")
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.upload_file(
        path_or_fileobj=output,
        path_in_repo=args.path_in_repo,
        repo_id=args.repo,
        repo_type="dataset",
        commit_message=(
            "materialize verified legacy source-run baseline "
            f"({summary['rows']} rows from {summary['source_files']} objects)"
        ),
    )
    summary["repo_path"] = args.path_in_repo
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
