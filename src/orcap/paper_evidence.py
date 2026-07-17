"""Machine-checkable evidence governance for the inference-market paper."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ENVIRONMENT_RE = re.compile(
    r"\\begin\{(?P<kind>proposition|corollary|theorem)\}"
    r"(?:\[(?P<title>[^\]]+)\])?"
    r"(?P<body>.*?)"
    r"\\end\{(?P=kind)\}",
    re.DOTALL,
)
LABEL_RE = re.compile(r"\\label\{(?P<label>(?:prop|cor|thm):[^}]+)\}")
GRAPHICS_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{(?P<path>[^}]+)\}")
BIBLIOGRAPHY_RE = re.compile(r"\\bibliography\{(?P<paths>[^}]+)\}")


@dataclass(frozen=True)
class EvidenceAudit:
    theorem_inventory: pd.DataFrame
    evidence_assignment: pd.DataFrame
    gate_genealogy: pd.DataFrame
    release_manifest: dict[str, Any]


def load_registry(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def parse_theorem_inventory(tex: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for match in ENVIRONMENT_RE.finditer(tex):
        label_match = LABEL_RE.search(match.group("body"))
        if label_match is None:
            continue
        rows.append(
            {
                "tex_label": label_match.group("label"),
                "kind": match.group("kind"),
                "title": match.group("title") or "",
                "line": tex.count("\n", 0, match.start()) + 1,
            }
        )
    return pd.DataFrame(rows, columns=["tex_label", "kind", "title", "line"])


def _joined(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _paper_dependencies(root: Path, paper_path: Path, tex: str) -> set[str]:
    dependencies: set[Path] = set()
    for match in GRAPHICS_RE.finditer(tex):
        dependencies.add((paper_path.parent / match.group("path")).resolve())
    for match in BIBLIOGRAPHY_RE.finditer(tex):
        for item in match.group("paths").split(","):
            candidate = (paper_path.parent / item.strip()).with_suffix(".bib").resolve()
            dependencies.add(candidate)
    relative: set[str] = set()
    for path in dependencies:
        try:
            relative.add(str(path.relative_to(root)))
        except ValueError as exc:
            raise ValueError(f"paper dependency is outside repository root: {path}") from exc
    return relative


def _claim_paths(claim: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for field in ("analyzers", "collectors", "tests", "protocols"):
        paths.update(str(item) for item in claim.get(field, []))
    return paths


def build_evidence_audit(root: Path, registry_path: Path) -> EvidenceAudit:
    root = root.resolve()
    registry_path = registry_path.resolve()
    registry = load_registry(registry_path)
    release = registry["release"]
    paper_path = root / release["paper_path"]
    tex = paper_path.read_text(encoding="utf-8")
    inventory = parse_theorem_inventory(tex)
    claims = registry.get("claim", [])

    registered_labels = {str(item["tex_label"]) for item in claims if item.get("tex_label")}
    paper_labels = set(inventory["tex_label"].astype(str))
    missing = sorted(paper_labels - registered_labels)
    stale = sorted(registered_labels - paper_labels)
    if missing or stale:
        raise ValueError(
            "theorem registry mismatch: "
            f"missing_from_registry={missing}, missing_from_paper={stale}"
        )

    rows: list[dict[str, Any]] = []
    paths = {
        str(release["paper_path"]),
        str(registry_path.relative_to(root)),
        str(release["amendment_ledger"]),
        *_paper_dependencies(root, paper_path, tex),
    }
    for claim in claims:
        paths.update(_claim_paths(claim))
        rows.append(
            {
                "claim_id": claim["claim_id"],
                "kind": claim["kind"],
                "tex_label": claim.get("tex_label", ""),
                "title": claim["title"],
                "disposition": claim["disposition"],
                "identification": claim["identification"],
                "status": claim["status"],
                "source_tables": _joined(claim.get("source_tables", [])),
                "analyzers": _joined(claim.get("analyzers", [])),
                "collectors": _joined(claim.get("collectors", [])),
                "tests": _joined(claim.get("tests", [])),
                "protocols": _joined(claim.get("protocols", [])),
                "validation_methods": _joined(claim.get("validation_methods", [])),
                "claim_boundary": claim["claim_boundary"],
            }
        )
    evidence = pd.DataFrame(rows)
    if evidence["claim_id"].duplicated().any():
        duplicates = evidence.loc[evidence["claim_id"].duplicated(), "claim_id"].tolist()
        raise ValueError(f"duplicate claim ids: {duplicates}")

    gate_rows = registry.get("gate_event", [])
    gates = pd.DataFrame(gate_rows)
    if not gates.empty:
        gates["effective_utc"] = pd.to_datetime(gates["effective_utc"], utc=True)
        gates = gates.sort_values(["study_id", "effective_utc", "gate_version"]).reset_index(
            drop=True
        )

    files = []
    for relative in sorted(paths):
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"registered evidence path does not exist: {relative}")
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest = {
        "schema_version": release["schema_version"],
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "paper_track": release["paper_track"],
        "status": release["status"],
        "authoritative_dataset": release["authoritative_dataset"],
        "authoritative_revision": release["authoritative_revision"],
        "evidence_freeze_utc": release["evidence_freeze_utc"],
        "paper_theorem_count": int(len(inventory)),
        "registered_claim_count": int(len(evidence)),
        "gate_event_count": int(len(gates)),
        "files": files,
    }
    return EvidenceAudit(inventory, evidence, gates, manifest)


def write_evidence_audit(audit: EvidenceAudit, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    audit.theorem_inventory.to_parquet(out_dir / "paper_theorem_inventory.parquet", index=False)
    audit.evidence_assignment.to_parquet(
        out_dir / "paper_evidence_assignment.parquet", index=False
    )
    audit.gate_genealogy.to_parquet(out_dir / "paper_gate_genealogy.parquet", index=False)
    (out_dir / "paper_release_manifest.json").write_text(
        json.dumps(audit.release_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
