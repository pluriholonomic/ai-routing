from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_information_congestion_workflow_is_plan_first_private_and_budgeted():
    workflow = (ROOT / ".github/workflows/information-congestion.yml").read_text()
    assert workflow.index("upload immutable assignment-only plan before requests") < workflow.index(
        "verify immutable plan and execute exactly once"
    )
    assert "group: randomized-routing-probes" in workflow
    assert "ORCAP_INFORMATION_CONGESTION_ENABLED" in workflow
    assert "ORCAP_PAID_PRICE_STUDIES_ENABLED" in workflow
    assert "OPENROUTER_PRICE_EXPERIMENT_KEY" in workflow
    assert "ORCAP_INFORMATION_CONGESTION_MAX_CAMPAIGN_USD" in workflow
    assert "checkpoint request-level outcomes only to private Hugging Face" in workflow
    assert '"contains_request_level_outcomes": False' in workflow
    assert "github.run_attempt == 1" in workflow
    assert "needs.plan.outputs.source_healthy == 'true'" in workflow
    assert "curated/endpoints_snapshots" in workflow
    assert "retention-days: 90" in workflow


def test_recurring_monitor_is_outcome_blind():
    workflow = (ROOT / ".github/workflows/information-congestion-monitor.yml").read_text()
    assert "--support-only" in workflow
    assert "curated/ic_attempts" not in workflow
    assert "curated/paid_spend_ledger" not in workflow
    assert "recurring monitor accessed outcomes" in workflow
    assert "outcome count leaked" in workflow
    assert "information_congestion_shocks" in workflow
    assert "curated/congestion_intraday" in workflow
    assert "curated/ic_quality_assignments" in workflow
    assert "curated/ic_quality/*" not in workflow
    assert "--report-only" in workflow


def test_release_marks_before_accessing_outcomes_and_never_promotes_asymptotics():
    workflow = (ROOT / ".github/workflows/information-congestion-release.yml").read_text()
    marker = workflow.index("publish one-time outcome-access marker")
    outcomes = workflow.index("download private attempts and spend")
    analysis = workflow.index("run frozen confirmatory analysis once")
    assert marker < outcomes < analysis
    assert "--require-paid" in workflow
    assert "--require-confirmatory-support" in workflow
    assert "--report-only" not in workflow
    assert "curated/ic_common_shocks" in workflow
    assert "refuse any second outcome release" in workflow
    assert "release already exists" in workflow
    assert '"asymptotic_limit_identified": False' in workflow
    assert "inputs.release == 'RELEASE'" in workflow


def test_compaction_overlay_and_remote_watchdog_cover_new_study():
    assembly = (ROOT / "scripts/assemble_artifacts.sh").read_text()
    overlay = (ROOT / "scripts/assemble_price_artifacts.sh").read_text()
    health = (ROOT / "src/orcap/remote_health.py").read_text()
    assert "information-congestion.yml" in assembly
    assert "capture-backstop.yml" in assembly
    assert '[ "$MODE" = "ic" ]' in overlay
    assert "information-congestion-quality.yml" in overlay
    for item in (
        '"information-congestion.yml": 180',
        '"information-congestion-quality.yml": 540',
        '"capture-backstop.yml": 300',
        '"information-congestion-monitor.yml": 1800',
        '"curated/endpoints_snapshots": 1800',
        '"curated/ic_run_ledger": 1800',
        '"curated/ic_assignments": 1800',
        '"curated/ic_quality_assignments": 43200',
        '"analysis/information-congestion-v1": 1800',
    ):
        assert item in health


def test_quality_workflow_is_balanced_plan_first_private_and_budgeted():
    workflow = (ROOT / ".github/workflows/information-congestion-quality.yml").read_text()
    assert workflow.index("upload immutable assignment-only quality plan") < workflow.index(
        "verify immutable quality plan and execute exactly once"
    )
    assert "group: randomized-routing-probes" in workflow
    assert "ORCAP_INFORMATION_CONGESTION_QUALITY_ENABLED" in workflow
    assert "ORCAP_INFORMATION_CONGESTION_QUALITY_MAX_CAMPAIGN_USD" in workflow
    assert "'75.00'" in workflow
    assert "checkpoint redacted quality grades and spend only to private Hugging Face" in workflow
    assert '"contains_request_level_outcomes": False' in workflow
    assert "github.run_attempt == 1" in workflow
    assert "needs.plan.outputs.source_healthy == 'true'" in workflow
    assert "curated/endpoints_snapshots" in workflow


def test_capture_backstop_is_independent_redundant_and_non_destructive():
    workflow = (ROOT / ".github/workflows/capture-backstop.yml").read_text()
    assert 'cron: "17 */2 * * *"' in workflow
    assert "--samples \"${{ github.event.inputs.samples || '23' }}\"" in workflow
    assert "--interval-seconds 300" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "retention-days: 7" in workflow
    for downstream in (
        "information-congestion.yml",
        "price-event-probes.yml",
        "glm52-market-share-hmp.yml",
    ):
        text = (ROOT / ".github/workflows" / downstream).read_text()
        assert 'workflows: ["capture", "capture-backstop"]' in text


def test_preregistration_and_data_dictionary_exist():
    experiment = ROOT / "experiments/information-congestion-v1"
    protocol = (ROOT / "config/information_congestion_v1.toml").read_text()
    preregistration = (experiment / "preregistration.md").read_text()
    dictionary = (experiment / "data-dictionary.md").read_text()
    assert "primary_tau_margin = 0.05" in protocol
    assert "maximum_campaign_usd = 500.0" in protocol
    assert "tau > 0.05" in preregistration
    assert "never described as\nproof" in preregistration
    assert "ic_kstar_scaling" in dictionary
