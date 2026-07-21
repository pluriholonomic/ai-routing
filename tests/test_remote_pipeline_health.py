from datetime import UTC, datetime, timedelta
from pathlib import Path

from orcap.remote_health import HF_PRICE_TABLES, WORKFLOWS, evaluate_workflow

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def test_confirmatory_probe_workflows_are_remotely_monitored():
    assert WORKFLOWS["probes.yml"] == 180
    assert WORKFLOWS["decomposition-probes.yml"] == 180
    assert WORKFLOWS["decomposition-replication.yml"] == 180
    assert WORKFLOWS["router-catalogs.yml"] == 180
    assert WORKFLOWS["confirmatory-release.yml"] == 1800
    assert WORKFLOWS["capacity-policy-probes.yml"] == 180
    assert WORKFLOWS["hf-policy-probes.yml"] == 180
    assert WORKFLOWS["akash-close-events.yml"] == 1800
    assert WORKFLOWS["paid-price-response.yml"] == 360
    assert WORKFLOWS["price-event-probes.yml"] == 180
    assert WORKFLOWS["price-tests-online.yml"] == 540
    assert WORKFLOWS["undercutting-incidence.yml"] == 540
    assert WORKFLOWS["live-router-exponent.yml"] == 540
    assert WORKFLOWS["adaptive-router.yml"] == 540
    assert WORKFLOWS["adaptive-router-monitor.yml"] == 1800
    assert WORKFLOWS["adaptive-router-counterfactual.yml"] == 1800
    assert WORKFLOWS["hmp-signal-coupling-monitor.yml"] == 1800
    assert "curated/price_response_assignments" in HF_PRICE_TABLES
    assert "analysis/router_exponent_estimates" in HF_PRICE_TABLES
    assert "analysis/undercutting-incidence-v1" in HF_PRICE_TABLES


def test_confirmatory_probe_workflows_share_concurrency_lock():
    workflows = Path(__file__).parents[1] / ".github" / "workflows"
    h80 = (workflows / "probes.yml").read_text(encoding="utf-8")
    h81 = (workflows / "decomposition-probes.yml").read_text(encoding="utf-8")
    h95 = (workflows / "decomposition-replication.yml").read_text(encoding="utf-8")
    h87 = (workflows / "capacity-policy-probes.yml").read_text(encoding="utf-8")
    h96 = (workflows / "route-calibration.yml").read_text(encoding="utf-8")
    price_response = (workflows / "paid-price-response.yml").read_text(encoding="utf-8")
    price_events = (workflows / "price-event-probes.yml").read_text(encoding="utf-8")
    adaptive = (workflows / "adaptive-router.yml").read_text(encoding="utf-8")
    lock = "group: randomized-routing-probes"
    assert lock in h80
    assert lock in h81
    assert lock in h95
    assert lock in h87
    assert lock in h96
    assert lock in price_response
    assert lock in price_events
    assert lock in adaptive


def test_paid_price_workflows_are_plan_first_trigger_scoped_and_fail_closed():
    root = Path(__file__).parents[1]
    workflows = root / ".github" / "workflows"
    response = (workflows / "paid-price-response.yml").read_text(encoding="utf-8")
    events = (workflows / "price-event-probes.yml").read_text(encoding="utf-8")
    for workflow in (response, events):
        assert "jobs:\n  plan:" in workflow
        assert "needs: plan" in workflow
        assert "ORCAP_PAID_PRICE_STUDIES_ENABLED == 'true'" in workflow
        assert "secrets.OPENROUTER_PRICE_EXPERIMENT_KEY" in workflow
        assert "retention-days: 90" in workflow
        assert "cancel-in-progress: false" in workflow
        assert "\nconcurrency:\n  group: randomized-routing-probes" not in workflow
    assert "github.event_name == 'schedule'" in response
    assert "github.event_name == 'push'" in response
    assert "activation-canary-v*" in response
    assert "ORCAP_PAID_PRICE_RESPONSE_ENABLED" not in response
    assert "ORCAP_PAID_PRICE_EVENTS_ENABLED" not in events
    for workflow in (response, events):
        assert "2026-07-20T04:00:00Z" in workflow
        assert "2026-07-27T04:00:00Z" in workflow
    assert 'workflows: ["capture"]' in events
    assert "github.event.workflow_run.conclusion == 'success'" in events
    assert "github.event_name == 'workflow_run'" in events
    assert "github.event_name == 'schedule' &&" not in events
    assert "needs.plan.outputs.has_tasks == 'true'" in events
    assert "plan_w1:" in events and "execute_w1:" in events
    assert "plan_w2:" in events and "execute_w2:" in events
    assert "--wave-id w1" in events and "--max-wait-seconds 1800" in events
    assert "--wave-id w2" in events and "--max-wait-seconds 3600" in events
    assert events.index("upload W1 plan before requests") < events.index(
        "verify uploaded W1 plan and execute exactly once"
    )
    assert events.index("upload W2 plan before requests") < events.index(
        "verify uploaded W2 plan and execute exactly once"
    )
    assert 'if Path(snapshot).exists()' in response
    assert 'if Path(snapshot).exists()' in events
    assert response.index("upload immutable assignment-only plan") < response.index(
        "verify uploaded plan and execute exactly once"
    )
    assert events.index("upload immutable event and assignment plan") < events.index(
        "verify uploaded wave plan and execute due tasks"
    )


def test_price_workflows_are_assembled_analyzed_and_preregistered():
    root = Path(__file__).parents[1]
    assembler = (root / "scripts/assemble_artifacts.sh").read_text(encoding="utf-8")
    assert "paid-price-response.yml" in assembler
    assert "price-event-probes.yml" in assembler
    price_assembler = (root / "scripts/assemble_price_artifacts.sh").read_text(
        encoding="utf-8"
    )
    assert "paid-price-response.yml price-event-probes.yml" in price_assembler
    assert 'WORKFLOWS="$WORKFLOWS capture.yml"' in price_assembler
    response = (root / ".github/workflows/paid-price-response.yml").read_text()
    events = (root / ".github/workflows/price-event-probes.yml").read_text()
    assert "assemble_price_artifacts.sh 26 input-data paid" in response
    assert "assemble_price_artifacts.sh 3 input-data event" in events
    for name in ("price-tests-online.yml", "live-router-exponent.yml"):
        workflow = (root / ".github/workflows" / name).read_text(encoding="utf-8")
        assert "workflow_run:" in workflow
        assert 'workflows: ["compact"]' in workflow
        assert "OPENROUTER_PRICE_EXPERIMENT_KEY" not in workflow
    exponent = (root / ".github/workflows/live-router-exponent.yml").read_text()
    for table in (
        "market_measurement_candidates",
        "market_measurement_assignments",
        "market_measurement_attempts",
    ):
        assert table in exponent
    assert (
        root / "experiments/openrouter-price-response-v1/preregistration.md"
    ).is_file()
    assert (root / "experiments/openrouter-price-event-v1/preregistration.md").is_file()
    assert (root / "experiments/undercutting-incidence-v1/preregistration.md").is_file()


def test_undercutting_incidence_is_recurring_and_uses_frozen_types():
    root = Path(__file__).parents[1]
    workflow = (root / ".github/workflows/undercutting-incidence.yml").read_text()
    online = (root / "src/orcap/analysis/price_tests_online.py").read_text()
    simulation = (root / "src/orcap/routing_simulation.py").read_text()
    protocol = (root / "config/undercutting_incidence_v1.toml").read_text()
    assert 'workflows: ["compact"]' in workflow
    assert "--hypothesis wf19" in workflow
    assert "frozen_label_artifact_revision" in protocol
    assert "frozen_labels_sha256" in protocol
    assert "wf19_undercutting_incidence" in online
    for model in (
        "minimax/minimax-m2.5",
        "minimax/minimax-m2.7",
        "moonshotai/kimi-k2.6",
        "moonshotai/kimi-k2.7-code",
        "qwen/qwen3-235b-a22b-2507",
        "qwen/qwen3.6-27b",
        "z-ai/glm-4.6",
        "z-ai/glm-5",
    ):
        assert model in simulation


def test_hmp_signal_coupling_workflows_are_support_gated_and_private():
    root = Path(__file__).parents[1]
    workflows = root / ".github" / "workflows"
    monitor = (workflows / "hmp-signal-coupling-monitor.yml").read_text()
    release = (workflows / "hmp-signal-coupling-release.yml").read_text()
    assert 'workflows: ["compact"]' in monitor
    assert "ORCAP_HF_REVISION" in monitor
    assert "snapshot_download_retry" in monitor
    assert "ORCAP_ANALYSIS_SOURCE: local" in monitor
    assert "ORCAP_DATA_DIR: input-data" in monitor
    assert "--preflight" in monitor
    assert "--hypothesis wf18" in monitor
    assert "wf18_owned_choice_risk_set.parquet" in monitor
    assert monitor.index("validate claim and privacy boundaries") < monitor.index(
        "remove private owned-choice rows before publication"
    )
    assert "OPENROUTER_PRICE_EXPERIMENT_KEY" not in monitor
    assert "Type RELEASE" in release
    assert "snapshot_download_retry" in release
    assert "ORCAP_ANALYSIS_SOURCE: local" in release
    assert "sample-only preflight before marker" in release
    assert "one-time immutable promotion marker before release publication" in release
    assert release.index(
        "run WF18 release-candidate analysis on the frozen revision"
    ) < release.index("one-time immutable promotion marker before release publication")
    assert "outcomes_accessed" in release
    assert "release_ready" in release
    assert (root / "experiments/hmp-signal-coupling-v1/preregistration.md").is_file()


def test_h96_remote_campaign_is_finite_budgeted_and_manual_preflight_only():
    root = Path(__file__).parents[1]
    workflow = (root / ".github/workflows/route-calibration.yml").read_text(
        encoding="utf-8"
    )
    assembler = (root / "scripts/assemble_artifacts.sh").read_text(encoding="utf-8")
    assert 'cron: "37 1,5,9,13,17,21 19,20 7 *"' in workflow
    assert 'ORCAP_H96_MAX_RUN_USD: "0.35"' in workflow
    assert 'ORCAP_H96_MAX_BLOCKS_PER_RUN: "3"' in workflow
    assert "timeout-minutes: 50" in workflow
    assert "--scheduled" in workflow
    assert "--preflight-only" in workflow
    assert "route-calibration.yml" in assembler


def _run(*, minutes_ago, status="completed", conclusion="success"):
    return {
        "id": 1,
        "created_at": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "status": status,
        "conclusion": conclusion,
        "html_url": "https://github.example/run/1",
    }


def test_remote_health_accepts_recent_success_or_active_run():
    success = evaluate_workflow("capture.yml", [_run(minutes_ago=60)], now=NOW, max_age_minutes=150)
    active = evaluate_workflow(
        "capture.yml",
        [_run(minutes_ago=20, status="in_progress", conclusion=None)],
        now=NOW,
        max_age_minutes=150,
    )
    assert success["healthy"] is True
    assert active["healthy"] is True


def test_remote_health_rejects_latest_failure_even_if_previous_run_succeeded():
    result = evaluate_workflow(
        "capture.yml",
        [_run(minutes_ago=80), _run(minutes_ago=20, conclusion="failure")],
        now=NOW,
        max_age_minutes=150,
    )
    assert result["healthy"] is False
    assert "failure" in result["reason"]


def test_remote_health_ignores_newer_skipped_or_cancelled_runs():
    for conclusion in ("skipped", "cancelled"):
        result = evaluate_workflow(
            "compact.yml",
            [_run(minutes_ago=80), _run(minutes_ago=20, conclusion=conclusion)],
            now=NOW,
            max_age_minutes=150,
        )
        assert result["healthy"] is True
        assert result["ignored_terminal_runs"] == 1
        assert "ignored 1" in result["reason"]


def test_remote_health_rejects_only_skipped_or_cancelled_runs():
    result = evaluate_workflow(
        "confirmatory-release.yml",
        [
            _run(minutes_ago=80, conclusion="cancelled"),
            _run(minutes_ago=20, conclusion="skipped"),
        ],
        now=NOW,
        max_age_minutes=150,
    )
    assert result["healthy"] is False
    assert result["ignored_terminal_runs"] == 2
    assert "no actionable runs" in result["reason"]


def test_remote_health_rejects_stale_success():
    result = evaluate_workflow(
        "capture.yml", [_run(minutes_ago=151)], now=NOW, max_age_minutes=150
    )
    assert result["healthy"] is False
    assert "stale" in result["reason"]
