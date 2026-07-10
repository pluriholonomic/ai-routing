"""H54 — pre-registered direct-provider reliability-audit certificates.

This module does not infer public-router reliability.  It reports an exact
one-sided lower bound only for completed, payload-free attempts that are
explicitly linked to an immutable direct-provider audit schedule.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from ..reliability import exact_one_sided_binomial_lower_bound, meets_reliability_threshold
from . import data
from .common import DEFAULT_OUT, save, save_json

DESIGN_COLUMNS = [
    "audit_assignment_id",
    "audit_manifest_id",
    "study_id",
    "provider",
    "model_id",
    "epoch_start",
    "epoch_end",
    "design_valid",
    "design_errors",
]
PANEL_COLUMNS = [
    "audit_assignment_id",
    "audit_manifest_id",
    "study_id",
    "provider",
    "model_id",
    "randomization_stratum",
    "attempts_linked",
    "direct_attempts_valid",
    "completed_attempts",
    "succeeded_attempts",
    "unsucceeded_completed_attempts",
    "unknown_outcome_attempts",
    "attempt_design_mismatch_count",
]
CERTIFICATE_COLUMNS = [
    "audit_manifest_id",
    "study_id",
    "provider",
    "model_id",
    "valid_assignment_rows",
    "invalid_assignment_rows",
    "linked_attempts",
    "completed_attempts",
    "succeeded_attempts",
    "unsucceeded_completed_attempts",
    "unknown_outcome_attempts",
    "attempt_design_mismatch_count",
    "observed_success_rate",
    "confidence_level",
    "one_sided_lower_reliability_bound",
    "minimum_attempts_per_provider_model",
    "minimum_reliability_lower_bound",
    "certification_status",
]
_COMPLETED = {"succeeded", "failed", "cancelled"}


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _load(table: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select * from read_parquet('{data.table_glob(table)}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def _latest(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    if frame.empty or key not in frame:
        return frame.copy()
    sort = [key] + (["run_ts"] if "run_ts" in frame else [])
    return frame.sort_values(sort).drop_duplicates(key, keep="last").copy()


def _latest_attempts(frame: pd.DataFrame) -> pd.DataFrame:
    """Respect the telemetry contract's source/event composite identity."""
    if frame.empty or "event_id" not in frame:
        return frame.copy()
    if "source" not in frame:
        return _latest(frame, "event_id")
    keyed = frame.copy()
    keyed["_source_event_id"] = (
        keyed["source"].fillna("").astype(str) + "\x1f" + keyed["event_id"].astype(str)
    )
    return _latest(keyed, "_source_event_id").drop(columns="_source_event_id")


def _timestamp(value) -> pd.Timestamp:
    return pd.to_datetime(value, utc=True, errors="coerce")


def design_audit(manifests: pd.DataFrame, assignments: pd.DataFrame) -> pd.DataFrame:
    """Verify pre-registration, schedule window, and provider/model overlap."""
    if assignments.empty:
        return _empty(DESIGN_COLUMNS)
    manifests = _latest(manifests, "audit_manifest_id")
    manifest_lookup = {
        str(row.audit_manifest_id): row
        for row in manifests.itertuples(index=False)
        if getattr(row, "audit_manifest_id", None)
    }
    rows = []
    for assignment in _latest(assignments, "audit_assignment_id").itertuples(index=False):
        errors: list[str] = []
        manifest_id = str(getattr(assignment, "audit_manifest_id", ""))
        manifest = manifest_lookup.get(manifest_id)
        start = _timestamp(getattr(assignment, "epoch_start", None))
        end = _timestamp(getattr(assignment, "epoch_end", None))
        assigned_at = _timestamp(getattr(assignment, "assigned_at", None))
        if pd.isna(start) or pd.isna(end) or pd.isna(assigned_at):
            errors.append("invalid_timestamp")
        elif start >= end:
            errors.append("nonpositive_epoch")
        elif assigned_at > start:
            errors.append("assigned_after_epoch_start")
        if manifest is None:
            errors.append("unknown_manifest")
        else:
            if str(getattr(assignment, "study_id", "")) != str(manifest.study_id):
                errors.append("study_id_mismatch")
            registered_at = _timestamp(manifest.registered_at)
            planned_start = _timestamp(manifest.planned_start_at)
            planned_end = _timestamp(manifest.planned_end_at)
            if not pd.isna(assigned_at) and assigned_at < registered_at:
                errors.append("assignment_before_manifest_registration")
            if not pd.isna(start) and not pd.isna(end) and (
                start < planned_start or end > planned_end
            ):
                errors.append("epoch_outside_registered_window")
        rows.append(
            {
                "audit_assignment_id": getattr(assignment, "audit_assignment_id", None),
                "audit_manifest_id": manifest_id,
                "study_id": getattr(assignment, "study_id", None),
                "provider": getattr(assignment, "provider", None),
                "model_id": getattr(assignment, "model_id", None),
                "epoch_start": getattr(assignment, "epoch_start", None),
                "epoch_end": getattr(assignment, "epoch_end", None),
                "design_valid": not errors,
                "design_errors": ";".join(errors),
            }
        )
    audit = pd.DataFrame(rows, columns=DESIGN_COLUMNS)
    valid = audit.loc[audit["design_valid"]].copy()
    if valid.empty:
        return audit
    valid["_start"] = pd.to_datetime(valid["epoch_start"], utc=True)
    valid["_end"] = pd.to_datetime(valid["epoch_end"], utc=True)
    overlaps: set[str] = set()
    for _, group in valid.groupby(
        ["audit_manifest_id", "study_id", "provider", "model_id"], dropna=False
    ):
        prior_end = None
        prior_id = None
        for assignment_id, start, end in group.sort_values(["_start", "_end"])[
            ["audit_assignment_id", "_start", "_end"]
        ].itertuples(index=False, name=None):
            if prior_end is not None and start < prior_end:
                overlaps.update({str(prior_id), str(assignment_id)})
            if prior_end is None or end > prior_end:
                prior_end, prior_id = end, assignment_id
    if overlaps:
        matches = audit["audit_assignment_id"].astype(str).isin(overlaps)
        audit.loc[matches, "design_valid"] = False
        audit.loc[matches, "design_errors"] = audit.loc[matches, "design_errors"].map(
            lambda value: ";".join(part for part in [value, "overlapping_assignment"] if part)
        )
    return audit


def _attempt_audit(
    assignments: pd.DataFrame, attempts: pd.DataFrame, design: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match only explicitly linked direct-provider attempts to audit epochs."""
    if assignments.empty:
        return _empty(PANEL_COLUMNS), _empty(
            ["audit_assignment_id", "event_id", "attempt_valid", "attempt_design_errors"]
        )
    assignments = _latest(assignments, "audit_assignment_id")
    assignment_lookup = {
        str(row.audit_assignment_id): row
        for row in assignments.itertuples(index=False)
        if getattr(row, "audit_assignment_id", None)
    }
    attempts = _latest_attempts(attempts)
    linked: dict[str, list[dict]] = {assignment_id: [] for assignment_id in assignment_lookup}
    attempt_rows = []
    if not attempts.empty and "reliability_audit_assignment_id" in attempts:
        for attempt in attempts.itertuples(index=False):
            assignment_id = str(getattr(attempt, "reliability_audit_assignment_id", "") or "")
            if assignment_id not in assignment_lookup:
                continue
            assignment = assignment_lookup[assignment_id]
            errors: list[str] = []
            observed_at = _timestamp(getattr(attempt, "observed_at", None))
            start = _timestamp(assignment.epoch_start)
            end = _timestamp(assignment.epoch_end)
            if pd.isna(observed_at) or observed_at < start or observed_at >= end:
                errors.append("attempt_outside_assigned_epoch")
            if str(getattr(attempt, "study_id", "")) != str(assignment.study_id):
                errors.append("attempt_study_id_mismatch")
            if str(getattr(attempt, "model_id", "")) != str(assignment.model_id):
                errors.append("attempt_model_id_mismatch")
            provider = str(assignment.provider)
            if str(getattr(attempt, "requested_provider", "") or "") != provider:
                errors.append("attempt_not_directly_requested")
            if str(getattr(attempt, "selected_provider", "") or "") != provider:
                errors.append("attempt_selected_provider_mismatch")
            row = {
                "audit_assignment_id": assignment_id,
                "event_id": getattr(attempt, "event_id", None),
                "attempt_valid": not errors,
                "attempt_design_errors": ";".join(errors),
                "outcome": str(getattr(attempt, "outcome", "unknown") or "unknown"),
            }
            linked[assignment_id].append(row)
            attempt_rows.append(row)
    rows = []
    for assignment in assignments.itertuples(index=False):
        assignment_id = str(assignment.audit_assignment_id)
        matches = linked.get(assignment_id, [])
        valid = [row for row in matches if row["attempt_valid"]]
        completed = [row for row in valid if row["outcome"] in _COMPLETED]
        succeeded = sum(row["outcome"] == "succeeded" for row in completed)
        rows.append(
            {
                "audit_assignment_id": assignment_id,
                "audit_manifest_id": assignment.audit_manifest_id,
                "study_id": assignment.study_id,
                "provider": assignment.provider,
                "model_id": assignment.model_id,
                "randomization_stratum": assignment.randomization_stratum,
                "attempts_linked": len(matches),
                "direct_attempts_valid": len(valid),
                "completed_attempts": len(completed),
                "succeeded_attempts": succeeded,
                "unsucceeded_completed_attempts": len(completed) - succeeded,
                "unknown_outcome_attempts": sum(
                    row["outcome"] not in _COMPLETED for row in valid
                ),
                "attempt_design_mismatch_count": sum(
                    not row["attempt_valid"] for row in matches
                ),
            }
        )
    return pd.DataFrame(rows, columns=PANEL_COLUMNS), pd.DataFrame(attempt_rows)


def certificates(
    manifests: pd.DataFrame, design: pd.DataFrame, panel: pd.DataFrame
) -> pd.DataFrame:
    """Aggregate eligible audit epochs into lower-bound eligibility certificates."""
    if manifests.empty or design.empty:
        return _empty(CERTIFICATE_COLUMNS)
    rows = []
    manifests = _latest(manifests, "audit_manifest_id")
    assignments = design.loc[
        :,
        [
            "audit_assignment_id",
            "audit_manifest_id",
            "study_id",
            "provider",
            "model_id",
            "design_valid",
        ],
    ]
    for manifest in manifests.itertuples(index=False):
        manifest_assignments = assignments[
            assignments["audit_manifest_id"].astype(str) == str(manifest.audit_manifest_id)
        ]
        for (provider, model_id), group in manifest_assignments.groupby(
            ["provider", "model_id"], dropna=False
        ):
            assignment_ids = set(group["audit_assignment_id"].astype(str))
            outcomes = panel[panel["audit_assignment_id"].astype(str).isin(assignment_ids)]
            completed = int(outcomes["completed_attempts"].sum()) if not outcomes.empty else 0
            successes = int(outcomes["succeeded_attempts"].sum()) if not outcomes.empty else 0
            unknown = int(outcomes["unknown_outcome_attempts"].sum()) if not outcomes.empty else 0
            mismatches = (
                int(outcomes["attempt_design_mismatch_count"].sum()) if not outcomes.empty else 0
            )
            lower = (
                exact_one_sided_binomial_lower_bound(
                    successes, completed, confidence_level=float(manifest.confidence_level)
                )
                if completed
                else None
            )
            invalid_assignments = int((~group["design_valid"]).sum())
            if invalid_assignments or mismatches:
                status = "invalid_design"
            elif unknown:
                status = "incomplete_outcomes"
            elif completed < int(manifest.minimum_attempts_per_provider_model):
                status = "power_gated"
            elif not meets_reliability_threshold(
                lower, minimum_reliability=float(manifest.minimum_reliability_lower_bound)
            ):
                status = "reliability_not_certified"
            else:
                status = "reliability_certified"
            rows.append(
                {
                    "audit_manifest_id": manifest.audit_manifest_id,
                    "study_id": manifest.study_id,
                    "provider": provider,
                    "model_id": model_id,
                    "valid_assignment_rows": int(group["design_valid"].sum()),
                    "invalid_assignment_rows": invalid_assignments,
                    "linked_attempts": (
                        int(outcomes["attempts_linked"].sum()) if not outcomes.empty else 0
                    ),
                    "completed_attempts": completed,
                    "succeeded_attempts": successes,
                    "unsucceeded_completed_attempts": completed - successes,
                    "unknown_outcome_attempts": unknown,
                    "attempt_design_mismatch_count": mismatches,
                    "observed_success_rate": successes / completed if completed else None,
                    "confidence_level": float(manifest.confidence_level),
                    "one_sided_lower_reliability_bound": lower,
                    "minimum_attempts_per_provider_model": int(
                        manifest.minimum_attempts_per_provider_model
                    ),
                    "minimum_reliability_lower_bound": float(
                        manifest.minimum_reliability_lower_bound
                    ),
                    "certification_status": status,
                }
            )
    return pd.DataFrame(rows, columns=CERTIFICATE_COLUMNS)


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    manifests = _load("router_reliability_audit_manifests")
    assignments = _load("router_reliability_audit_assignments")
    attempts = _load("router_route_attempts")
    design = design_audit(manifests, assignments)
    panel, attempt_audit = _attempt_audit(assignments, attempts, design)
    certificate_rows = certificates(manifests, design, panel)
    save(design, out_dir, "h54_reliability_audit_design_audit")
    save(panel, out_dir, "h54_reliability_audit_panel")
    save(attempt_audit, out_dir, "h54_reliability_audit_attempt_audit")
    save(certificate_rows, out_dir, "h54_reliability_certificates")
    status_counts = Counter(certificate_rows.get("certification_status", pd.Series(dtype=str)))
    summary = {
        "audit_manifest_count": int(len(_latest(manifests, "audit_manifest_id"))),
        "audit_assignment_count": int(len(_latest(assignments, "audit_assignment_id"))),
        "certificate_count": int(len(certificate_rows)),
        "certification_status_counts": dict(sorted(status_counts.items())),
        "claim_boundary": (
            "H54 certifies only an exact one-sided lower success-probability bound for a "
            "pre-registered provider/model direct-audit population, conditional on independent "
            "completed attempts, the disclosed sampling schedule, and complete redacted outcome "
            "logging. It does not establish platform-wide reliability, exogenous provider "
            "selection, truthful reliability reports, correlated-outage risk, or welfare."
        ),
        "required_design": [
            "immutable manifest and provider/model/epoch schedule before audit outcomes",
            "later auditor verification of the disclosed random seed against its commitment",
            "requested_provider and selected_provider both equal the pre-assigned provider",
            "all linked direct-attempt outcomes retained, including failures and cancellations",
        ],
    }
    save_json(summary, out_dir, "h54_summary")
    return summary
