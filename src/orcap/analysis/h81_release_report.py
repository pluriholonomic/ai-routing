"""Frozen presentation layer for the one-time H81 confirmatory release.

The analyzer owns all estimands and inference.  This module only validates its
released outputs and renders a deterministic table, figure, and neutral LaTeX
paragraph.  It must never be called on a blinded/accruing result.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

POLICY_ORDER = (
    "price_only_no_fallback",
    "price_order_fallback",
    "delegated_default",
)
POLICY_LABELS = {
    "price_only_no_fallback": "No fallback (N)",
    "price_order_fallback": "Price-order fallback (F)",
    "delegated_default": "Delegated default (D)",
}
ESTIMAND_ORDER = ("fallback_option", "hidden_selection", "total_delegation")
ESTIMAND_LABELS = {
    "fallback_option": "Fallback option (F - N)",
    "hidden_selection": "Hidden selection (D - F)",
    "total_delegation": "Total delegation (D - N)",
}
REPORT_SCHEMA_VERSION = "h81-release-report-v1"
REPORT_FAILURE_SCHEMA_VERSION = "h81-release-report-failure-v1"


def _finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _fmt_number(value: Any, *, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}" if _finite(value) else "NA"


def _fmt_pp(value: Any, *, digits: int = 1) -> str:
    return f"{100.0 * float(value):.{digits}f}" if _finite(value) else "NA"


def _fmt_p(value: Any) -> str:
    if not _finite(value):
        return "NA"
    result = float(value)
    return "$<0.001$" if result < 0.001 else f"{result:.3f}"


def _fmt_interval(low: Any, high: Any, *, percentage_points: bool = True) -> str:
    if not (_finite(low) and _finite(high)):
        return "NA"
    scale = 100.0 if percentage_points else 1.0
    return f"[{scale * float(low):.1f}, {scale * float(high):.1f}]"


def _require_columns(frame: pd.DataFrame, required: set[str], *, name: str) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required release columns: {missing}")


def validate_release_outputs(
    policy_panel: pd.DataFrame,
    contrasts: pd.DataFrame,
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed unless the H81 result is complete and algebraically coherent."""
    if not bool(summary.get("outcomes_released")):
        raise ValueError("H81 release report requires outcomes_released=true")
    if summary.get("evidence_status") != "randomized_decomposition_ready":
        raise ValueError("H81 release report requires randomized_decomposition_ready")
    if not bool(summary.get("terminal_gate_block_excluded")):
        raise ValueError("H81 release report requires terminal-block exclusion")

    _require_columns(
        policy_panel,
        {
            "policy",
            "first_position_attempts",
            "success_rate",
            "success_design_simultaneous_ci_low",
            "success_design_simultaneous_ci_high",
            "first_row_observation_rate",
            "assignment_replay_rate",
            "treatment_metadata_pass_rate",
            "success_outcomes_missing",
        },
        name="policy_panel",
    )
    _require_columns(
        contrasts,
        {
            "estimand",
            "primary",
            "positive_n",
            "negative_n",
            "success_difference_hajek",
            "success_difference_ht",
            "success_difference_simultaneous_ci_low",
            "success_difference_simultaneous_ci_high",
            "success_difference_design_simultaneous_ci_low",
            "success_difference_design_simultaneous_ci_high",
            "success_difference_treatment_outcome_lower_bound",
            "success_difference_treatment_outcome_upper_bound",
            "randomization_p_greater",
            "randomization_p_two_sided",
            "holm_p_greater",
        },
        name="contrasts",
    )

    policies = policy_panel.set_index("policy", drop=False)
    estimates = contrasts.set_index("estimand", drop=False)
    if set(POLICY_ORDER) - set(policies.index):
        raise ValueError("H81 policy panel does not contain all three frozen policies")
    if set(ESTIMAND_ORDER) - set(estimates.index):
        raise ValueError("H81 contrast panel does not contain all three frozen estimands")

    numeric_policy_columns = (
        "success_rate",
        "success_design_simultaneous_ci_low",
        "success_design_simultaneous_ci_high",
        "first_row_observation_rate",
        "assignment_replay_rate",
        "treatment_metadata_pass_rate",
    )
    for policy in POLICY_ORDER:
        row = policies.loc[policy]
        if int(row["first_position_attempts"]) <= 0:
            raise ValueError(f"H81 policy {policy} has no preterminal assignments")
        if int(row["success_outcomes_missing"]) != 0:
            raise ValueError("H81 complete-data report cannot mask missing binary outcomes")
        if not all(_finite(row[column]) for column in numeric_policy_columns):
            raise ValueError(f"H81 policy {policy} has incomplete released estimates")

    for estimand in ESTIMAND_ORDER:
        row = estimates.loc[estimand]
        required = (
            "success_difference_hajek",
            "success_difference_ht",
            "success_difference_design_simultaneous_ci_low",
            "success_difference_design_simultaneous_ci_high",
            "success_difference_treatment_outcome_lower_bound",
            "success_difference_treatment_outcome_upper_bound",
            "randomization_p_greater",
            "randomization_p_two_sided",
        )
        if not all(_finite(row[column]) for column in required):
            raise ValueError(f"H81 estimand {estimand} has incomplete released inference")
        if not math.isclose(
            float(row["success_difference_hajek"]),
            float(row["success_difference_ht"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(f"H81 estimand {estimand} violates ITT/HT equality")
        for column in ("randomization_p_greater", "randomization_p_two_sided"):
            if not 0.0 <= float(row[column]) <= 1.0:
                raise ValueError(f"H81 estimand {estimand} has an invalid p-value")

    fallback = float(estimates.loc["fallback_option", "success_difference_hajek"])
    selection = float(estimates.loc["hidden_selection", "success_difference_hajek"])
    total = float(estimates.loc["total_delegation", "success_difference_hajek"])
    identity_error = total - fallback - selection
    if not math.isclose(identity_error, 0.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"H81 decomposition identity error is {identity_error}")

    primary = estimates[estimates["primary"].astype(bool)]
    if set(primary.index) != {"fallback_option", "hidden_selection"}:
        raise ValueError("H81 release must contain exactly the two frozen primary contrasts")
    if primary["holm_p_greater"].map(_finite).sum() != 2:
        raise ValueError("H81 primary contrasts require Holm-adjusted directional p-values")
    if (
        pd.to_numeric(primary["holm_p_greater"], errors="coerce") + 1e-15
        < pd.to_numeric(primary["randomization_p_greater"], errors="coerce")
    ).any():
        raise ValueError("H81 Holm p-values cannot be smaller than raw p-values")

    release_blocks = int(summary.get("release_gate_prefix_blocks", 0))
    confirmatory_blocks = int(summary.get("confirmatory_prefix_blocks", 0))
    if release_blocks != confirmatory_blocks + 1:
        raise ValueError("H81 release must exclude exactly one gate-hitting terminal block")
    if int(policy_panel["first_position_attempts"].sum()) != confirmatory_blocks:
        raise ValueError("H81 arm counts do not equal the preterminal prefix size")

    sensitivity = summary.get("treatment_outcome_missingness_sensitivity") or {}
    for field in (
        "candidate_blocks_preterminal",
        "assigned_policy_reconstructed",
        "treatment_verified",
        "treatment_missing_or_noncompliant",
        "binary_outcome_missing_among_verified",
    ):
        if field not in sensitivity:
            raise ValueError(f"H81 release is missing sensitivity field {field}")

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "release_gate_prefix_blocks": release_blocks,
        "confirmatory_prefix_blocks": confirmatory_blocks,
        "terminal_gate_block_policy": summary.get("terminal_gate_block_policy"),
        "decomposition_identity_error": identity_error,
        "complete_binary_outcomes": True,
        "primary_holm_family_complete": True,
        "treatment_outcome_sensitivity_complete": True,
        "claim_boundary": (
            "Finite-prefix owned-account intended-assignment effects only; the report does not "
            "identify market-wide routing, provider intent, equivalence, or welfare."
        ),
    }


def _write_table(contrasts: pd.DataFrame, path: Path) -> None:
    indexed = contrasts.set_index("estimand")
    lines = [
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"Estimand & $n_+$ & $n_-$ & ITT (pp) & Design 95\% CI & Exact $p_+$ & Holm $p_+$ \\",
        r"\midrule",
    ]
    for estimand in ESTIMAND_ORDER:
        row = indexed.loc[estimand]
        holm = _fmt_p(row["holm_p_greater"]) if bool(row["primary"]) else "--"
        lines.append(
            f"{ESTIMAND_LABELS[estimand]} & {int(row['positive_n'])} & "
            f"{int(row['negative_n'])} & {_fmt_pp(row['success_difference_hajek'])} & "
            f"{_fmt_interval(row['success_difference_design_simultaneous_ci_low'], row['success_difference_design_simultaneous_ci_high'])} "  # noqa: E501
            "& "
            f"{_fmt_p(row['randomization_p_greater'])} & {holm} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            "% ITT is percentage points. Design intervals are simultaneous "
            "finite-population bounds.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_paragraph(
    policy_panel: pd.DataFrame,
    contrasts: pd.DataFrame,
    summary: dict[str, Any],
    path: Path,
) -> None:
    policies = policy_panel.set_index("policy")
    estimates = contrasts.set_index("estimand")
    sensitivity = summary["treatment_outcome_missingness_sensitivity"]
    terminal_policy = str(summary["terminal_gate_block_policy"])
    terminal_label = POLICY_LABELS.get(terminal_policy, terminal_policy)
    sentences = [
        "The frozen H81 gate opened after "
        f"{int(summary['release_gate_prefix_blocks'])} intended assignments. "
        f"We exclude the terminal {terminal_label} block and analyze "
        f"{int(summary['confirmatory_prefix_blocks'])} preterminal assignments.",
        "The preterminal success rates were "
        f"{_fmt_pp(policies.loc['price_only_no_fallback', 'success_rate'])}\\% for no fallback "
        f"($n={int(policies.loc['price_only_no_fallback', 'first_position_attempts'])}$), "
        f"{_fmt_pp(policies.loc['price_order_fallback', 'success_rate'])}\\% for "
        "price-order fallback "
        f"($n={int(policies.loc['price_order_fallback', 'first_position_attempts'])}$), and "
        f"{_fmt_pp(policies.loc['delegated_default', 'success_rate'])}\\% for delegated default "
        f"($n={int(policies.loc['delegated_default', 'first_position_attempts'])}$).",
    ]
    for estimand in ("fallback_option", "hidden_selection"):
        row = estimates.loc[estimand]
        design_interval = _fmt_interval(
            row["success_difference_design_simultaneous_ci_low"],
            row["success_difference_design_simultaneous_ci_high"],
        )
        sentences.append(
            f"The {ESTIMAND_LABELS[estimand].split(' (')[0].lower()} ITT effect was "
            f"{_fmt_pp(row['success_difference_hajek'])} percentage points "
            f"(simultaneous design interval {design_interval}; "
            f"exact one-sided $p={_fmt_number(row['randomization_p_greater'])}$, "
            f"Holm $p={_fmt_number(row['holm_p_greater'])}$)."
        )
    total = estimates.loc["total_delegation"]
    sentences.append(
        "The total delegation contrast was "
        f"{_fmt_pp(total['success_difference_hajek'])} percentage points and equals the sum "
        "of the two component estimates by construction."
    )
    sentences.append(
        "Treatment realization was verified for "
        f"{int(sensitivity['treatment_verified'])} of "
        f"{int(sensitivity['assigned_policy_reconstructed'])} reconstructed preterminal "
        "assignments; "
        f"{int(sensitivity['binary_outcome_missing_among_verified'])} verified assignments "
        "had a missing binary outcome."
    )
    sentences.append(
        "These are finite-prefix owned-account intention-to-treat effects. A nonsignificant "
        "contrast is not evidence of equivalence, and the experiment does not identify "
        "market-wide allocation, provider intent, or welfare."
    )
    path.write_text("\n".join(sentences) + "\n", encoding="utf-8")


def _plot_release(policy_panel: pd.DataFrame, contrasts: pd.DataFrame, out_dir: Path) -> None:
    policies = policy_panel.set_index("policy")
    estimates = contrasts.set_index("estimand")
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.7), constrained_layout=True)

    x = np.arange(len(POLICY_ORDER))
    means = np.asarray([float(policies.loc[policy, "success_rate"]) for policy in POLICY_ORDER])
    lows = np.asarray(
        [
            float(policies.loc[policy, "success_design_simultaneous_ci_low"])
            for policy in POLICY_ORDER
        ]
    )
    highs = np.asarray(
        [
            float(policies.loc[policy, "success_design_simultaneous_ci_high"])
            for policy in POLICY_ORDER
        ]
    )
    colors = ["#6b7280", "#2563eb", "#7c3aed"]
    for index, color in enumerate(colors):
        axes[0].errorbar(
            x[index],
            means[index],
            yerr=np.asarray([[means[index] - lows[index]], [highs[index] - means[index]]]),
            fmt="o",
            color=color,
            ecolor=color,
            markersize=7,
            elinewidth=2.0,
            capsize=4,
            zorder=3,
        )
    axes[0].set_xticks(x, ["N", "F", "D"])
    axes[0].set_ylim(-0.03, 1.03)
    axes[0].set_ylabel("First-request success probability")
    axes[0].set_title("A. Intended-policy arm means")
    axes[0].grid(axis="y", alpha=0.25)
    for index, policy in enumerate(POLICY_ORDER):
        axes[0].text(
            index,
            min(1.0, highs[index] + 0.035),
            f"n={int(policies.loc[policy, 'first_position_attempts'])}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    y = np.arange(len(ESTIMAND_ORDER))[::-1]
    points = np.asarray(
        [float(estimates.loc[estimand, "success_difference_hajek"]) for estimand in ESTIMAND_ORDER]
    )
    design_low = np.asarray(
        [
            float(estimates.loc[estimand, "success_difference_design_simultaneous_ci_low"])
            for estimand in ESTIMAND_ORDER
        ]
    )
    design_high = np.asarray(
        [
            float(estimates.loc[estimand, "success_difference_design_simultaneous_ci_high"])
            for estimand in ESTIMAND_ORDER
        ]
    )
    sensitivity_low = np.asarray(
        [
            float(estimates.loc[estimand, "success_difference_treatment_outcome_lower_bound"])
            for estimand in ESTIMAND_ORDER
        ]
    )
    sensitivity_high = np.asarray(
        [
            float(estimates.loc[estimand, "success_difference_treatment_outcome_upper_bound"])
            for estimand in ESTIMAND_ORDER
        ]
    )
    for index in range(len(ESTIMAND_ORDER)):
        axes[1].hlines(
            y[index], sensitivity_low[index], sensitivity_high[index], color="#cbd5e1", lw=7
        )
        axes[1].hlines(y[index], design_low[index], design_high[index], color="#1f2937", lw=2)
        axes[1].plot(points[index], y[index], "o", color="#dc2626", ms=6)
    axes[1].axvline(0.0, color="#111827", linestyle="--", linewidth=1)
    axes[1].set_yticks(y, [ESTIMAND_LABELS[item] for item in ESTIMAND_ORDER])
    axes[1].set_xlim(-1.03, 1.03)
    axes[1].set_xlabel("ITT success difference")
    axes[1].set_title("B. Decomposition contrasts")
    axes[1].grid(axis="x", alpha=0.25)
    axes[1].text(
        0.01,
        -0.18,
        "Dark: simultaneous design interval; light: treatment/outcome sensitivity bound",
        transform=axes[1].transAxes,
        fontsize=8,
        va="top",
    )

    fig.savefig(out_dir / "h81_release_result.png", dpi=220)
    fig.savefig(out_dir / "h81_release_result.pdf")
    plt.close(fig)


def build_release_report(
    policy_panel: pd.DataFrame,
    model_panel: pd.DataFrame,
    contrasts: pd.DataFrame,
    summary: dict[str, Any],
    *,
    out_dir: Path,
) -> dict[str, Any]:
    """Validate and render the frozen H81 release presentation bundle."""
    out_dir.mkdir(parents=True, exist_ok=True)
    validation = validate_release_outputs(policy_panel, contrasts, summary)
    table_path = out_dir / "h81_release_result_table.tex"
    paragraph_path = out_dir / "h81_release_result_paragraph.tex"
    _write_table(contrasts, table_path)
    _write_paragraph(policy_panel, contrasts, summary, paragraph_path)
    _plot_release(policy_panel, contrasts, out_dir)

    model_count = int(model_panel["model_id"].nunique()) if "model_id" in model_panel else 0
    report = {
        **validation,
        "model_count": model_count,
        "files": [
            "h81_release_result.pdf",
            "h81_release_result.png",
            table_path.name,
            paragraph_path.name,
        ],
        "interpretation_rule": (
            "Report every estimate, interval, and p-value regardless of sign. Statistical "
            "nonsignificance is described as low precision, never equivalence."
        ),
    }
    (out_dir / "h81_release_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def build_release_report_safely(
    policy_panel: pd.DataFrame,
    model_panel: pd.DataFrame,
    contrasts: pd.DataFrame,
    summary: dict[str, Any],
    *,
    out_dir: Path,
) -> dict[str, Any]:
    """Render the paper-facing package without endangering the one-shot bundle.

    The remote transaction commits its irreversible first-outcome-access marker
    before the analyzer runs.  A presentation invariant or plotting failure must
    therefore remain fail-closed for the manuscript while still allowing the
    already-written raw tables and summary to enter the immutable release bundle.
    The strict ``build_release_report`` API continues to raise for direct callers;
    only the one-shot analyzer uses this preservation wrapper.
    """
    try:
        report = build_release_report(
            policy_panel,
            model_panel,
            contrasts,
            summary,
            out_dir=out_dir,
        )
    except Exception as exc:  # noqa: BLE001 - preserve every post-marker failure
        failure = {
            "schema_version": REPORT_FAILURE_SCHEMA_VERSION,
            "status": "failed_closed_raw_release_preserved",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "outcomes_released": bool(summary.get("outcomes_released")),
            "raw_analysis_files_preserved": True,
            "paper_promotion_permitted": False,
            "automatic_outcome_requery_permitted": False,
            "recovery_rule": (
                "Use the immutable raw release tables and a dated amendment; do not query "
                "the source outcomes again."
            ),
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        error_path = out_dir / "h81_release_report_error.json"
        error_path.write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return failure | {"error_artifact": error_path.name}
    return report | {
        "status": "rendered",
        "paper_promotion_permitted": True,
        "automatic_outcome_requery_permitted": False,
    }
