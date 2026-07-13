#!/usr/bin/env python3
"""Bundle artifact-backed curated parquet files before the nightly HF push."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from orcap.compact import bundle_curated_partitions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--min-dt", default=None)
    parser.add_argument("--bundle-name", default="buffered-part.parquet")
    args = parser.parse_args()
    print(
        json.dumps(
            bundle_curated_partitions(
                args.data_dir,
                min_dt=args.min_dt,
                bundle_name=args.bundle_name,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
