from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_quality_workflow_is_plan_first_budgeted_and_remote():
    text = (ROOT / ".github/workflows/score-memory-quality.yml").read_text()
    assert 'cron: "43 0,6,12,18 * * *"' in text
    assert text.index("upload immutable assignment-only plan") < text.index(
        "verify uploaded plan and execute exactly once"
    )
    assert "group: randomized-routing-probes" in text
    assert "cancel-in-progress: false" in text
    for gate in (
        "ORCAP_PAID_PRICE_STUDIES_ENABLED",
        "ORCAP_SCORE_MEMORY_QUALITY_ENABLED",
        "ORCAP_SCORE_MEMORY_QUALITY_START_UTC",
        "ORCAP_SCORE_MEMORY_QUALITY_END_UTC",
        "ORCAP_SCORE_MEMORY_QUALITY_MAX_RUN_USD",
        "ORCAP_SCORE_MEMORY_QUALITY_MAX_DAY_USD",
        "ORCAP_SCORE_MEMORY_QUALITY_MAX_CAMPAIGN_USD",
    ):
        assert gate in text
    assert "OPENROUTER_PRICE_EXPERIMENT_KEY" in text
    assert "retention-days: 90" in text


def test_monitor_reads_isolated_tables_and_publishes_only_aggregates():
    text = (ROOT / ".github/workflows/score-memory-monitor.yml").read_text()
    for table in (
        "glm52_routing_candidates",
        "glm52_routing_assignments",
        "glm52_routing_attempts",
        "score_memory_quality",
    ):
        assert table in text
    assert "router_route_attempts" not in text
    assert "orcap.analysis.score_memory_monitor" in text
    assert "assemble_price_artifacts.sh 48 input-data score-memory" in text
    assert "uv run orcap push" in text
    assert 'repo_id="t4run/openrouter-memo"' in text


def test_quality_artifacts_feed_nightly_compaction_and_spend_overlay():
    main = (ROOT / "scripts/assemble_artifacts.sh").read_text()
    paid = (ROOT / "scripts/assemble_price_artifacts.sh").read_text()
    assert "score-memory-quality.yml" in main
    assert 'WORKFLOWS="score-memory-quality.yml"' in paid
    assert 'WORKFLOWS="score-memory-routing.yml"' in paid
    assert 'WORKFLOWS="glm52-routing.yml score-memory-routing.yml score-memory-quality.yml"' in paid


def test_successor_is_separate_plan_first_and_window_gated():
    text = (ROOT / ".github/workflows/score-memory-routing.yml").read_text()
    assert 'cron: "12,27,42,57 21-23 4 8 *"' in text
    assert 'cron: "12,27,42,57 * 5-18 8 *"' in text
    assert (
        "openrouter-score-memory-routing-v1"
        in (ROOT / "src/orcap/capture_score_memory_routing.py").read_text()
    )
    assert text.index("upload immutable assignment-only plan") < text.index(
        "verify uploaded plan and execute exactly once"
    )
    assert "check frozen successor campaign window" in text
    assert "steps.window.outputs.open == 'true'" in text
    assert "group: randomized-routing-probes" in text
    assert "retention-days: 90" in text
    monitor = (ROOT / ".github/workflows/score-memory-monitor.yml").read_text()
    assert '"score-memory-routing"' in monitor
