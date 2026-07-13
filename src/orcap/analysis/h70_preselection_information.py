"""H70 — audit timing evidence for an opt-in private pre-selection study.

This module distinguishes three facts that are often conflated: a public
quote change, a quote action inside a request's selection window, and a causal
effect of provider visibility.  Only the last requires randomized visible,
blinded, and decoy arms.  It never reads request payloads.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

from . import data
from .common import DEFAULT_OUT, save, save_json

MIN_EVENTS_PER_RANDOMIZED_ARM = 200
ARMS = ("provider_visible", "provider_blinded", "decoy_signal")


def _empty_panel() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "event_id",
            "study_id",
            "router",
            "source",
            "arrival_at",
            "route_committed_at",
            "candidate_set_version",
            "selected_endpoint",
            "retry_outcome",
            "retry_count",
            "quote_or_capacity_action_at",
            "provider_signal_at",
            "action_class",
            "experiment_arm",
            "assignment_id",
            "selection_window_ms",
            "action_observed",
            "action_in_selection_window",
            "signal_observed",
            "action_after_signal",
            "ordered_preselection_action",
        ]
    )


def load_events() -> pd.DataFrame:
    try:
        table_glob = data.table_glob("router_decision_events")
        return data.q(
            f"select distinct * from read_parquet('{table_glob}', union_by_name = true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def decision_window_panel(events: pd.DataFrame) -> pd.DataFrame:
    """Label timestamp ordering without treating it as proof of intent."""
    if events.empty:
        return _empty_panel()
    frame = events.copy()
    for column in _empty_panel().columns:
        if column not in frame:
            frame[column] = pd.NA
    for column in (
        "arrival_at",
        "route_committed_at",
        "quote_or_capacity_action_at",
        "provider_signal_at",
    ):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    frame = frame.dropna(subset=["arrival_at", "route_committed_at"]).copy()
    frame["selection_window_ms"] = (
        frame["route_committed_at"] - frame["arrival_at"]
    ).dt.total_seconds() * 1000
    frame["action_observed"] = frame["quote_or_capacity_action_at"].notna()
    frame["action_in_selection_window"] = (
        frame["action_observed"]
        & (frame["quote_or_capacity_action_at"] >= frame["arrival_at"])
        & (frame["quote_or_capacity_action_at"] < frame["route_committed_at"])
    )
    frame["signal_observed"] = frame["provider_signal_at"].notna()
    frame["action_after_signal"] = (
        frame["action_observed"]
        & frame["signal_observed"]
        & (frame["quote_or_capacity_action_at"] >= frame["provider_signal_at"])
    )
    frame["ordered_preselection_action"] = (
        frame["action_in_selection_window"] & frame["action_after_signal"]
    )
    return frame.loc[:, _empty_panel().columns]


def arm_effects(panel: pd.DataFrame) -> pd.DataFrame:
    """Estimate the visible-versus-control action-rate contrast when available."""
    columns = [
        "study_id",
        "contrast",
        "visible_events",
        "control_events",
        "visible_ordered_actions",
        "control_ordered_actions",
        "risk_difference",
        "fisher_exact_p_value",
        "power_gated",
    ]
    if panel.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict] = []
    for study_id, study in panel.groupby("study_id", dropna=False):
        visible = study[study["experiment_arm"] == "provider_visible"]
        for control_arm in ("provider_blinded", "decoy_signal"):
            control = study[study["experiment_arm"] == control_arm]
            n_visible, n_control = len(visible), len(control)
            a_visible = int(visible["ordered_preselection_action"].sum())
            a_control = int(control["ordered_preselection_action"].sum())
            powered = (
                n_visible >= MIN_EVENTS_PER_RANDOMIZED_ARM
                and n_control >= MIN_EVENTS_PER_RANDOMIZED_ARM
            )
            p_value = np.nan
            if powered:
                p_value = float(
                    fisher_exact(
                        [[a_visible, n_visible - a_visible], [a_control, n_control - a_control]],
                        alternative="two-sided",
                    ).pvalue
                )
            rows.append(
                {
                    "study_id": study_id,
                    "contrast": f"provider_visible_minus_{control_arm}",
                    "visible_events": n_visible,
                    "control_events": n_control,
                    "visible_ordered_actions": a_visible,
                    "control_ordered_actions": a_control,
                    "risk_difference": a_visible / n_visible - a_control / n_control
                    if n_visible and n_control
                    else np.nan,
                    "fisher_exact_p_value": p_value,
                    "power_gated": not powered,
                }
            )
    return pd.DataFrame(rows, columns=columns)


def summarize(panel: pd.DataFrame, effects: pd.DataFrame) -> dict:
    arm_counts = (
        panel["experiment_arm"].value_counts().sort_index().astype(int).to_dict()
        if not panel.empty
        else {}
    )
    required_arms_present = all(arm_counts.get(arm, 0) > 0 for arm in ARMS)
    powered = all(arm_counts.get(arm, 0) >= MIN_EVENTS_PER_RANDOMIZED_ARM for arm in ARMS)
    if panel.empty:
        status = "not_collected"
    elif not required_arms_present:
        status = "observational_timing_only"
    elif not powered:
        status = "randomized_signal_power_gated"
    else:
        status = "signal_arm_coverage_ready"
    return {
        "evidence_status": status,
        "n_decision_events": int(len(panel)),
        "n_actions_observed": int(panel["action_observed"].sum()) if not panel.empty else 0,
        "n_actions_in_selection_window": int(panel["action_in_selection_window"].sum())
        if not panel.empty
        else 0,
        "n_ordered_preselection_actions": int(panel["ordered_preselection_action"].sum())
        if not panel.empty
        else 0,
        "arm_counts": arm_counts,
        "min_events_per_randomized_arm": MIN_EVENTS_PER_RANDOMIZED_ARM,
        "contrast_rows": int(len(effects)),
        "claim_boundary": (
            "Timestamp ordering alone is association evidence. "
            "A literal pre-selection information claim requires a verifiable "
            "provider-visible signal plus visible, blinded, and decoy arms linked to an "
            "immutable randomization manifest. "
            "This audit never establishes customer harm, profit, or market-wide behavior."
        ),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = decision_window_panel(load_events())
    effects = arm_effects(panel)
    save(panel, out_dir, "h70_preselection_timing_panel")
    save(effects, out_dir, "h70_preselection_arm_effects")
    summary = summarize(panel, effects)
    save_json(summary, out_dir, "h70_summary")
    return summary
