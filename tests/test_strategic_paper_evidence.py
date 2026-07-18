import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    "esim5": "3e5a55405e",
    "esim6": "93265b9b03",
    "esim7": "bd74ab2eb7",
    "esim8": "4d84b9b3a2",
    "esim9": "179eca0f9d",
}
SOURCE_COMMIT = "4f9007be9e1ffdaea2cfce2a5ecc421d58b80f45"


def _load(experiment: str, filename: str) -> dict:
    path = ROOT / "output" / "market_env" / experiment / RUNS[experiment] / filename
    return json.loads(path.read_text())


def test_clean_confirmatory_manifests_match_committed_source():
    for experiment, run_id in RUNS.items():
        manifest = _load(experiment, "manifest.json")
        assert manifest["run_id"] == run_id
        assert manifest["commit"] == SOURCE_COMMIT
        assert manifest["market_env_source_matches_commit"]
        assert manifest["market_env_source_sha256"] == manifest["market_env_commit_source_sha256"]
        assert manifest["result_sha256"]


def test_delayed_credit_claim_boundary_matches_results():
    esim5 = _load("esim5", "results.json")
    esim6 = _load("esim6", "results.json")
    esim7 = _load("esim7", "results.json")
    esim8 = _load("esim8", "results.json")
    esim9 = _load("esim9", "results.json")

    assert not esim5["state_aliasing_mechanism_supported"]
    assert esim5["secondary"]["history_aware_exact_first_action"] == 1

    assert esim6["delayed_credit_intervention_supported"]
    assert esim6["primary"]["paired_mean"] == pytest.approx(-0.06425116521128763)
    assert esim6["primary"]["paired_bootstrap_ci95"] == pytest.approx(
        [-0.07552830101524913, -0.04930183305321537]
    )
    calibrated = next(arm for arm in esim6["sweep"] if arm["memory"] == 7)
    assert calibrated["primitive_success_profiles"] == 1
    assert calibrated["option_success_profiles"] == 18

    assert not esim7["cross_market_transport_supported"]
    for market in esim7["markets"].values():
        effect_is_beneficial = market["option_minus_primitive_regret"]["paired_mean"] < 0
        assert effect_is_beneficial == market["profile"]["delayed_credit_eligible"]

    assert esim8["robustness_gate"]
    assert esim8["passing_cells"] == 7
    assert all(
        cell["option_minus_primitive_regret"]["paired_bootstrap_ci95"][1] < 0
        for cell in esim8["cells"]
    )

    assert not esim9["multi_step_credit_supported"]
    assert esim9["primary"]["paired_mean"] == pytest.approx(0.003776415050762456)
    assert esim9["primary"]["paired_bootstrap_ci95"] == pytest.approx([0.0, 0.011329245152287368])
    assert esim9["primitive_success_profiles"] == 1
    assert esim9["n_step_success_profiles"] == 0
    assert esim9["option_success_profiles"] == 18


def test_paper_uses_clean_ids_and_preserves_negative_results():
    markdown = (ROOT / "manuscripts" / "price-weighted-routing.md").read_text()
    latex = (ROOT / "paper" / "price-weighted-routing" / "main.tex").read_text()
    registry = (ROOT / "docs" / "strategic-routing-confirmatory-registry-2026-07-18.md").read_text()

    for run_id in RUNS.values():
        assert run_id in latex
        assert run_id in registry
    assert "strict transport gate fails" in latex
    assert "state-aliasing gate fails" in latex
    assert "The preregistered state-aliasing gate\nfails" in markdown
    assert "not confidence intervals for live-market parameters" in markdown
    assert "ordinary multi-step target fails" in markdown
    assert "registered gate fails" in latex
