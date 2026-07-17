#!/usr/bin/env python3
"""Validate and materialize the paper claim, theorem, and gate registry."""

from __future__ import annotations

import argparse
from pathlib import Path

from orcap.paper_evidence import build_evidence_audit, write_evidence_audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("config/paper_evidence_registry.toml"),
    )
    parser.add_argument("--out", type=Path, default=Path("analysis"))
    args = parser.parse_args()
    root = args.root.resolve()
    registry = args.registry if args.registry.is_absolute() else root / args.registry
    out = args.out if args.out.is_absolute() else root / args.out
    audit = build_evidence_audit(root, registry)
    write_evidence_audit(audit, out)
    print(
        "validated "
        f"{len(audit.theorem_inventory)} paper theorems, "
        f"{len(audit.evidence_assignment)} registered claims, and "
        f"{len(audit.gate_genealogy)} gate events"
    )


if __name__ == "__main__":
    main()

