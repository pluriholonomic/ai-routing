from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_glm52_capture_is_high_frequency_plan_first_and_fail_closed():
    text = (ROOT / ".github/workflows/glm52-routing.yml").read_text()
    assert 'cron: "7,22,37,52 * * * *"' in text
    assert "group: randomized-routing-probes" in text
    assert "cancel-in-progress: false" in text
    assert text.index("upload immutable assignment-only plan") < text.index(
        "verify uploaded plan and execute exactly once"
    )
    for gate in (
        "ORCAP_PAID_PRICE_STUDIES_ENABLED",
        "ORCAP_GLM52_ROUTING_ENABLED",
        "ORCAP_GLM52_ROUTING_START_UTC",
        "ORCAP_GLM52_ROUTING_END_UTC",
        "ORCAP_GLM52_ROUTING_MAX_RUN_USD",
        "ORCAP_GLM52_ROUTING_MAX_DAY_USD",
        "ORCAP_GLM52_ROUTING_MAX_CAMPAIGN_USD",
    ):
        assert gate in text
    assert "OPENROUTER_PRICE_EXPERIMENT_KEY" in text
    assert "OPENROUTER_API_KEY" not in text
    assert "assemble_price_artifacts.sh 48 input-data glm52" in text
    assert "retention-days: 90" in text


def test_glm52_monitor_reads_only_isolated_tables_and_publishes_aggregates():
    text = (ROOT / ".github/workflows/glm52-routing-monitor.yml").read_text()
    for table in (
        "glm52_routing_candidates",
        "glm52_routing_assignments",
        "glm52_routing_attempts",
    ):
        assert table in text
    assert "router_route_attempts" not in text
    assert "assemble_price_artifacts.sh 48 input-data glm52" in text
    assert "orcap.analysis.glm52_routing_monitor" in text
    assert "uv run orcap push" in text
    assert 'repo_id="t4run/openrouter-memo"' in text


def test_glm52_artifacts_feed_compaction_and_live_exponent():
    main = (ROOT / "scripts/assemble_artifacts.sh").read_text()
    paid = (ROOT / "scripts/assemble_price_artifacts.sh").read_text()
    exponent_workflow = (ROOT / ".github/workflows/live-router-exponent.yml").read_text()
    exponent_code = (ROOT / "src/orcap/analysis/live_router_exponent.py").read_text()
    assert "glm52-routing.yml" in main
    assert 'if [ "$wf" = "glm52-routing.yml" ]' in main
    assert "limit=120" in main
    assert 'WORKFLOWS="glm52-routing.yml"' in paid
    assert "LIMIT=220" in paid
    assert "glm52_routing_candidates" in exponent_workflow
    assert "glm52_routing_assignments" in exponent_workflow
    assert "openrouter-glm52-routing-v1" in exponent_code
    assert (ROOT / "experiments/openrouter-glm52-routing-v1/preregistration.md").is_file()
