from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_paid_workflow_is_separate_plan_first_budgeted_and_locked():
    text = (ROOT / ".github/workflows/adaptive-router.yml").read_text()
    assert text.index("upload immutable assignment-only plan before requests") < text.index(
        "execute frozen provider draws exactly once"
    )
    assert "group: randomized-routing-probes" in text
    assert "cancel-in-progress: false" in text
    assert "OPENROUTER_PRICE_EXPERIMENT_KEY" in text
    assert "ORCAP_ADAPTIVE_ROUTER_ENABLED" in text
    assert "2026-07-21T00:00:00Z" in text
    assert "2026-08-04T03:00:00Z" in text
    assert "--max-blocks 3" in text
    assert "retention-days: 90" in text


def test_monitor_and_counterfactual_use_immutable_hf_inputs():
    monitor = (ROOT / ".github/workflows/adaptive-router-monitor.yml").read_text()
    replay = (ROOT / ".github/workflows/adaptive-router-counterfactual.yml").read_text()
    assert "curated/adaptive_router_assignments" in monitor
    assert "curated/adaptive_router_attempts" in monitor
    assert "adaptive_router_counterfactual" not in monitor
    assert 'workflows: ["compact"]' in replay
    assert "curated/endpoints_snapshots" in replay
    assert "revision=revision" in replay
    assert "hf-revision.txt" in replay


def test_compaction_assemblers_include_adaptive_router_artifacts():
    assert "adaptive-router.yml" in (ROOT / "scripts/assemble_artifacts.sh").read_text()
    assert "adaptive-router.yml" in (ROOT / "scripts/assemble_price_artifacts.sh").read_text()
    assert (ROOT / "experiments/openrouter-adaptive-monotone-v1/preregistration.md").is_file()
