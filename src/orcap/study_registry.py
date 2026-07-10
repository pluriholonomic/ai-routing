"""Immutable, privacy-preserving registration for controlled routing studies.

The public panel cannot identify an allocation or delivery treatment effect.
This module records the design of an *owned* randomized study before the first
assigned epoch.  It deliberately stores neither prompts nor provider secrets,
and it does not send requests or alter a router configuration.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
from pyarrow.parquet import ParquetFile

from .capture_api import write_partition
from .config import CURATED_DIR, dt_partition, run_timestamp

POLICIES = {
    "capacity_certified",
    "inverse_square_price",
    "lowest_cost",
    "reliability_only",
}
OUTCOMES = {
    "attempt_success_rate",
    "capacity_shortfall_rate",
    "fallback_rate",
    "mean_cost_usd",
    "mean_latency_ms",
    "registered_value_net_cost",
}
FORBIDDEN = {
    "api_key",
    "authorization",
    "completion",
    "content",
    "input",
    "messages",
    "output",
    "prompt",
    "raw_request",
    "raw_response",
    "response",
    "secret",
    "token",
}
MANIFEST_REQUIRED = {
    "manifest_id",
    "study_id",
    "registered_at",
    "planned_start_at",
    "planned_end_at",
    "randomization_unit",
    "randomization_seed_commitment",
    "baseline_arm",
    "arms",
    "primary_outcomes",
    "negative_control_outcome",
    "min_clusters_per_arm",
    "min_attempts_per_arm",
    "stopping_rule",
}
ASSIGNMENT_REQUIRED = {
    "assignment_id",
    "manifest_id",
    "study_id",
    "model_id",
    "epoch_start",
    "epoch_end",
    "assigned_at",
    "treatment_arm",
    "randomization_stratum",
    "assignment_probability",
}
RELIABILITY_AUDIT_MANIFEST_REQUIRED = {
    "audit_manifest_id",
    "study_id",
    "registered_at",
    "planned_start_at",
    "planned_end_at",
    "randomization_unit",
    "randomization_seed_commitment",
    "routing_mode",
    "outcome_definition",
    "confidence_level",
    "minimum_attempts_per_provider_model",
    "minimum_reliability_lower_bound",
    "stopping_rule",
}
RELIABILITY_AUDIT_ASSIGNMENT_REQUIRED = {
    "audit_assignment_id",
    "audit_manifest_id",
    "study_id",
    "provider",
    "model_id",
    "epoch_start",
    "epoch_end",
    "assigned_at",
    "randomization_stratum",
    "assignment_probability",
}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _forbidden_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = set(value).intersection(FORBIDDEN)
        for nested in value.values():
            found |= _forbidden_keys(nested)
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for nested in value:
            found |= _forbidden_keys(nested)
        return found
    return set()


def _missing(record: dict[str, Any], required: set[str]) -> list[str]:
    return sorted(
        key for key in required if key not in record or record[key] is None or record[key] == ""
    )


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _positive_int(value: Any, field: str, minimum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if number < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return number


def _probability(value: Any, field: str) -> float:
    try:
        probability = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not 0 < probability <= 1:
        raise ValueError(f"{field} must lie in (0, 1]")
    return probability


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{field} must be a stable non-payload identifier")
    return value


def _model_id(value: Any) -> str:
    """Accept canonical model keys without allowing multiline free text."""
    if not isinstance(value, str) or not value.strip() or len(value) > 256 or "\n" in value:
        raise ValueError("model_id must be a non-empty canonical model identifier")
    return value.strip()


def _existing_ids(table: str, key: str, curated_dir: Path) -> set[str]:
    """Read immutable IDs without treating a later partition as an update."""
    result: set[str] = set()
    for path in (curated_dir / table).glob("dt=*/*.parquet"):
        try:
            result.update(
                str(value)
                for value in ParquetFile(path).read(columns=[key]).column(key).to_pylist()
                if value is not None
            )
        except (OSError, KeyError, pa.ArrowInvalid):
            continue
    return result


def _arms(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) < 2:
        raise ValueError("arms must list at least two randomized policies")
    normalized = []
    for arm in value:
        if not isinstance(arm, dict):
            raise ValueError("each arm must be an object")
        name = _id(arm.get("name"), "arm.name")
        policy = arm.get("policy")
        if policy not in POLICIES:
            raise ValueError(f"arm {name} uses unsupported policy {policy!r}")
        normalized.append(
            {
                "name": name,
                "policy": policy,
                "assignment_probability": _probability(
                    arm.get("assignment_probability"), f"arm {name} assignment_probability"
                ),
            }
        )
    names = [arm["name"] for arm in normalized]
    if len(names) != len(set(names)):
        raise ValueError("arm names must be unique")
    if abs(sum(arm["assignment_probability"] for arm in normalized) - 1.0) > 1e-9:
        raise ValueError("arm assignment probabilities must sum to one")
    return normalized


def validate_manifest(record: dict[str, Any]) -> dict[str, Any]:
    """Validate a pre-outcome protocol for a model-epoch randomized trial."""
    if not isinstance(record, dict):
        raise ValueError("study manifest must be an object")
    missing = _missing(record, MANIFEST_REQUIRED)
    if missing:
        raise ValueError(f"study manifest missing required fields: {', '.join(missing)}")
    forbidden = sorted(_forbidden_keys(record))
    if forbidden:
        raise ValueError(
            "study manifest contains forbidden payload fields: " + ", ".join(forbidden)
        )
    registered_at = _timestamp(record["registered_at"], "registered_at")
    planned_start = _timestamp(record["planned_start_at"], "planned_start_at")
    planned_end = _timestamp(record["planned_end_at"], "planned_end_at")
    if registered_at > planned_start:
        raise ValueError("registered_at must not be after planned_start_at")
    if planned_start >= planned_end:
        raise ValueError("planned_end_at must be after planned_start_at")
    if record["randomization_unit"] != "model_epoch":
        raise ValueError("randomization_unit must be model_epoch")
    seed_commitment = record["randomization_seed_commitment"]
    if not isinstance(seed_commitment, str) or not _SHA256.fullmatch(seed_commitment):
        raise ValueError("randomization_seed_commitment must be a lowercase SHA-256 commitment")
    arms = _arms(record["arms"])
    arm_names = {arm["name"] for arm in arms}
    baseline_arm = _id(record["baseline_arm"], "baseline_arm")
    if baseline_arm not in arm_names:
        raise ValueError("baseline_arm must be one of the registered arms")
    primary_outcomes = record["primary_outcomes"]
    if not isinstance(primary_outcomes, list) or not primary_outcomes:
        raise ValueError("primary_outcomes must be a non-empty list")
    if any(outcome not in OUTCOMES for outcome in primary_outcomes):
        raise ValueError("primary_outcomes contains an unsupported estimand")
    if len(primary_outcomes) != len(set(primary_outcomes)):
        raise ValueError("primary_outcomes must be unique")
    negative_control = record["negative_control_outcome"]
    if negative_control not in OUTCOMES or negative_control in primary_outcomes:
        raise ValueError("negative_control_outcome must be a distinct supported estimand")
    value_per_success = record.get("value_per_success_usd")
    if "registered_value_net_cost" in primary_outcomes:
        try:
            value_per_success = float(value_per_success)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "value_per_success_usd is required for registered_value_net_cost"
            ) from exc
        if value_per_success < 0:
            raise ValueError("value_per_success_usd must be non-negative")
    elif value_per_success is not None:
        value_per_success = float(value_per_success)
        if value_per_success < 0:
            raise ValueError("value_per_success_usd must be non-negative")
    stopping_rule = record["stopping_rule"]
    if not isinstance(stopping_rule, str) or not stopping_rule.strip():
        raise ValueError("stopping_rule must be a non-empty pre-registered description")
    return {
        "manifest_id": _id(record["manifest_id"], "manifest_id"),
        "study_id": _id(record["study_id"], "study_id"),
        "registered_at": registered_at.isoformat().replace("+00:00", "Z"),
        "planned_start_at": planned_start.isoformat().replace("+00:00", "Z"),
        "planned_end_at": planned_end.isoformat().replace("+00:00", "Z"),
        "randomization_unit": "model_epoch",
        "randomization_seed_commitment": seed_commitment,
        "baseline_arm": baseline_arm,
        "arms_json": json.dumps(arms, sort_keys=True, separators=(",", ":")),
        "primary_outcomes_json": json.dumps(primary_outcomes, separators=(",", ":")),
        "negative_control_outcome": negative_control,
        "value_per_success_usd": value_per_success,
        "min_clusters_per_arm": _positive_int(
            record["min_clusters_per_arm"], "min_clusters_per_arm", 20
        ),
        "min_attempts_per_arm": _positive_int(
            record["min_attempts_per_arm"], "min_attempts_per_arm", 100
        ),
        "stopping_rule": stopping_rule.strip(),
        "metadata_json": json.dumps(
            record.get("metadata") or {}, sort_keys=True, separators=(",", ":")
        ),
        "payload_retained": False,
    }


def validate_assignment(record: dict[str, Any]) -> dict[str, Any]:
    """Validate one pre-assigned model-epoch treatment without payload data."""
    if not isinstance(record, dict):
        raise ValueError("study assignment must be an object")
    missing = _missing(record, ASSIGNMENT_REQUIRED)
    if missing:
        raise ValueError(f"study assignment missing required fields: {', '.join(missing)}")
    forbidden = sorted(_forbidden_keys(record))
    if forbidden:
        raise ValueError(
            "study assignment contains forbidden payload fields: " + ", ".join(forbidden)
        )
    epoch_start = _timestamp(record["epoch_start"], "epoch_start")
    epoch_end = _timestamp(record["epoch_end"], "epoch_end")
    assigned_at = _timestamp(record["assigned_at"], "assigned_at")
    if epoch_start >= epoch_end:
        raise ValueError("epoch_end must be after epoch_start")
    if assigned_at > epoch_start:
        raise ValueError("assigned_at must not be after epoch_start")
    return {
        "assignment_id": _id(record["assignment_id"], "assignment_id"),
        "manifest_id": _id(record["manifest_id"], "manifest_id"),
        "study_id": _id(record["study_id"], "study_id"),
        "model_id": _model_id(record["model_id"]),
        "epoch_start": epoch_start.isoformat().replace("+00:00", "Z"),
        "epoch_end": epoch_end.isoformat().replace("+00:00", "Z"),
        "assigned_at": assigned_at.isoformat().replace("+00:00", "Z"),
        "treatment_arm": _id(record["treatment_arm"], "treatment_arm"),
        "randomization_stratum": _id(record["randomization_stratum"], "randomization_stratum"),
        "assignment_probability": _probability(
            record["assignment_probability"], "assignment_probability"
        ),
        "metadata_json": json.dumps(
            record.get("metadata") or {}, sort_keys=True, separators=(",", ":")
        ),
        "payload_retained": False,
    }


def _reliability_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence_level must be numeric") from exc
    if not 0.5 < confidence < 1:
        raise ValueError("confidence_level must lie in (0.5, 1)")
    return confidence


def _reliability_threshold(value: Any) -> float:
    try:
        threshold = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("minimum_reliability_lower_bound must be numeric") from exc
    if not 0 <= threshold < 1:
        raise ValueError("minimum_reliability_lower_bound must lie in [0, 1)")
    return threshold


def validate_reliability_audit_manifest(record: dict[str, Any]) -> dict[str, Any]:
    """Validate a pre-outcome, direct-provider reliability-audit protocol.

    The schedule samples provider/model epochs before outcomes occur.  The
    registry does not send traffic or prove that a private seed was random; an
    auditor must later verify the disclosed seed against its commitment.
    """
    if not isinstance(record, dict):
        raise ValueError("reliability audit manifest must be an object")
    missing = _missing(record, RELIABILITY_AUDIT_MANIFEST_REQUIRED)
    if missing:
        raise ValueError(
            "reliability audit manifest missing required fields: " + ", ".join(missing)
        )
    forbidden = sorted(_forbidden_keys(record))
    if forbidden:
        raise ValueError(
            "reliability audit manifest contains forbidden payload fields: " + ", ".join(forbidden)
        )
    registered_at = _timestamp(record["registered_at"], "registered_at")
    planned_start = _timestamp(record["planned_start_at"], "planned_start_at")
    planned_end = _timestamp(record["planned_end_at"], "planned_end_at")
    if registered_at > planned_start:
        raise ValueError("registered_at must not be after planned_start_at")
    if planned_start >= planned_end:
        raise ValueError("planned_end_at must be after planned_start_at")
    if record["randomization_unit"] != "provider_model_epoch":
        raise ValueError("randomization_unit must be provider_model_epoch")
    if record["routing_mode"] != "direct_provider":
        raise ValueError("routing_mode must be direct_provider")
    if record["outcome_definition"] != "completed_attempt_success":
        raise ValueError("outcome_definition must be completed_attempt_success")
    seed_commitment = record["randomization_seed_commitment"]
    if not isinstance(seed_commitment, str) or not _SHA256.fullmatch(seed_commitment):
        raise ValueError("randomization_seed_commitment must be a lowercase SHA-256 commitment")
    stopping_rule = record["stopping_rule"]
    if not isinstance(stopping_rule, str) or not stopping_rule.strip():
        raise ValueError("stopping_rule must be a non-empty pre-registered description")
    return {
        "audit_manifest_id": _id(record["audit_manifest_id"], "audit_manifest_id"),
        "study_id": _id(record["study_id"], "study_id"),
        "registered_at": registered_at.isoformat().replace("+00:00", "Z"),
        "planned_start_at": planned_start.isoformat().replace("+00:00", "Z"),
        "planned_end_at": planned_end.isoformat().replace("+00:00", "Z"),
        "randomization_unit": "provider_model_epoch",
        "randomization_seed_commitment": seed_commitment,
        "routing_mode": "direct_provider",
        "outcome_definition": "completed_attempt_success",
        "confidence_level": _reliability_confidence(record["confidence_level"]),
        "minimum_attempts_per_provider_model": _positive_int(
            record["minimum_attempts_per_provider_model"],
            "minimum_attempts_per_provider_model",
            100,
        ),
        "minimum_reliability_lower_bound": _reliability_threshold(
            record["minimum_reliability_lower_bound"]
        ),
        "stopping_rule": stopping_rule.strip(),
        "metadata_json": json.dumps(
            record.get("metadata") or {}, sort_keys=True, separators=(",", ":")
        ),
        "payload_retained": False,
    }


def validate_reliability_audit_assignment(record: dict[str, Any]) -> dict[str, Any]:
    """Validate one payload-free, pre-assigned direct-provider audit epoch."""
    if not isinstance(record, dict):
        raise ValueError("reliability audit assignment must be an object")
    missing = _missing(record, RELIABILITY_AUDIT_ASSIGNMENT_REQUIRED)
    if missing:
        raise ValueError(
            "reliability audit assignment missing required fields: " + ", ".join(missing)
        )
    forbidden = sorted(_forbidden_keys(record))
    if forbidden:
        raise ValueError(
            "reliability audit assignment contains forbidden payload fields: "
            + ", ".join(forbidden)
        )
    epoch_start = _timestamp(record["epoch_start"], "epoch_start")
    epoch_end = _timestamp(record["epoch_end"], "epoch_end")
    assigned_at = _timestamp(record["assigned_at"], "assigned_at")
    if epoch_start >= epoch_end:
        raise ValueError("epoch_end must be after epoch_start")
    if assigned_at > epoch_start:
        raise ValueError("assigned_at must not be after epoch_start")
    return {
        "audit_assignment_id": _id(record["audit_assignment_id"], "audit_assignment_id"),
        "audit_manifest_id": _id(record["audit_manifest_id"], "audit_manifest_id"),
        "study_id": _id(record["study_id"], "study_id"),
        "provider": _id(record["provider"], "provider"),
        "model_id": _model_id(record["model_id"]),
        "epoch_start": epoch_start.isoformat().replace("+00:00", "Z"),
        "epoch_end": epoch_end.isoformat().replace("+00:00", "Z"),
        "assigned_at": assigned_at.isoformat().replace("+00:00", "Z"),
        "randomization_stratum": _id(record["randomization_stratum"], "randomization_stratum"),
        "assignment_probability": _probability(
            record["assignment_probability"], "assignment_probability"
        ),
        "metadata_json": json.dumps(
            record.get("metadata") or {}, sort_keys=True, separators=(",", ":")
        ),
        "payload_retained": False,
    }


def write_manifest(record: dict[str, Any], *, curated_dir: Path = CURATED_DIR) -> Path:
    row = validate_manifest(record)
    existing = _existing_ids("router_study_manifests", "manifest_id", curated_dir)
    if row["manifest_id"] in existing:
        raise ValueError("manifest_id is already registered and immutable")
    run_ts, dt = run_timestamp(), dt_partition()
    return write_partition(
        pa.Table.from_pylist([row | {"run_ts": run_ts, "dt": dt}]),
        "router_study_manifests",
        run_ts,
        dt,
        curated_dir,
    )


def write_assignments(
    records: list[dict[str, Any]], *, curated_dir: Path = CURATED_DIR
) -> Path | None:
    if not records:
        return None
    rows = [validate_assignment(record) for record in records]
    if len({row["assignment_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate assignment_id in batch")
    existing = _existing_ids("router_study_assignments", "assignment_id", curated_dir)
    if existing.intersection(row["assignment_id"] for row in rows):
        raise ValueError("assignment_id is already registered and immutable")
    run_ts, dt = run_timestamp(), dt_partition()
    return write_partition(
        pa.Table.from_pylist([row | {"run_ts": run_ts, "dt": dt} for row in rows]),
        "router_study_assignments",
        run_ts,
        dt,
        curated_dir,
    )


def write_reliability_audit_manifest(
    record: dict[str, Any], *, curated_dir: Path = CURATED_DIR
) -> Path:
    """Persist an immutable direct-provider reliability-audit manifest."""
    row = validate_reliability_audit_manifest(record)
    existing = _existing_ids(
        "router_reliability_audit_manifests", "audit_manifest_id", curated_dir
    )
    if row["audit_manifest_id"] in existing:
        raise ValueError("audit_manifest_id is already registered and immutable")
    run_ts, dt = run_timestamp(), dt_partition()
    return write_partition(
        pa.Table.from_pylist([row | {"run_ts": run_ts, "dt": dt}]),
        "router_reliability_audit_manifests",
        run_ts,
        dt,
        curated_dir,
    )


def write_reliability_audit_assignments(
    records: list[dict[str, Any]], *, curated_dir: Path = CURATED_DIR
) -> Path | None:
    """Persist immutable provider/model/epoch audit assignments."""
    if not records:
        return None
    rows = [validate_reliability_audit_assignment(record) for record in records]
    if len({row["audit_assignment_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate audit_assignment_id in batch")
    existing = _existing_ids(
        "router_reliability_audit_assignments", "audit_assignment_id", curated_dir
    )
    if existing.intersection(row["audit_assignment_id"] for row in rows):
        raise ValueError("audit_assignment_id is already registered and immutable")
    run_ts, dt = run_timestamp(), dt_partition()
    return write_partition(
        pa.Table.from_pylist([row | {"run_ts": run_ts, "dt": dt} for row in rows]),
        "router_reliability_audit_assignments",
        run_ts,
        dt,
        curated_dir,
    )


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"study manifest at {path} is not an object")
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"assignment at {path}:{number} is not an object")
        rows.append(value)
    return rows


def register_main(path: str) -> dict[str, Any]:
    destination = write_manifest(load_json(Path(path)))
    result = {"manifest_path": str(destination)}
    print(json.dumps(result, indent=2))
    return result


def assignments_main(path: str) -> dict[str, Any]:
    records = load_jsonl(Path(path))
    destination = write_assignments(records)
    result = {
        "assignment_rows": len(records),
        "assignment_path": str(destination) if destination else None,
    }
    print(json.dumps(result, indent=2))
    return result


def register_reliability_audit_main(path: str) -> dict[str, Any]:
    destination = write_reliability_audit_manifest(load_json(Path(path)))
    result = {"audit_manifest_path": str(destination)}
    print(json.dumps(result, indent=2))
    return result


def reliability_audit_assignments_main(path: str) -> dict[str, Any]:
    records = load_jsonl(Path(path))
    destination = write_reliability_audit_assignments(records)
    result = {
        "audit_assignment_rows": len(records),
        "audit_assignment_path": str(destination) if destination else None,
    }
    print(json.dumps(result, indent=2))
    return result
