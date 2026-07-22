from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_live_workflow_is_assignment_first_budgeted_private_and_separate():
    text = (ROOT / ".github/workflows/glm52-market-share-hmp.yml").read_text()
    assert text.index("upload assignment-first immutable plan") < text.index(
        "verify immutable plan and execute due tasks once"
    )
    assert "group: glm52-market-share-hmp-queue" in text
    assert "randomized-routing-probes" not in text
    for gate in (
        "ORCAP_GLM52_HMP_ENABLED",
        "ORCAP_GLM52_HMP_START_UTC",
        "ORCAP_GLM52_HMP_END_UTC",
        "ORCAP_GLM52_HMP_MAX_RUN_USD",
        "ORCAP_GLM52_HMP_MAX_DAY_USD",
        "ORCAP_GLM52_HMP_MAX_CAMPAIGN_USD",
    ):
        assert gate in text
    assert "OPENROUTER_PRICE_EXPERIMENT_KEY" in text
    assert "OPENROUTER_API_KEY" not in text
    assert "glm52_hmp_events" in text
    assert "glm52_hmp_wave_plans" in text
    assert "congestion_intraday" in text
    assert "glm52_hmp_run_ledger" in text
    assert "assemble_price_artifacts.sh 48 input-data hmp" in text
    assert "github.run_attempt == 1" in text
    assert "checkpoint request-level telemetry to private Hugging Face" in text
    assert "glm52-hmp-public-execution.json" in text
    assert '"contains_request_level_outcomes": False' in text
    assert "preserve redacted attempts and spend ledger" not in text
    assert "path: plan-data/\n          if-no-files-found: warn" not in text


def test_monitor_and_full_simulation_cannot_self_promote_claims():
    monitor = (ROOT / ".github/workflows/glm52-market-share-hmp-monitor.yml").read_text()
    simulation = (ROOT / ".github/workflows/glm52-market-share-hmp-simulation.yml").read_text()
    for boundary in (
        "market_wide_share_identified",
        "provider_algorithm_identified",
        "provider_cost_identified",
        "collusion_identified",
        "communication_identified",
    ):
        assert boundary in monitor
    assert "empirical_property_chain_passed" in simulation
    assert "mechanism_validated" in simulation
    assert "--data-root input-data" in simulation
    assert "curated/endpoints_snapshots" in simulation
    assert "market-share-hmp.html" in monitor
    assert "group: glm52-market-share-hmp-monitor" in monitor
    assert "cancel-in-progress: false" in monitor
    assert '"curated/glm52_hmp_*/*/*.parquet"' in monitor
    assert '"curated/router_route_attempts/*/*.parquet"' not in monitor
    assert '"curated/paid_spend_ledger/*/*.parquet"' not in monitor


def test_compaction_and_overlay_include_the_new_queue():
    assembly = (ROOT / "scripts/assemble_artifacts.sh").read_text()
    overlay = (ROOT / "scripts/assemble_price_artifacts.sh").read_text()
    assert "glm52-market-share-hmp.yml" in assembly
    assert 'if [ "$MODE" = "hmp" ]' in overlay
    assert 'WORKFLOWS="capture.yml glm52-market-share-hmp.yml"' in overlay
    assert "request-level execution" in overlay.lower()
    assert "request-level outcomes" in assembly.lower()
