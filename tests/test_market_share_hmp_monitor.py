from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from orcap.analysis.market_share_hmp_monitor import _attempt_panel, gate_outcomes, run


def _write(frame: pd.DataFrame, root: Path, name: str) -> None:
    path = root / "curated" / name / "dt=2026-07-22"
    path.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path / "part.parquet", index=False)


def test_monitor_withholds_empirical_claims_before_support(tmp_path):
    _write(
        pd.DataFrame(
            [
                {
                    "event_id": "event-1",
                    "clean_event": True,
                    "multiplicity": "pair",
                    "focal_provider": "Novita",
                    "co_cutters": ["StreamLake"],
                    "co_cutter_count": 1,
                    "co_cutter_share_mass": 0.2,
                    "co_cutter_exposure": 0.2,
                }
            ]
        ),
        tmp_path,
        "glm52_hmp_events",
    )
    out = tmp_path / "analysis"
    simulation = out / "simulation-monitor"
    simulation.mkdir(parents=True)
    (simulation / "market_share_hmp_simulation_summary.json").write_text(
        json.dumps({"exact_singleton_zero_wedge_passed": True})
    )
    summary = run(tmp_path, out, source_revision="fixture")
    assert summary["empirical_support_gate_passed"] is False
    assert summary["outcomes_blinded_until_support_gate"] is True
    assert all(pd.isna(row["active_selection_rate"]) for row in summary["arm_summary"])
    assert summary["claim_ladder"]["MS1_exact_identity"] == "passed"
    assert summary["claim_ladder"]["MS2_public_multiplicity"] == "not_tested"
    for key in (
        "market_wide_share_identified",
        "provider_algorithm_identified",
        "provider_cost_identified",
        "collusion_identified",
        "communication_identified",
    ):
        assert summary[key] is False
    assert (out / "market-share-hmp.html").is_file()
    assert (out / "market_share_hmp_monitor.png").is_file()


def test_gate_outcomes_is_one_way_at_the_support_boundary():
    arms = pd.DataFrame(
        [
            {
                "policy": "joint_default",
                "attempts": 4,
                "successful": 3,
                "active_selections": 2,
                "active_selection_rate": 2 / 3,
            }
        ]
    )
    events = pd.DataFrame(
        [{"event_id": "event-1", "active_selection_rate": 0.75}]
    )

    blind_arms, blind_events = gate_outcomes(arms, events, released=False)
    assert blind_arms.loc[0, "attempts"] == 4
    assert pd.isna(blind_arms.loc[0, "successful"])
    assert pd.isna(blind_arms.loc[0, "active_selection_rate"])
    assert pd.isna(blind_events.loc[0, "active_selection_rate"])

    open_arms, open_events = gate_outcomes(arms, events, released=True)
    assert open_arms.loc[0, "active_selection_rate"] == 2 / 3
    assert open_events.loc[0, "active_selection_rate"] == 0.75


def test_first_two_background_blocks_are_frozen_as_legacy_cap_stratum(tmp_path):
    rows = []
    for event_id in (
        "mshmp-background-20260722T0300Z",
        "mshmp-background-20260722T0400Z",
        "mshmp-background-20260722T0500Z",
    ):
        rows.append(
            {
                "study_id": "openrouter-glm52-market-share-hmp-v1",
                "metadata_json": json.dumps(
                    {"task_id": event_id, "block_id": event_id, "event_id": event_id}
                ),
            }
        )
    _write(pd.DataFrame(rows), tmp_path, "glm52_hmp_attempts")

    panel = _attempt_panel(tmp_path).set_index("registered_event_id")

    assert (
        panel.loc["mshmp-background-20260722T0300Z", "execution_cap_stratum"]
        == "legacy_eight_token_cap"
    )
    assert (
        panel.loc["mshmp-background-20260722T0400Z", "execution_cap_stratum"]
        == "legacy_eight_token_cap"
    )
    assert (
        panel.loc["mshmp-background-20260722T0500Z", "execution_cap_stratum"]
        == "one_token_cap"
    )
