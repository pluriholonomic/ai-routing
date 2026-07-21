"""Plan-first successor routing panel for the 28-day score-memory horizon."""

from __future__ import annotations

import argparse
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from . import capture_glm52_routing as base
from .config import CURATED_DIR, run_timestamp
from .price_experiments import plan_manifest, validate_manifest

STUDY_ID = "openrouter-score-memory-routing-v1"
PLAN_VERSION = "score-memory-routing-plan-v1"


def _rewrite_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    candidates = [dict(row) for row in bundle["candidates"]]
    assignments = [dict(row) for row in bundle["assignments"]]
    summary = dict(bundle["summary"])
    block_map = {}
    for row in candidates:
        old = str(row["block_id"])
        new = f"{STUDY_ID}|{row['run_id']}|{row['model_id']}|{row['shape_id']}"
        block_map[old] = new
        row.update({"study_id": STUDY_ID, "plan_version": PLAN_VERSION, "block_id": new})
    for row in assignments:
        new_block = block_map[str(row["block_id"])]
        row.update(
            {
                "study_id": STUDY_ID,
                "plan_version": PLAN_VERSION,
                "block_id": new_block,
                "task_id": f"{new_block}|{row['policy']}|{row['replicate_index']}",
            }
        )
        row["session_group"] = f"fresh|{row['task_id']}"
    summary.update(
        {
            "study_id": STUDY_ID,
            "plan_version": PLAN_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "claim_boundary": (
                "Prospective successor owned-routing panel with the same ten policies; "
                "not market-wide flow, a proprietary score, provider cost, intent, or collusion."
            ),
        }
    )
    manifest = plan_manifest(candidates, assignments, summary)
    return {
        "format": "orcap-score-memory-routing-plan-v1",
        "candidates": candidates,
        "assignments": assignments,
        "summary": summary,
        "manifest": manifest,
    }


def build_plan_bundle(client: httpx.Client, *, run_id: str, seed: int) -> dict[str, Any]:
    return _rewrite_bundle(base.build_plan_bundle(client, run_id=run_id, seed=seed))


def write_plan_bundle(
    bundle: dict[str, Any], *, bundle_path: Path, curated_dir: Path = CURATED_DIR
) -> dict[str, str]:
    return base.write_plan_bundle(bundle, bundle_path=bundle_path, curated_dir=curated_dir)


def execute_bundle(
    bundle: dict[str, Any],
    *,
    curated_dir: Path = CURATED_DIR,
    data_root: Path | None = None,
    now: datetime | None = None,
    send: Any = base._send_assignment,
) -> dict[str, Any]:
    return base.execute_bundle(
        bundle,
        curated_dir=curated_dir,
        data_root=data_root,
        now=now,
        send=send,
        study_id=STUDY_ID,
        enabled_env="ORCAP_SCORE_MEMORY_ROUTING_ENABLED",
        start_env="ORCAP_SCORE_MEMORY_ROUTING_START_UTC",
        end_env="ORCAP_SCORE_MEMORY_ROUTING_END_UTC",
        budget_env_prefix="ORCAP_SCORE_MEMORY_ROUTING",
        campaign_label="score-memory successor",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--bundle", type=Path, default=Path("score-memory-routing-plan.json"))
    plan.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    execute = commands.add_parser("execute")
    execute.add_argument("--bundle", type=Path, required=True)
    execute.add_argument("--curated-dir", type=Path, default=CURATED_DIR)
    validate = commands.add_parser("validate-plan")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--require-tasks", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        run_id = os.environ.get("ORCAP_SCORE_MEMORY_ROUTING_RUN_ID") or run_timestamp()
        seed = int(os.environ.get("ORCAP_SCORE_MEMORY_ROUTING_SEED", secrets.randbits(64)))
        with httpx.Client(timeout=base.REQUEST_TIMEOUT_SECONDS) as client:
            bundle = build_plan_bundle(client, run_id=run_id, seed=seed)
        paths = write_plan_bundle(bundle, bundle_path=args.bundle, curated_dir=args.curated_dir)
        print(json.dumps(bundle["summary"] | bundle["manifest"] | paths, indent=2))
    elif args.command == "execute":
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        print(
            json.dumps(
                execute_bundle(
                    bundle,
                    curated_dir=args.curated_dir,
                    data_root=args.curated_dir.parent,
                ),
                indent=2,
            )
        )
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        validate_manifest(
            bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
        )
        if not bundle["summary"].get("source_healthy"):
            raise RuntimeError("public successor source failed health validation")
        if args.require_tasks and len(bundle["assignments"]) != 10:
            raise RuntimeError("validated successor plan does not contain ten tasks")
        print(
            json.dumps(
                {
                    "manifest_sha256": bundle["manifest"]["manifest_sha256"],
                    "source_healthy": True,
                    "planned_tasks": len(bundle["assignments"]),
                    "planned_quote_cap_usd": bundle["summary"]["planned_quote_cap_usd"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
