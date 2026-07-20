"""Build an evidence-bounded scorecard from adversarial router studies."""

from __future__ import annotations

import argparse
import html
import json
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
        "post_ucb_exploitability_ratio": _ratio(
            hardened_l.get("mean_post_learning_exploitability"),
            baseline_l.get("mean_post_learning_exploitability"),
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
    result = {
        "status": "screening_complete" if available else "awaiting_components",
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
        "verdict": (
            "screening_descriptively_nonworsening"
            if descriptive_nonworsening
            else "screening_mixed_or_incomplete"
        ),
        "claim_boundary": (
            "Screening synthesis of public-menu attacks and bounded strategic simulation. "
            "Ratios below one favor the hardened router. The conjunction is descriptive, "
            "not a confirmatory acceptance test, equilibrium proof, causal provider-response "
            "estimate, or welfare result."
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
    lines.extend(["", result["claim_boundary"], ""])
    markdown = "\n".join(lines)
    (out_dir / "README.md").write_text(markdown, encoding="utf-8")
    body = "".join(
        f"<tr><td>{html.escape(key.replace('_', ' '))}</td>"
        f"<td>{'—' if value is None else f'{float(value):.4f}'}</td></tr>"
        for key, value in comparisons.items()
    )
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
    args = parser.parse_args()
    print(
        json.dumps(
            build_scorecard(
                replay_path=args.replay,
                simulation_path=args.simulation,
                out_dir=args.output_dir,
                source_revision=args.source_revision,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
