import pandas as pd

from orcap.analysis.h70_preselection_information import (
    arm_effects,
    decision_window_panel,
    summarize,
)


def _row(event_id, arm, action_at="2026-07-12T00:00:00.100000Z"):
    return {
        "event_id": event_id,
        "study_id": "study-v1",
        "router": "router",
        "source": "router_decision_export",
        "arrival_at": "2026-07-12T00:00:00Z",
        "route_committed_at": "2026-07-12T00:00:00.200000Z",
        "candidate_set_version": "candidates",
        "selected_endpoint": "endpoint-a",
        "retry_outcome": "succeeded",
        "retry_count": 0,
        "quote_or_capacity_action_at": action_at,
        "provider_signal_at": "2026-07-12T00:00:00.050000Z",
        "action_class": "quote",
        "experiment_arm": arm,
        "assignment_id": f"assignment-{event_id}",
    }


def test_h70_labels_only_actions_inside_the_ordered_selection_window():
    panel = decision_window_panel(
        pd.DataFrame(
            [
                _row("in-window", "provider_visible"),
                _row("pre-arrival", "provider_blinded", "2026-07-11T23:59:59Z"),
            ]
        )
    )
    assert panel.loc[panel["event_id"] == "in-window", "ordered_preselection_action"].item()
    assert not panel.loc[panel["event_id"] == "pre-arrival", "action_in_selection_window"].item()


def test_h70_reports_randomized_study_as_power_gated_before_registered_sample_size():
    panel = decision_window_panel(
        pd.DataFrame(
            [
                _row("visible", "provider_visible"),
                _row("blinded", "provider_blinded"),
                _row("decoy", "decoy_signal"),
            ]
        )
    )
    effects = arm_effects(panel)
    result = summarize(panel, effects)
    assert result["evidence_status"] == "randomized_signal_power_gated"
    assert len(effects) == 2
    assert effects["power_gated"].all()
