#!/usr/bin/env python3
"""Render the dated H81 missing-outcome recovery from an immutable bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from orcap.analysis.h81_release_recovery import recover_release_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        required=True,
        help="Directory containing the marker-bound H81 raw release files",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    report = recover_release_report(args.bundle_dir, args.out_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
