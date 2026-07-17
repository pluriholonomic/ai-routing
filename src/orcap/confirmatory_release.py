"""One-shot, immutable release runner for the focal randomized studies.

The runner performs an assignment-only gate check against one pinned dataset
revision.  It cannot read outcome columns before the frozen gate opens.  Once a
gate is open, it writes and remotely commits a first-access marker *before* the
study analyzer may query outcomes, then publishes a content-addressed bundle.

An orphaned first-access marker is fail-closed: a later invocation refuses to
query outcomes again and requires manual forensic recovery from the original
workflow artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from huggingface_hub import HfApi

from .analysis import data
from .analysis import h81_delegation_decomposition as h81
from .analysis import h95_delegation_replication as h95
from .config import HF_DATASET_REPO

ROOT = Path(__file__).resolve().parents[2]
RELEASE_PROTOCOL_VERSION = "confirmatory-release-v1"
ASSIGNMENT_COLUMNS = (
    "source, event_id, run_ts, observed_at, study_id, model_id, policy, metadata_json"
)
H81_PLAN_COLUMNS = (
    "plan_id, planned_at, run_id, run_ts, study_id, ranking_position, "
    "evaluation_order, model_id, block_id, block_seed, first_policy_planned, "
    "assignment_probability_first, randomized_order"
)
H81_ELIGIBILITY_ASSIGNMENT_COLUMNS = (
    "run_id, run_seed, run_ts, observed_at, study_id, ranking_position, "
    "evaluation_order, model_id, eligible, block_id"
)


@dataclass(frozen=True)
class StudySpec:
    key: str
    study_id: str
    release_path: str
    preregistration: str
    analyzer_path: str
    gate: Callable[[], dict[str, Any]]
    runner: Callable[..., dict[str, Any]]
    supporting_paths: tuple[str, ...] = ()


def _empty_assignment_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "source",
            "event_id",
            "run_ts",
            "observed_at",
            "study_id",
            "model_id",
            "policy",
            "metadata_json",
        ]
    )


def h81_gate_status() -> dict[str, Any]:
    """Read only H81 assignment metadata and evaluate the frozen 40/arm gate."""
    try:
        assignment = data.q(
            f"""
            select {ASSIGNMENT_COLUMNS}
            from read_parquet(
              '{data.table_glob("router_route_attempts")}', union_by_name=true
            ) where study_id = '{h81.STUDY_ID}'
            """
        ).df()
    except Exception:
        assignment = _empty_assignment_frame()
    try:
        plans = data.q(
            f"""
            select {H81_PLAN_COLUMNS}
            from read_parquet(
              '{data.table_glob("router_decomposition_plans")}', union_by_name=true
            ) where study_id = '{h81.STUDY_ID}'
            """
        ).df()
    except Exception:
        plans = pd.DataFrame()
    try:
        eligibility = data.q(
            f"""
            select {H81_ELIGIBILITY_ASSIGNMENT_COLUMNS}
            from read_parquet(
              '{data.table_glob("router_probe_eligibility")}', union_by_name=true
            ) where study_id = '{h81.STUDY_ID}'
            """
        ).df()
    except Exception:
        eligibility = pd.DataFrame()
    assignment_plans, plan_audit = h81.combined_assignment_plans(plans, eligibility)
    first, audit = h81.first_position_sample(assignment, plans=assignment_plans)
    audit["assignment_plan_sources"] = plan_audit
    prefix, ready, cutoff = h81.first_balanced_prefix(
        first, h81.POLICIES, h81.MIN_FIRST_POSITION_PER_POLICY
    )
    balance_ready = bool(ready)
    integrity_pass = h81.assignment_integrity_pass(audit)
    ready = bool(balance_ready and integrity_pass)
    counts = (
        first["policy"].value_counts().reindex(h81.POLICIES, fill_value=0)
        if len(first)
        else pd.Series(0, index=h81.POLICIES, dtype=int)
    )
    return {
        "study_id": h81.STUDY_ID,
        "release_ready": bool(ready),
        "balance_gate_ready": balance_ready,
        "assignment_integrity_pass": integrity_pass,
        "outcomes_queried": False,
        "target_per_policy": h81.MIN_FIRST_POSITION_PER_POLICY,
        "first_position_counts": {key: int(value) for key, value in counts.items()},
        "remaining_by_policy": {
            key: max(0, h81.MIN_FIRST_POSITION_PER_POLICY - int(value))
            for key, value in counts.items()
        },
        "intended_first_position_blocks": int(len(first)),
        "verified_first_position_blocks": int(audit.get("verified_first_position_blocks", 0)),
        "release_gate_prefix_blocks": int(len(prefix)) if ready else 0,
        "confirmatory_cutoff": cutoff,
        "assignment_plan_coverage": audit.get("assignment_plan_coverage"),
        "assignment_plan_replay_rate": audit.get("assignment_plan_replay_rate"),
        "assignment_plan_sources": audit.get("assignment_plan_sources"),
        "assignment_reconstruction_rate": audit.get("assignment_reconstruction_rate"),
        "assignment_replay_rate": audit.get("assignment_replay_rate"),
        "first_row_observation_rate": audit.get("first_row_observation_rate"),
        "treatment_metadata_pass_rate": audit.get("treatment_metadata_pass_rate"),
        "outcome_access": (
            "permitted_after_remote_first_access_marker"
            if ready
            else "not_queried_by_40_per_arm_gate"
        ),
    }


def h95_gate_status() -> dict[str, Any]:
    """Read only H95 plans and assignment metadata at its fixed horizon."""
    try:
        eligibility = data.q(
            f"""
            select * from read_parquet(
              '{data.table_glob("router_replication_eligibility")}',
              union_by_name=true
            ) where study_id = '{h95.STUDY_ID}'
            """
        ).df()
    except Exception:
        eligibility = pd.DataFrame()
    try:
        assignment = data.q(
            f"""
            select {ASSIGNMENT_COLUMNS}
            from read_parquet(
              '{data.table_glob("router_route_attempts")}', union_by_name=true
            ) where study_id = '{h95.STUDY_ID}'
            """
        ).df()
    except Exception:
        assignment = _empty_assignment_frame()
    prepared = h95.prepare_assignment_attempts(assignment)
    summary, _, _, _ = h95.gate_summary(prepared, eligibility, simulations=0)
    summary = dict(summary)
    # ``gate_summary`` describes what the analyzer will release at the horizon;
    # this preflight has intentionally not touched an outcome column.
    summary["outcomes_released"] = False
    summary["outcomes_queried"] = False
    summary["outcome_access"] = (
        "permitted_after_remote_first_access_marker"
        if summary["release_ready"]
        else "not_queried_by_fixed_horizon_gate"
    )
    return summary


STUDIES: dict[str, StudySpec] = {
    "h81": StudySpec(
        key="h81",
        study_id=h81.STUDY_ID,
        release_path="releases/h81-confirmatory-v1",
        preregistration="experiments/h81-delegation-decomposition-v1/preregistration.md",
        analyzer_path="src/orcap/analysis/h81_delegation_decomposition.py",
        gate=h81_gate_status,
        runner=h81.run,
        supporting_paths=("src/orcap/analysis/h81_release_report.py",),
    ),
    "h95": StudySpec(
        key="h95",
        study_id=h95.STUDY_ID,
        release_path="releases/h95-confirmatory-v1",
        preregistration="experiments/h95-delegation-replication-v1/preregistration.md",
        analyzer_path="src/orcap/analysis/h95_delegation_replication.py",
        gate=h95_gate_status,
        runner=h95.run,
    ),
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _code_commit() -> str:
    if value := os.environ.get("GITHUB_SHA", "").strip():
        return value
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _code_hashes(spec: StudySpec) -> dict[str, str]:
    paths = [
        "uv.lock",
        "pyproject.toml",
        "src/orcap/confirmatory_release.py",
        spec.analyzer_path,
        spec.preregistration,
    ]
    paths.extend(spec.supporting_paths)
    protocol_dir = (ROOT / spec.preregistration).parent
    paths.extend(
        path.relative_to(ROOT).as_posix() for path in sorted(protocol_dir.glob("amendment-*.md"))
    )
    return {path: _sha256(ROOT / path) for path in paths}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _commit_id(value: Any) -> str | None:
    for field in ("oid", "commit_id"):
        result = getattr(value, field, None)
        if result:
            return str(result)
    return None


def _bundle_files(bundle_dir: Path) -> list[dict[str, Any]]:
    files = []
    for path in sorted(bundle_dir.rglob("*")):
        if path.is_file() and path.name != "release_manifest.json":
            files.append(
                {
                    "path": path.relative_to(bundle_dir).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    return files


def release_study(
    key: str,
    *,
    output_root: Path,
    publish: bool,
    api: HfApi | Any | None = None,
) -> dict[str, Any]:
    """Check one gate and, if open, publish exactly one immutable release."""
    spec = STUDIES[key]
    bundle_dir = output_root / key
    bundle_dir.mkdir(parents=True, exist_ok=True)
    client = api
    if publish and client is None:
        token = os.environ.get("HF_TOKEN")
        if not token:
            raise RuntimeError("HF_TOKEN is required for a published release")
        client = HfApi(token=token)

    with data.pinned_analysis_source() as source:
        gate = spec.gate()
        preflight = {
            "protocol_version": RELEASE_PROTOCOL_VERSION,
            "checked_at_utc": _utc_now(),
            "code_commit": _code_commit(),
            "dataset": source,
            "study": spec.key,
            "study_id": spec.study_id,
            "gate": gate,
        }
        _write_json(bundle_dir / "assignment_only_gate.json", preflight)
        if not gate.get("release_ready"):
            return {
                "study": key,
                "status": "accruing",
                "release_ready": False,
                "dataset_revision": source.get("revision"),
                "gate": gate,
            }

        if not publish:
            return {
                "study": key,
                "status": "ready_requires_published_first_access",
                "release_ready": True,
                "dataset_revision": source.get("revision"),
                "gate": gate,
                "outcome_access": "not_queried_without_remote_first_access_marker",
            }

        manifest_remote = f"{spec.release_path}/release_manifest.json"
        marker_remote = f"{spec.release_path}/first_outcome_access.json"
        if publish and client.file_exists(HF_DATASET_REPO, manifest_remote, repo_type="dataset"):
            return {
                "study": key,
                "status": "already_released",
                "release_ready": True,
                "dataset_revision": source.get("revision"),
                "remote_manifest": manifest_remote,
            }
        if publish and client.file_exists(HF_DATASET_REPO, marker_remote, repo_type="dataset"):
            raise RuntimeError(
                f"{key} first-outcome marker exists without a release manifest; "
                "refusing a second outcome access"
            )

        access = {
            **preflight,
            "first_outcome_access_utc": _utc_now(),
            "transition": "assignment_only_gate_passed_to_outcome_query_permitted",
            "outcome_fields_before_marker": "not_queried",
            "environment_lock_sha256": _sha256(ROOT / "uv.lock"),
            "code_hashes": _code_hashes(spec),
        }
        marker_path = bundle_dir / "first_outcome_access.json"
        _write_json(marker_path, access)
        marker_commit = None
        if publish:
            marker_info = client.upload_file(
                path_or_fileobj=marker_path,
                path_in_repo=marker_remote,
                repo_id=HF_DATASET_REPO,
                repo_type="dataset",
                commit_message=f"{key} record first confirmatory outcome access",
            )
            marker_commit = _commit_id(marker_info)

        # This is the first code path allowed to issue a full outcome query.
        summary = spec.runner(out_dir=bundle_dir)
        if not summary.get("outcomes_released"):
            raise RuntimeError(f"{key} analyzer did not confirm outcome release")

        manifest = {
            "protocol_version": RELEASE_PROTOCOL_VERSION,
            "released_at_utc": _utc_now(),
            "study": key,
            "study_id": spec.study_id,
            "code_commit": preflight["code_commit"],
            "dataset": source,
            "first_outcome_access_utc": access["first_outcome_access_utc"],
            "first_access_marker_commit": marker_commit,
            "environment_lock_sha256": access["environment_lock_sha256"],
            "code_hashes": access["code_hashes"],
            "gate": gate,
            "analysis_summary": summary,
            "files": _bundle_files(bundle_dir),
            "claim_boundary": (
                "This bundle releases the frozen owned-account estimand only. "
                "It does not identify market-wide routing, provider intent, or welfare."
            ),
        }
        manifest_path = bundle_dir / "release_manifest.json"
        _write_json(manifest_path, manifest)
        release_commit = None
        if publish:
            release_info = client.upload_folder(
                repo_id=HF_DATASET_REPO,
                repo_type="dataset",
                folder_path=bundle_dir,
                path_in_repo=spec.release_path,
                commit_message=f"{key} publish frozen confirmatory release",
            )
            release_commit = _commit_id(release_info)
        return {
            "study": key,
            "status": "released",
            "release_ready": True,
            "dataset_revision": source.get("revision"),
            "first_access_marker_commit": marker_commit,
            "release_commit": release_commit,
            "remote_manifest": manifest_remote if publish else None,
            "local_manifest": str(manifest_path),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", choices=["h81", "h95", "all"], default="all")
    parser.add_argument("--output-dir", type=Path, default=Path("confirmatory-release"))
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    keys = list(STUDIES) if args.study == "all" else [args.study]
    results = [
        release_study(
            key,
            output_root=args.output_dir,
            publish=args.publish,
        )
        for key in keys
    ]
    _write_json(args.output_dir / "release_status.json", {"studies": results})
    print(json.dumps({"studies": results}, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
