from __future__ import annotations

import json
from pathlib import Path

import pytest

from orcap.paper_evidence import build_evidence_audit, parse_theorem_inventory


def test_parse_theorem_inventory_extracts_labels_and_lines():
    tex = """first
\\begin{proposition}[A title]
Body. \\label{prop:a}
\\end{proposition}
\\begin{corollary}[A consequence]
Body. \\label{cor:b}
\\end{corollary}
"""
    result = parse_theorem_inventory(tex)
    assert result[["tex_label", "kind", "line"]].to_dict("records") == [
        {"tex_label": "prop:a", "kind": "proposition", "line": 2},
        {"tex_label": "cor:b", "kind": "corollary", "line": 5},
    ]


def _write_fixture(root: Path, *, label: str = "prop:a") -> Path:
    (root / "paper").mkdir()
    (root / "config").mkdir()
    (root / "src").mkdir()
    (root / "docs").mkdir()
    (root / "paper/main.tex").write_text(
        "\\begin{proposition}[A]x\\label{prop:a}\\end{proposition}\n",
        encoding="utf-8",
    )
    (root / "src/analyzer.py").write_text("# fixture\n", encoding="utf-8")
    (root / "docs/ledger.md").write_text("# ledger\n", encoding="utf-8")
    registry = root / "config/registry.toml"
    registry.write_text(
        f"""[release]
schema_version = 1
paper_path = "paper/main.tex"
paper_track = "test"
authoritative_dataset = "dataset"
authoritative_revision = "revision"
evidence_freeze_utc = "2026-01-01T00:00:00Z"
status = "audit"
amendment_ledger = "docs/ledger.md"

[[claim]]
claim_id = "T1"
kind = "theorem"
tex_label = "{label}"
title = "A"
disposition = "main"
identification = "logical"
status = "proved"
source_tables = []
analyzers = ["src/analyzer.py"]
collectors = []
tests = []
validation_methods = ["proof"]
claim_boundary = "bounded"

[[gate_event]]
study_id = "H1"
effective_utc = "2026-01-01T00:00:00Z"
commit = "abc"
gate_version = "v1"
target_per_arm = 10
event = "frozen"
outcome_visibility = "masked"
classification = "original"
""",
        encoding="utf-8",
    )
    return registry


def test_build_evidence_audit_checks_and_hashes_registered_files(tmp_path):
    registry = _write_fixture(tmp_path)
    audit = build_evidence_audit(tmp_path, registry)
    assert len(audit.theorem_inventory) == 1
    assert audit.release_manifest["registered_claim_count"] == 1
    paths = {item["path"] for item in audit.release_manifest["files"]}
    assert paths == {
        "config/registry.toml",
        "docs/ledger.md",
        "paper/main.tex",
        "src/analyzer.py",
    }
    assert all(len(item["sha256"]) == 64 for item in audit.release_manifest["files"])
    json.dumps(audit.release_manifest)


def test_build_evidence_audit_rejects_theorem_registry_drift(tmp_path):
    registry = _write_fixture(tmp_path, label="prop:wrong")
    with pytest.raises(ValueError, match="theorem registry mismatch"):
        build_evidence_audit(tmp_path, registry)
