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
    "akash-close-events.yml": 1800,
    "capacity-policy-probes.yml": 180,
    "enforcement-policy-probes.yml": 180,
    "capture.yml": 150,
    "decomposition-probes.yml": 180,
    "decomposition-replication.yml": 180,
    "paid-price-response.yml": 360,
    "price-event-probes.yml": 180,
    "price-tests-online.yml": 540,
    "live-router-exponent.yml": 540,
    "adaptive-router.yml": 540,
    "adaptive-router-monitor.yml": 1800,
    "adaptive-router-counterfactual.yml": 1800,
    "gpu.yml": 180,
    "hf-router.yml": 180,
    "hf-policy-probes.yml": 180,
    "livepeer.yml": 180,
    "market.yml": 180,
    "probes.yml": 180,
    "router-catalogs.yml": 180,
    "route-simulation-monitor.yml": 180,
    "compact.yml": 1800,
    "confirmatory-release.yml": 1800,
    "scrape.yml": 1800,
    "open-usage.yml": 1800,
    "memo.yml": 1800,
    "marketplace-history.yml": 1800,
    "bittensor.yml": 540,
}
HF_MAX_AGE_MINUTES = 1800
HF_PRICE_TABLES = {
    "curated/price_response_assignments": 1800,
    "curated/price_event_wave_plans": 1800,
    "analysis/router_exponent_estimates": 720,
}


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def evaluate_workflow(
    workflow: str, runs: list[dict[str, Any]], *, now: datetime, max_age_minutes: int
) -> dict[str, Any]:
    if not runs:
        return {"workflow": workflow, "healthy": False, "reason": "no runs"}
    ordered = sorted(runs, key=lambda run: _time(run["created_at"]), reverse=True)
    # GitHub records a workflow_run job as skipped when its upstream workflow
    # fails the job-level guard. Workflows with cancel-in-progress also retain
    # superseded cancellations. Neither is an execution result for the monitored
    # pipeline, so fall back to the most recent actionable run. A true failure
    # remains actionable and must never be hidden by an older success.
    ignored = [
        run
        for run in ordered
        if run.get("status") == "completed"
        and run.get("conclusion") in {"skipped", "cancelled"}
    ]
    actionable = [run for run in ordered if run not in ignored]
    if not actionable:
        latest_observed = ordered[0]
        return {
            "workflow": workflow,
            "healthy": False,
            "reason": "no actionable runs (only skipped/cancelled)",
            "age_minutes": round(
                (now - _time(latest_observed["created_at"])).total_seconds() / 60,
                2,
            ),
            "status": latest_observed.get("status"),
            "conclusion": latest_observed.get("conclusion"),
            "run_id": latest_observed.get("id"),
            "html_url": latest_observed.get("html_url"),
            "created_at": latest_observed.get("created_at"),
            "ignored_terminal_runs": len(ignored),
        }
    latest = actionable[0]
    age_minutes = (now - _time(latest["created_at"])).total_seconds() / 60
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    if age_minutes > max_age_minutes:
        healthy, reason = False, f"latest run is stale ({age_minutes:.0f} minutes)"
    elif status in {"queued", "in_progress", "waiting", "pending", "requested"}:
        healthy, reason = True, "recent run active"
    elif status == "completed" and conclusion == "success":
        healthy = True
        reason = (
            f"latest actionable run succeeded; ignored {len(ignored)} "
            "newer skipped/cancelled run(s)"
            if ignored and ordered[0] is not latest
            else "latest run succeeded"
        )
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
        "ignored_terminal_runs": len(ignored),
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


def _hf_table_health(
    token: str, repo_id: str, path: str, now: datetime, max_age_minutes: int
) -> dict[str, Any]:
    api = HfApi(token=token)
    try:
        entries = list(
            api.list_repo_tree(
                repo_id,
                path_in_repo=path,
                repo_type="dataset",
                recursive=True,
                expand=True,
            )
        )
    except Exception as exc:
        return {
            "path": path,
            "healthy": False,
            "reason": f"table unavailable ({type(exc).__name__})",
        }
    dates = []
    for entry in entries:
        commit = getattr(entry, "last_commit", None)
        created_at = getattr(commit, "date", None)
        if isinstance(created_at, datetime):
            dates.append(
                created_at.replace(tzinfo=created_at.tzinfo or UTC).astimezone(UTC)
            )
    if not dates:
        return {"path": path, "healthy": False, "reason": "no dated table objects"}
    latest = max(dates)
    age_minutes = (now - latest).total_seconds() / 60
    return {
        "path": path,
        "healthy": age_minutes <= max_age_minutes,
        "reason": (
            "latest table object fresh"
            if age_minutes <= max_age_minutes
            else f"table stale ({age_minutes:.0f} minutes)"
        ),
        "age_minutes": round(age_minutes, 2),
        "created_at": latest.isoformat(),
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
    price_tables = [
        _hf_table_health(
            hf_token,
            "t4run/openrouter-market-history",
            path,
            now,
            max_age,
        )
        for path, max_age in HF_PRICE_TABLES.items()
    ]
    require_price_tables = (
        os.environ.get("ORCAP_PRICE_MONITOR_TABLES_REQUIRED", "").lower() == "true"
    )
    tables_healthy = all(item["healthy"] for item in price_tables)
    result = {
        "checked_at": now.isoformat(),
        "repository": repo,
        "healthy": (
            all(item["healthy"] for item in workflows)
            and sink["healthy"]
            and (tables_healthy or not require_price_tables)
        ),
        "workflows": workflows,
        "data_sink": sink,
        "price_table_sinks": price_tables,
        "price_tables_required": require_price_tables,
    }
    Path("remote-health.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["healthy"] else 1
