"""Aggregate-only support and result monitor for the GLM-5.2 market-share HMP study."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import tomllib
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..market_share_hmp import STUDY_ID, provider_key

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "glm52_market_share_hmp_v1.toml"
DEFAULT_OUT = ROOT / "data" / "analysis" / "glm52-market-share-hmp-v1"


def _read(root: Path, name: str) -> pd.DataFrame:
    frames = []
    for path in sorted((root / "curated" / name).glob("dt=*/*.parquet")):
        try:
            frames.append(pq.ParquetFile(path).read().to_pandas())
        except (OSError, pa.ArrowInvalid):
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _latest_events(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty or "event_id" not in events:
        return events
    output = events.copy()
    priority = {"provisional": 0, "multiplicity_finalized": 1, "final": 2}
    output["_status_priority"] = output.get(
        "event_status", pd.Series("final", index=output.index)
    ).map(priority).fillna(0)
    output["_row_order"] = np.arange(len(output))
    output = output.sort_values(
        ["event_id", "_status_priority", "_row_order"], kind="stable"
    ).drop_duplicates("event_id", keep="last")
    return output.drop(columns=["_status_priority", "_row_order"])


def _metadata(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _binomial_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return math.nan, math.nan
    estimate = successes / total
    denominator = 1.0 + z * z / total
    center = (estimate + z * z / (2 * total)) / denominator
    radius = (
        z * math.sqrt(estimate * (1 - estimate) / total + z * z / (4 * total * total)) / denominator
    )
    return max(0.0, center - radius), min(1.0, center + radius)


def _attempt_panel(root: Path) -> pd.DataFrame:
    attempts = _read(root, "glm52_hmp_attempts")
    if attempts.empty:
        attempts = _read(root, "router_route_attempts")
    if attempts.empty or "study_id" not in attempts:
        return pd.DataFrame()
    attempts = attempts[attempts["study_id"].astype(str).eq(STUDY_ID)].copy()
    if attempts.empty:
        return attempts
    metadata = attempts.get("metadata_json", pd.Series("{}", index=attempts.index)).map(_metadata)
    attempts["task_id"] = metadata.map(lambda row: row.get("task_id"))
    attempts["block_id"] = metadata.map(lambda row: row.get("block_id"))
    attempts["registered_event_id"] = metadata.map(lambda row: row.get("event_id"))
    attempts["wave_id"] = metadata.map(lambda row: row.get("wave_id"))
    return attempts


def _event_support(
    events: pd.DataFrame, panel: pd.DataFrame, protocol: dict[str, Any]
) -> pd.DataFrame:
    multiplicities = ("singleton", "pair", "multiple")
    rows = []
    clean = events[events.get("clean_event", False).fillna(False)] if not events.empty else events
    for name in multiplicities:
        event_ids = (
            set(clean.loc[clean["multiplicity"].astype(str).eq(name), "event_id"].astype(str))
            if not clean.empty
            else set()
        )
        selected = (
            panel[panel["registered_event_id"].astype(str).isin(event_ids)]
            if not panel.empty
            else panel
        )
        covered = (
            selected[
                selected["outcome"].astype(str).eq("succeeded")
                & selected["selected_provider"].notna()
            ]
            if not selected.empty
            else selected
        )
        rows.append(
            {
                "multiplicity": name,
                "clean_events": len(event_ids),
                "covered_choices": int(len(covered)),
                "event_gate_passed": len(event_ids)
                >= int(protocol["support"]["minimum_events_per_multiplicity"]),
                "choice_gate_passed": len(covered)
                >= int(protocol["support"]["minimum_choices_per_multiplicity"]),
            }
        )
    return pd.DataFrame(rows)


def _arm_summary(panel: pd.DataFrame, protocol: dict[str, Any]) -> pd.DataFrame:
    columns = [
        "sample_kind",
        "policy",
        "attempts",
        "successful",
        "active_selections",
        "anchor_selections",
        "active_selection_rate",
        "active_rate_ci_low",
        "active_rate_ci_high",
        "mean_cost_usd",
        "mean_latency_ms",
        "fallback_rate",
    ]
    if panel.empty:
        return pd.DataFrame(columns=columns)
    panel = panel.copy()
    panel["sample_kind"] = np.where(
        panel["registered_event_id"].astype(str).str.startswith("mshmp-background-"),
        "background",
        "natural_event",
    )
    active = {provider_key(item) for item in protocol["providers"]["active"]}
    anchors = {provider_key(item) for item in protocol["providers"]["anchors"]}
    successful = panel[
        panel["outcome"].astype(str).eq("succeeded") & panel["selected_provider"].notna()
    ].copy()
    successful["selected_key"] = successful["selected_provider"].map(provider_key)
    rows = []
    policies = list(protocol["arms"]["names"])
    for sample_kind in ("background", "natural_event"):
        kind_panel = panel[panel["sample_kind"].eq(sample_kind)]
        kind_successful = successful[successful["sample_kind"].eq(sample_kind)]
        if kind_panel.empty:
            continue
        for policy in policies:
            attempted = kind_panel[kind_panel["policy"].astype(str).eq(policy)]
            group = kind_successful[kind_successful["policy"].astype(str).eq(policy)]
            active_count = int(group["selected_key"].isin(active).sum())
            anchor_count = int(group["selected_key"].isin(anchors).sum())
            low, high = _binomial_interval(active_count, len(group))
            rows.append(
                {
                    "sample_kind": sample_kind,
                    "policy": policy,
                    "attempts": int(len(attempted)),
                    "successful": int(len(group)),
                    "active_selections": active_count,
                    "anchor_selections": anchor_count,
                    "active_selection_rate": (
                        active_count / len(group) if len(group) else np.nan
                    ),
                    "active_rate_ci_low": low,
                    "active_rate_ci_high": high,
                    "mean_cost_usd": pd.to_numeric(
                        group.get("cost_usd"), errors="coerce"
                    ).mean(),
                    "mean_latency_ms": pd.to_numeric(
                        group.get("latency_ms"), errors="coerce"
                    ).mean(),
                    "fallback_rate": group.get(
                        "fallback_triggered", pd.Series(dtype=float)
                    ).mean(),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _event_panel(
    events: pd.DataFrame, attempts: pd.DataFrame, protocol: dict[str, Any]
) -> pd.DataFrame:
    columns = [
        "event_id",
        "multiplicity",
        "focal_provider",
        "co_cutter_count",
        "co_cutter_share_mass",
        "co_cutter_exposure",
        "covered_choices",
        "active_selection_rate",
        "anchor_selection_rate",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)
    active = {provider_key(item) for item in protocol["providers"]["active"]}
    anchors = {provider_key(item) for item in protocol["providers"]["anchors"]}
    rows = []
    for event in events.drop_duplicates("event_id").to_dict("records"):
        group = (
            attempts[
                attempts["registered_event_id"].astype(str).eq(str(event["event_id"]))
                & attempts["outcome"].astype(str).eq("succeeded")
                & attempts["selected_provider"].notna()
            ]
            if not attempts.empty
            else attempts
        )
        selected = (
            group["selected_provider"].map(provider_key)
            if not group.empty
            else pd.Series(dtype=str)
        )
        rows.append(
            {
                "event_id": str(event["event_id"]),
                "multiplicity": str(event.get("multiplicity") or ""),
                "focal_provider": str(event.get("focal_provider") or ""),
                "co_cutter_count": int(event.get("co_cutter_count") or 0),
                "co_cutter_share_mass": float(event.get("co_cutter_share_mass") or 0.0),
                "co_cutter_exposure": float(event.get("co_cutter_exposure") or 0.0),
                "covered_choices": int(len(group)),
                "active_selection_rate": float(selected.isin(active).mean())
                if len(group)
                else np.nan,
                "anchor_selection_rate": float(selected.isin(anchors).mean())
                if len(group)
                else np.nan,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def gate_outcomes(
    arms: pd.DataFrame,
    event_panel: pd.DataFrame,
    *,
    released: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Withhold outcomes until the frozen support and integrity gate passes."""
    published_arms = arms.copy()
    published_events = event_panel.copy()
    if released:
        return published_arms, published_events
    for column in (
        "successful",
        "active_selections",
        "anchor_selections",
        "active_selection_rate",
        "active_rate_ci_low",
        "active_rate_ci_high",
        "mean_cost_usd",
        "mean_latency_ms",
        "fallback_rate",
    ):
        if column in published_arms:
            published_arms[column] = np.nan
    for column in ("active_selection_rate", "anchor_selection_rate"):
        if column in published_events:
            published_events[column] = np.nan
    return published_arms, published_events


def _plot_public_prices(
    public: pd.DataFrame,
    events: pd.DataFrame,
    *,
    out_dir: Path,
) -> Path:
    figure = out_dir / "glm52_public_relative_price_paths.png"
    fig, axis = plt.subplots(figsize=(10.4, 4.8), constrained_layout=True)
    if public.empty:
        axis.text(0.5, 0.5, "No prospective public snapshots yet", ha="center", va="center")
        axis.set_axis_off()
    else:
        frame = public.copy()
        frame["captured_at"] = pd.to_datetime(frame["captured_at"], utc=True, errors="coerce")
        frame["relative_to_author"] = pd.to_numeric(
            frame["relative_to_author"], errors="coerce"
        )
        frame = frame.dropna(subset=["captured_at", "relative_to_author"])
        active = frame[frame["provider_group"].astype(str).eq("active")]
        palette = plt.get_cmap("tab10")
        for index, (provider, group) in enumerate(active.groupby("provider_name")):
            group = group.sort_values("captured_at")
            axis.plot(
                group["captured_at"],
                group["relative_to_author"],
                lw=1.5,
                color=palette(index % 10),
                label=str(provider),
            )
        anchors = frame[frame["provider_group"].astype(str).eq("anchor")]
        if not anchors.empty:
            anchor_median = anchors.groupby("captured_at")["relative_to_author"].median()
            axis.plot(
                anchor_median.index,
                anchor_median,
                color="#777777",
                lw=1.8,
                linestyle="--",
                label="anchor median",
            )
        axis.axhline(1.0, color="black", lw=1.0, label="model-author quote")
        for row in events.to_dict("records"):
            if str(row.get("event_status")) == "provisional":
                continue
            axis.axvline(
                pd.Timestamp(row["detected_at"]),
                color="#555555" if bool(row.get("clean_event")) else "#bbbbbb",
                lw=0.7,
                alpha=0.45,
            )
        axis.set_ylabel("request-shaped quote / author quote")
        axis.set_xlabel("UTC")
        axis.set_title("Prospective GLM-5.2 public price paths")
        axis.legend(frameon=False, fontsize=8, ncol=3)
        axis.grid(axis="y", alpha=0.2)
    fig.savefig(figure, dpi=180)
    fig.savefig(out_dir / "glm52_public_relative_price_paths.pdf")
    plt.close(fig)
    return figure


def run(
    data_root: Path,
    out_dir: Path = DEFAULT_OUT,
    *,
    config_path: Path = DEFAULT_CONFIG,
    source_revision: str | None = None,
) -> dict[str, Any]:
    payload = config_path.read_bytes()
    protocol = tomllib.loads(payload.decode("utf-8"))
    protocol_sha = hashlib.sha256(payload).hexdigest()
    events = _latest_events(_read(data_root, "glm52_hmp_events"))
    waves = _read(data_root, "glm52_hmp_wave_plans")
    runs = _read(data_root, "glm52_hmp_run_ledger")
    public = _read(data_root, "glm52_hmp_public_panel")
    assignments = _read(data_root, "glm52_hmp_assignments")
    candidates = _read(data_root, "glm52_hmp_candidates")
    attempts = _attempt_panel(data_root)
    support = _event_support(events, attempts, protocol)
    arms = _arm_summary(attempts, protocol)
    event_panel = _event_panel(events, attempts, protocol)

    assignment_tasks = set(assignments.get("task_id", pd.Series(dtype=str)).dropna().astype(str))
    attempt_tasks = set(attempts.get("task_id", pd.Series(dtype=str)).dropna().astype(str))
    joined = len(assignment_tasks & attempt_tasks)
    integrity = joined / len(assignment_tasks) if assignment_tasks else 1.0
    attempted_blocks = set(attempts.get("block_id", pd.Series(dtype=str)).dropna().astype(str))
    candidate_blocks = set(candidates.get("block_id", pd.Series(dtype=str)).dropna().astype(str))
    menu_coverage = (
        len(attempted_blocks & candidate_blocks) / len(attempted_blocks)
        if attempted_blocks
        else 1.0
    )
    pair_counts: dict[str, int] = {}
    if not events.empty:
        for row in events[events.get("clean_event", False).fillna(False)].to_dict("records"):
            co = row.get("co_cutters")
            if isinstance(co, np.ndarray):
                co = co.tolist()
            pair = "|".join(
                [
                    provider_key(row.get("focal_provider")),
                    *sorted(provider_key(item) for item in (co or ["none"])),
                ]
            )
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
    total_pairs = sum(pair_counts.values())
    maximum_pair_share = max(pair_counts.values(), default=0) / total_pairs if total_pairs else 0.0
    clean_events = (
        events[events.get("clean_event", False).fillna(False)]
        if not events.empty
        else events
    )
    provider_pairs = set()
    for row in clean_events.to_dict("records"):
        co = row.get("co_cutters")
        if isinstance(co, np.ndarray):
            co = co.tolist()
        for provider in co or []:
            provider_pairs.add(
                "|".join(sorted((provider_key(row.get("focal_provider")), provider_key(provider))))
            )
    active_keys = {provider_key(item) for item in protocol["providers"]["active"]}
    selected_active_count = 0
    if not attempts.empty and "selected_provider" in attempts:
        selected = attempts.loc[
            attempts["outcome"].astype(str).eq("succeeded"), "selected_provider"
        ].dropna().map(provider_key)
        selected_active_count = int(selected[selected.isin(active_keys)].nunique())
    assignment_duplicates = int(assignments.get("task_id", pd.Series(dtype=str)).duplicated().sum())
    attempt_duplicates = int(attempts.get("task_id", pd.Series(dtype=str)).duplicated().sum())
    protocol_integrity = bool(
        assignments.empty
        or (
            "protocol_sha256" in assignments
            and assignments["protocol_sha256"].notna().all()
            and assignments["protocol_sha256"].astype(str).eq(protocol_sha).all()
        )
    )
    prospective_start = pd.Timestamp(protocol["study"]["prospective_start_utc"])
    healthy_runs = (
        runs[runs.get("source_healthy", False).fillna(False)] if not runs.empty else runs
    )
    last_healthy = (
        pd.to_datetime(healthy_runs["created_at"], utc=True, errors="coerce").max()
        if not healthy_runs.empty and "created_at" in healthy_runs
        else pd.NaT
    )
    accrued_days = (
        max(0.0, (last_healthy - prospective_start).total_seconds() / 86_400)
        if pd.notna(last_healthy)
        else 0.0
    )
    duration_gate = accrued_days >= float(protocol["support"]["confirmatory_days"])
    empirical_gate = bool(
        not support.empty
        and duration_gate
        and support["event_gate_passed"].all()
        and support["choice_gate_passed"].all()
        and len(provider_pairs) >= int(protocol["support"]["minimum_provider_pair_clusters"])
        and selected_active_count >= int(protocol["support"]["minimum_selected_active_providers"])
        and menu_coverage >= float(protocol["support"]["minimum_menu_coverage"])
        and integrity >= float(protocol["support"]["minimum_assignment_integrity"])
        and maximum_pair_share <= float(protocol["support"]["maximum_pair_share"])
        and assignment_duplicates == 0
        and attempt_duplicates == 0
        and protocol_integrity
    )
    published_arms, published_event_panel = gate_outcomes(
        arms,
        event_panel,
        released=empirical_gate,
    )

    simulation_summary_path = out_dir / "simulation" / "market_share_hmp_simulation_summary.json"
    simulation = (
        json.loads(simulation_summary_path.read_text(encoding="utf-8"))
        if simulation_summary_path.is_file()
        else {}
    )
    ms1 = bool(simulation.get("exact_singleton_zero_wedge_passed"))
    claims = {
        "MS1_exact_identity": "passed" if ms1 else "accruing",
        "MS2_public_multiplicity": "not_tested" if not empirical_gate else "pending_analysis",
        "MS3_owned_routing": "not_tested" if not empirical_gate else "pending_analysis",
        "MS4_passive_incidence": "not_tested" if not empirical_gate else "pending_analysis",
        "MS5_memory": "not_tested" if not empirical_gate else "pending_analysis",
        "MS6_mechanism_transport": "not_promoted",
    }
    summary = {
        "study_id": STUDY_ID,
        "protocol_sha256": protocol_sha,
        "source_revision": source_revision,
        "events": int(events["event_id"].nunique()) if not events.empty else 0,
        "clean_events": int(
            events.loc[events.get("clean_event", False).fillna(False), "event_id"].nunique()
        )
        if not events.empty
        else 0,
        "wave_plans": int(len(waves)),
        "public_price_rows": int(len(public)),
        "public_price_snapshots": (
            int(public["source_run_ts"].nunique())
            if not public.empty and "source_run_ts" in public
            else 0
        ),
        "assignments": int(len(assignment_tasks)),
        "attempts": int(len(attempts)),
        "covered_choices": int(
            (
                attempts["outcome"].astype(str).eq("succeeded")
                & attempts["selected_provider"].notna()
            ).sum()
        )
        if not attempts.empty
        else 0,
        "assignment_integrity": integrity,
        "menu_coverage": menu_coverage,
        "maximum_pair_share": maximum_pair_share,
        "accrued_complete_days": int(math.floor(accrued_days)),
        "duration_gate_passed": duration_gate,
        "provider_pair_clusters": len(provider_pairs),
        "selected_active_providers": selected_active_count,
        "assignment_duplicates": assignment_duplicates,
        "attempt_duplicates": attempt_duplicates,
        "protocol_integrity": protocol_integrity,
        "empirical_support_gate_passed": empirical_gate,
        "outcomes_blinded_until_support_gate": not empirical_gate,
        "support_by_multiplicity": support.to_dict("records"),
        "arm_summary": published_arms.to_dict("records"),
        "claim_ladder": claims,
        "market_wide_share_identified": False,
        "provider_algorithm_identified": False,
        "provider_cost_identified": False,
        "collusion_identified": False,
        "communication_identified": False,
        "claim_boundary": (
            "Interim owned-request and public-event support only. No confirmatory HMP, "
            "market-wide share, algorithm, cost, collusion, communication, or welfare claim."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    support.to_parquet(out_dir / "support_by_multiplicity.parquet", index=False)
    published_arms.to_parquet(out_dir / "arm_summary.parquet", index=False)
    published_event_panel.to_parquet(out_dir / "event_aggregate.parquet", index=False)
    (out_dir / "market_share_hmp_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    fig, axes = plt.subplots(2, 2, figsize=(10.4, 7.2), constrained_layout=True)
    x = np.arange(len(support))
    event_target = int(protocol["support"]["minimum_events_per_multiplicity"])
    choice_target = int(protocol["support"]["minimum_choices_per_multiplicity"])
    event_progress = np.minimum(support["clean_events"] / event_target, 1.0)
    choice_progress = np.minimum(support["covered_choices"] / choice_target, 1.0)
    axes[0, 0].bar(x - 0.18, event_progress, 0.36, label=f"events / {event_target}")
    axes[0, 0].bar(x + 0.18, choice_progress, 0.36, label=f"choices / {choice_target}")
    for index, row in support.iterrows():
        if int(row["clean_events"]):
            axes[0, 0].text(
                index - 0.18,
                float(event_progress.iloc[index]) + 0.02,
                str(int(row["clean_events"])),
                ha="center",
                va="bottom",
                fontsize=8,
            )
        if int(row["covered_choices"]):
            axes[0, 0].text(
                index + 0.18,
                float(choice_progress.iloc[index]) + 0.02,
                str(int(row["covered_choices"])),
                ha="center",
                va="bottom",
                fontsize=8,
            )
    axes[0, 0].set_xticks(x, support["multiplicity"])
    axes[0, 0].set_ylim(0, 1.08)
    axes[0, 0].set_ylabel("fraction of frozen gate")
    axes[0, 0].set_title("A. Confirmatory support")
    axes[0, 0].legend(frameon=False, fontsize=8)
    available = published_arms.dropna(subset=["active_selection_rate"])
    if available.empty:
        message = (
            "Outcomes withheld until support gate"
            if len(attempts)
            else "No covered paid choices yet"
        )
        axes[0, 1].text(0.5, 0.5, message, ha="center", va="center")
        axes[0, 1].set_axis_off()
    else:
        y = np.arange(len(available))
        rates = available["active_selection_rate"].to_numpy()
        lower = rates - available["active_rate_ci_low"].to_numpy()
        upper = available["active_rate_ci_high"].to_numpy() - rates
        axes[0, 1].errorbar(rates, y, xerr=np.vstack([lower, upper]), fmt="o", color="#1f4e79")
        arm_labels = available["sample_kind"].str.replace("_", " ") + ": " + available[
            "policy"
        ].str.replace("_", " ")
        axes[0, 1].set_yticks(y, arm_labels)
        axes[0, 1].set_xlim(0, 1)
        axes[0, 1].set_xlabel("active-provider first-choice rate")
    axes[0, 1].set_title("B. Owned routing by randomized menu")
    visible_events = published_event_panel.dropna(subset=["active_selection_rate"])
    if visible_events.empty:
        message = (
            "Outcomes withheld until support gate"
            if len(published_event_panel)
            else "No finalized events yet"
        )
        axes[1, 0].text(0.5, 0.5, message, ha="center", va="center")
        axes[1, 0].set_axis_off()
    else:
        axes[1, 0].scatter(
            visible_events["co_cutter_share_mass"],
            visible_events["active_selection_rate"],
            s=18 + 3 * visible_events["covered_choices"],
            alpha=0.7,
        )
        axes[1, 0].set_xlabel("pre-event co-cutter shadow-share mass")
        axes[1, 0].set_ylabel("owned active-provider choice rate")
    axes[1, 0].set_title("C. Multiplicity exposure")
    axes[1, 1].set_axis_off()
    for index, (label, status) in enumerate(claims.items()):
        color = "#2e7d32" if status == "passed" else "#666666"
        axes[1, 1].text(
            0.04,
            0.9 - index * 0.15,
            f"{label.split('_', 1)[0]}   {status.replace('_', ' ')}",
            color=color,
            fontsize=11,
            family="monospace",
            transform=axes[1, 1].transAxes,
        )
    axes[1, 1].set_title("D. Ordered claim ladder")
    fig.suptitle(
        "GLM-5.2 market-share HMP experiment: support, not promotion",
        y=0.985,
        fontsize=14,
    )
    figure = out_dir / "market_share_hmp_monitor.png"
    fig.savefig(figure, dpi=180)
    fig.savefig(out_dir / "market_share_hmp_monitor.pdf")
    plt.close(fig)

    price_figure = _plot_public_prices(public, events, out_dir=out_dir)
    encoded = base64.b64encode(figure.read_bytes()).decode("ascii")
    price_encoded = base64.b64encode(price_figure.read_bytes()).decode("ascii")
    html = f"""<!doctype html><meta charset=\"utf-8\">
<title>GLM-5.2 market-share HMP</title>
<style>
body{{font:15px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}}
img{{max-width:100%}}
pre{{white-space:pre-wrap;background:#f5f5f5;padding:1rem}}
</style>
<h1>GLM-5.2 market-share HMP experiment</h1>
<p><strong>Boundary:</strong> {summary["claim_boundary"]}</p>
<p>Events: {summary["events"]} ·
Covered owned choices: {summary["covered_choices"]} ·
Confirmatory support: {summary["empirical_support_gate_passed"]}</p>
<img alt=\"market-share HMP support panel\" src=\"data:image/png;base64,{encoded}\">
<h2>Public price paths</h2>
<img alt=\"GLM-5.2 public relative price paths\" src=\"data:image/png;base64,{price_encoded}\">
<h2>Frozen aggregate</h2><pre>{json.dumps(summary, indent=2)}</pre>"""
    (out_dir / "market-share-hmp.html").write_text(html, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.data_root,
                args.out,
                config_path=args.config,
                source_revision=args.source_revision,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
