"""Remote GitHub Actions and Hugging Face sink health checks."""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi

WORKFLOWS = {
    "capacity-policy-probes.yml": 180,
    "enforcement-policy-probes.yml": 180,
    "capture.yml": 150,
    "decomposition-probes.yml": 180,
    "gpu.yml": 180,
    "hf-router.yml": 180,
    "hf-policy-probes.yml": 180,
    "livepeer.yml": 180,
    "market.yml": 180,
    "probes.yml": 180,
    "route-simulation-monitor.yml": 180,
    "compact.yml": 1800,
    "scrape.yml": 1800,
    "open-usage.yml": 1800,
    "memo.yml": 1800,
    "marketplace-history.yml": 1800,
    "bittensor.yml": 540,
}
HF_MAX_AGE_MINUTES = 1800


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def evaluate_workflow(
    workflow: str, runs: list[dict[str, Any]], *, now: datetime, max_age_minutes: int
) -> dict[str, Any]:
    if not runs:
        return {"workflow": workflow, "healthy": False, "reason": "no runs"}
    latest = max(runs, key=lambda run: _time(run["created_at"]))
    age_minutes = (now - _time(latest["created_at"])).total_seconds() / 60
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    if age_minutes > max_age_minutes:
        healthy, reason = False, f"latest run is stale ({age_minutes:.0f} minutes)"
    elif status in {"queued", "in_progress", "waiting", "pending", "requested"}:
        healthy, reason = True, "recent run active"
    elif status == "completed" and conclusion == "success":
        healthy, reason = True, "latest run succeeded"
    else:
        healthy, reason = False, f"latest run ended {status}/{conclusion}"
    return {
        "workflow": workflow,
        "healthy": healthy,
        "reason": reason,
        "age_minutes": round(age_minutes, 2),
        "status": status,
        "conclusion": conclusion,
        "run_id": latest.get("id"),
        "html_url": latest.get("html_url"),
        "created_at": latest.get("created_at"),
    }


def _github_runs(repo: str, workflow: str, token: str) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?per_page=10"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "orcap-remote-health/1",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    return body.get("workflow_runs", []) if isinstance(body, dict) else []


def _hf_health(token: str, repo_id: str, now: datetime) -> dict[str, Any]:
    commits = HfApi(token=token).list_repo_commits(repo_id, repo_type="dataset")
    if not commits:
        return {"sink": repo_id, "healthy": False, "reason": "no dataset commits"}
    latest = commits[0]
    created_at = latest.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    age_minutes = (now - created_at.astimezone(UTC)).total_seconds() / 60
    return {
        "sink": repo_id,
        "healthy": age_minutes <= HF_MAX_AGE_MINUTES,
        "reason": (
            "latest dataset commit fresh"
            if age_minutes <= HF_MAX_AGE_MINUTES
            else f"dataset sink stale ({age_minutes:.0f} minutes)"
        ),
        "age_minutes": round(age_minutes, 2),
        "commit_id": latest.commit_id,
        "created_at": created_at.isoformat(),
    }


def main() -> int:
    token = os.environ.get("GH_TOKEN")
    hf_token = os.environ.get("HF_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not hf_token or not repo:
        raise RuntimeError("GH_TOKEN, HF_TOKEN, and GITHUB_REPOSITORY are required")
    now = datetime.now(UTC)
    workflows = [
        evaluate_workflow(
            workflow,
            _github_runs(repo, workflow, token),
            now=now,
            max_age_minutes=max_age,
        )
        for workflow, max_age in WORKFLOWS.items()
    ]
    sink = _hf_health(hf_token, "t4run/openrouter-market-history", now)
    result = {
        "checked_at": now.isoformat(),
        "repository": repo,
        "healthy": all(item["healthy"] for item in workflows) and sink["healthy"],
        "workflows": workflows,
        "data_sink": sink,
    }
    Path("remote-health.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1
