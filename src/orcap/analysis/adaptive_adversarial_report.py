"""Build an evidence-bounded scorecard from adversarial router studies."""

from __future__ import annotations

import argparse
import html
import json
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_REPLAY = Path(
    "data/analysis/adaptive-router-adversarial/adaptive-adversarial-summary.json"
)
DEFAULT_SIMULATION = Path(
    "data/analysis/adaptive-router-adversarial-simulation/"
    "adaptive-adversarial-simulation-summary.json"
)
DEFAULT_OUT = Path("data/analysis/adaptive-router-adversarial-scorecard")


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _rows_by_policy(payload: dict[str, Any] | None, key: str) -> dict[str, dict[str, Any]]:
    if not payload:
        return {}
    return {str(row["policy"]): row for row in payload.get(key, [])}


def _ratio(candidate: Any, baseline: Any) -> float | None:
    if candidate is None or baseline is None:
        return None
    denominator = float(baseline)
    if abs(denominator) <= 1e-15:
        return None
    return float(candidate) / denominator


def build_scorecard(
    *,
    replay_path: Path = DEFAULT_REPLAY,
    simulation_path: Path = DEFAULT_SIMULATION,
    out_dir: Path = DEFAULT_OUT,
    source_revision: str | None = None,
    protocol_config: Path | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    replay = _load(replay_path)
    simulation = _load(simulation_path)
    historical = _rows_by_policy(replay, "policies")
    strategic = _rows_by_policy(simulation, "policies")
    learning = _rows_by_policy(simulation, "learning")
    q_learning = _rows_by_policy(simulation, "q_learning")
    baseline_h = historical.get("baseline_eta2", {})
    hardened_h = historical.get("menu_adaptive_hardened", {})
    baseline_s = strategic.get("baseline_eta2", {})
    hardened_s = strategic.get("menu_adaptive_hardened", {})
    baseline_l = learning.get("baseline_eta2", {})
    hardened_l = learning.get("menu_adaptive_hardened", {})

    comparisons = {
        "historical_mean_max_share_gain_ratio": _ratio(
            hardened_h.get("mean_max_share_gain"),
            baseline_h.get("mean_max_share_gain"),
        ),
        "historical_p95_max_share_gain_ratio": _ratio(
            hardened_h.get("p95_max_share_gain"),
            baseline_h.get("p95_max_share_gain"),
        ),
        "historical_quote_fade_share_ratio": _ratio(
            hardened_h.get("mean_quote_fade_share"),
            baseline_h.get("mean_quote_fade_share"),
        ),
        "historical_sybil_gain_difference": (
            float(hardened_h["mean_sybil_gain"]) - float(baseline_h["mean_sybil_gain"])
            if hardened_h.get("mean_sybil_gain") is not None
            and baseline_h.get("mean_sybil_gain") is not None
            else None
        ),
        "historical_mean_sybil_gain": (
            float(hardened_h["mean_sybil_gain"])
            if hardened_h.get("mean_sybil_gain") is not None
            else None
        ),
        "simulation_mean_unilateral_exploitability_ratio": _ratio(
            hardened_s.get("mean_unilateral_exploitability"),
            baseline_s.get("mean_unilateral_exploitability"),
        ),
        "simulation_p95_unilateral_exploitability_ratio": _ratio(
            hardened_s.get("p95_unilateral_exploitability"),
            baseline_s.get("p95_unilateral_exploitability"),
        ),
        "simulation_mean_coalition_exploitability_ratio": _ratio(
            hardened_s.get("mean_coalition_exploitability"),
            baseline_s.get("mean_coalition_exploitability"),
        ),
        "simulation_p95_coalition_exploitability_ratio": _ratio(
            hardened_s.get("p95_coalition_exploitability"),
            baseline_s.get("p95_coalition_exploitability"),
        ),
        "post_ucb_mean_exploitability_ratio": _ratio(
            hardened_l.get("mean_post_learning_exploitability"),
            baseline_l.get("mean_post_learning_exploitability"),
        ),
        "post_ucb_p95_exploitability_ratio": _ratio(
            hardened_l.get("p95_post_learning_exploitability"),
            baseline_l.get("p95_post_learning_exploitability"),
        ),
    }
    available = replay is not None and simulation is not None
    finite_comparisons = [
        value
        for key, value in comparisons.items()
        if key.endswith("ratio") and value is not None
    ]
    descriptive_nonworsening = bool(
        available and finite_comparisons and all(value <= 1.0 for value in finite_comparisons)
    )
    confirmatory: dict[str, Any] | None = None
    if protocol_config is not None:
        with protocol_config.open("rb") as handle:
            protocol = tomllib.load(handle)
        population = protocol["population"]
        acceptance = protocol["acceptance"]
        replay_window = replay.get("date_window", {}) if replay else {}
        simulation_window = simulation.get("date_window", {}) if simulation else {}
        start = str(population["test_start_date"])
        end = str(population["test_end_date"])
        simulation_observed_min = simulation_window.get("observed_min")
        simulation_observed_max = simulation_window.get("observed_max")
        support_gates = {
            "protocol_is_frozen_future_only": (
                protocol.get("status") == "frozen_future_only"
            ),
            "historical_window_exact": (
                replay_window.get("start_date") == start
                and replay_window.get("end_date") == end
                and replay_window.get("observed_min") == start
                and replay_window.get("observed_max") == end
            ),
            "simulation_window_exact": (
                simulation_window.get("start_date") == start
                and simulation_window.get("end_date") == end
                and isinstance(simulation_observed_min, str)
                and isinstance(simulation_observed_max, str)
                and simulation_observed_min >= start
                and simulation_observed_max <= end
            ),
            "minimum_distinct_dates": bool(
                replay
                and int(replay.get("dates", 0))
                >= int(population["minimum_distinct_dates"])
            ),
            "minimum_historical_menus": bool(
                replay
                and int(replay.get("menus", 0))
                >= int(population["minimum_historical_menus"])
            ),
        }
        threshold_sources = {
            "historical_mean_max_share_gain_ratio_max": (
                "historical_mean_max_share_gain_ratio"
            ),
            "historical_p95_max_share_gain_ratio_max": (
                "historical_p95_max_share_gain_ratio"
            ),
            "historical_quote_fade_share_ratio_max": (
                "historical_quote_fade_share_ratio"
            ),
            "historical_mean_sybil_gain_max": "historical_mean_sybil_gain",
            "simulation_mean_unilateral_exploitability_ratio_max": (
                "simulation_mean_unilateral_exploitability_ratio"
            ),
            "simulation_p95_unilateral_exploitability_ratio_max": (
                "simulation_p95_unilateral_exploitability_ratio"
            ),
            "simulation_mean_coalition_exploitability_ratio_max": (
                "simulation_mean_coalition_exploitability_ratio"
            ),
            "simulation_p95_coalition_exploitability_ratio_max": (
                "simulation_p95_coalition_exploitability_ratio"
            ),
            "post_ucb_mean_exploitability_ratio_max": (
                "post_ucb_mean_exploitability_ratio"
            ),
        }
        metric_gates = {}
        for threshold_name, metric_name in threshold_sources.items():
            observed = comparisons.get(metric_name)
            limit = float(acceptance[threshold_name])
            metric_gates[metric_name] = {
                "observed": observed,
                "maximum": limit,
                "passed": observed is not None and float(observed) <= limit,
            }
        support_passed = all(support_gates.values())
        metrics_passed = all(gate["passed"] for gate in metric_gates.values())
        confirmatory = {
            "study_id": protocol["study_id"],
            "protocol_config": str(protocol_config),
            "support_gates": support_gates,
            "metric_gates": metric_gates,
            "support_passed": support_passed,
            "metrics_passed": metrics_passed,
            "all_gates_passed": support_passed and metrics_passed,
        }
    result = {
        "status": (
            "confirmatory_complete"
            if available and confirmatory is not None and confirmatory["support_passed"]
            else (
                "confirmatory_incomplete"
                if confirmatory is not None
                else ("screening_complete" if available else "awaiting_components")
            )
        ),
        "source_revision": source_revision,
        "historical_available": replay is not None,
        "simulation_available": simulation is not None,
        "historical_support": (
            {
                "menus": replay.get("menus"),
                "models": replay.get("models"),
                "dates": replay.get("dates"),
            }
            if replay
            else None
        ),
        "simulation_support": (
            {
                "menus": simulation.get("menus"),
                "static_cells": simulation.get("static_cells"),
                "learning_runs": simulation.get("learning_runs"),
                "q_learning_runs": simulation.get("q_learning_runs"),
            }
            if simulation
            else None
        ),
        "comparisons_hardened_over_baseline": comparisons,
        "descriptive_all_ratio_metrics_nonworsening": descriptive_nonworsening,
        "q_learning": q_learning,
        "confirmatory": confirmatory,
        "verdict": (
            (
                "future_only_confirmatory_passed"
                if confirmatory["all_gates_passed"]
                else (
                    "future_only_confirmatory_failed"
                    if confirmatory["support_passed"]
                    else "future_only_confirmatory_incomplete"
                )
            )
            if confirmatory is not None
            else (
                "screening_descriptively_nonworsening"
                if descriptive_nonworsening
                else "screening_mixed_or_incomplete"
            )
        ),
        "claim_boundary": (
            (
                "Future-only validation of public-menu attacks and bounded strategic "
                "simulation under the frozen v2 support, deviation, and learner classes. "
                "Passing is not a strategy-proofness, equilibrium, causal provider-response, "
                "collusion, or welfare result."
            )
            if confirmatory is not None
            else (
                "Screening synthesis of public-menu attacks and bounded strategic "
                "simulation. Ratios below one favor the hardened router. The conjunction "
                "is descriptive, not a confirmatory acceptance test, equilibrium proof, "
                "causal provider-response estimate, or welfare result."
            )
        ),
    }
    (out_dir / "adaptive-adversarial-scorecard.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Adaptive-router adversarial scorecard",
        "",
        f"Status: **{result['status']}**. Verdict: **{result['verdict']}**.",
        "",
        "Ratios below one favor the hardened router relative to inverse-square routing.",
        "",
        "| Quantity | Hardened / baseline |",
        "|---|---:|",
    ]
    for key, value in comparisons.items():
        label = key.replace("_", " ")
        rendered = "—" if value is None else f"{float(value):.4f}"
        lines.append(f"| {label} | {rendered} |")
    if confirmatory is not None:
        lines.extend(
            [
                "",
                "## Frozen future-only gates",
                "",
                "| Gate | Observed | Maximum | Pass |",
                "|---|---:|---:|:---:|",
            ]
        )
        for name, gate in confirmatory["metric_gates"].items():
            observed = gate["observed"]
            rendered = "—" if observed is None else f"{float(observed):.4f}"
            lines.append(
                f"| {name.replace('_', ' ')} | {rendered} | "
                f"{float(gate['maximum']):.4f} | {'yes' if gate['passed'] else 'no'} |"
            )
    lines.extend(["", result["claim_boundary"], ""])
    markdown = "\n".join(lines)
    (out_dir / "README.md").write_text(markdown, encoding="utf-8")
    body = "".join(
        f"<tr><td>{html.escape(key.replace('_', ' '))}</td>"
        f"<td>{'—' if value is None else f'{float(value):.4f}'}</td></tr>"
        for key, value in comparisons.items()
    )
    gate_body = ""
    if confirmatory is not None:
        gate_body = "<h2>Frozen future-only gates</h2><table><thead><tr>" + (
            "<th>Gate</th><th>Observed</th><th>Maximum</th><th>Pass</th></tr></thead><tbody>"
        )
        for name, gate in confirmatory["metric_gates"].items():
            observed = gate["observed"]
            rendered = "—" if observed is None else f"{float(observed):.4f}"
            gate_body += (
                f"<tr><td>{html.escape(name.replace('_', ' '))}</td>"
                f"<td>{rendered}</td><td>{float(gate['maximum']):.4f}</td>"
                f"<td>{'yes' if gate['passed'] else 'no'}</td></tr>"
            )
        gate_body += "</tbody></table>"
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Adaptive-router adversarial scorecard</title>
<style>body{{font:16px system-ui;max-width:960px;margin:40px auto;padding:0 20px;color:#17202a}}
table{{border-collapse:collapse;width:100%}}
td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}
.card{{padding:18px;border:1px solid #ddd;border-radius:10px;margin:18px 0}}
code{{background:#f4f4f4;padding:2px 4px}}</style>
</head>
<body><h1>Adaptive-router adversarial scorecard</h1>
<div class="card"><b>Status:</b> {html.escape(result['status'])}<br>
<b>Verdict:</b> {html.escape(result['verdict'])}</div>
<p>Ratios below one favor the hardened router.</p>
<table><thead><tr><th>Quantity</th><th>Hardened / baseline</th></tr></thead>
<tbody>{body}</tbody></table>
{gate_body}
<p>{html.escape(result['claim_boundary'])}</p></body></html>"""
    (out_dir / "adaptive-adversarial-scorecard.html").write_text(
        document, encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    parser.add_argument("--simulation", type=Path, default=DEFAULT_SIMULATION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-revision")
    parser.add_argument("--protocol-config", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            build_scorecard(
                replay_path=args.replay,
                simulation_path=args.simulation,
                out_dir=args.output_dir,
                source_revision=args.source_revision,
                protocol_config=args.protocol_config,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
