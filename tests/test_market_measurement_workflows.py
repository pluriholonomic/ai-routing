from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_capture_workflow_is_plan_first_gated_budgeted_and_h95_isolated():
    text = (ROOT / ".github/workflows/market-measurement.yml").read_text()
    assert "group: randomized-routing-probes" in text
    assert "\nconcurrency:\n  group: randomized-routing-probes" not in text
    assert text.index("upload immutable assignment-only plan") < text.index(
        "verify uploaded plan and execute exactly once"
    )
    for gate in (
        "ORCAP_PAID_PRICE_STUDIES_ENABLED",
        "ORCAP_MARKET_MEASUREMENT_ENABLED",
        "ORCAP_MARKET_MEASUREMENT_START_UTC",
        "ORCAP_MARKET_MEASUREMENT_END_UTC",
        "ORCAP_MARKET_MEASUREMENT_MAX_RUN_USD",
        "ORCAP_MARKET_MEASUREMENT_MAX_DAY_USD",
        "ORCAP_MARKET_MEASUREMENT_MAX_CAMPAIGN_USD",
    ):
        assert gate in text
    assert "OPENROUTER_PRICE_EXPERIMENT_KEY" in text
    assert "OPENROUTER_API_KEY" not in text
    assert "decomposition-replication" not in text
    assert "execute_paid" in text
    assert "Path(snapshot).exists()" in text


def test_monitor_hydrates_only_isolated_tables_and_publishes_to_hf():
    text = (ROOT / ".github/workflows/market-measurement-monitor.yml").read_text()
    for table in (
        "market_measurement_assignments",
        "market_measurement_attempts",
        "market_measurement_quality",
    ):
        assert table in text
    assert "router_route_attempts" not in text
    assert "revision=revision" in text
    assert "uv run orcap push" in text
    assert 'repo_id="t4run/openrouter-memo"' in text
    assert "Path(snapshot).exists()" in text
    assert 'workflows: ["market-measurement"]' in text
    assert 'workflows: ["market-measurement", "compact"]' not in text
    assert "has_execution=true" in text
    assert "steps.overlay.outputs.has_execution == 'true'" in text
    assert "source_run_id:" in text
    assert 'gh run download "$SOURCE_RUN_ID"' in text
    assert "*/curated/market_measurement_attempts/*/*.parquet" in text
    assert "*/plan-data/curated/market_measurement_attempts/*/*.parquet" not in text
    assert "-type d -name curated" in text


def test_nightly_hf_assembly_includes_the_new_workflow():
    main = (ROOT / "scripts/assemble_artifacts.sh").read_text()
    paid = (ROOT / "scripts/assemble_price_artifacts.sh").read_text()
    assert "market-measurement.yml" in main
    assert "market-measurement.yml" in paid
