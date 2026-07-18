"""Missingness-aware presentation of the immutable H81 release bundle.

This module is deliberately separate from the outcome-blind frozen renderer.
It is a post-release recovery path for a marker-bound bundle whose strict
complete-data renderer failed closed.  It never queries source data and never
fills in a missing binary outcome.  The paper-facing objects are identified
sets copied from the released analyzer tables; preregistered randomization and
Holm columns remain unavailable when the released family is incomplete.
"""

from __future__ import annotations

import hashlib
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
SCHEMA_VERSION = "h81-release-missingness-recovery-v1"


def _finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_columns(frame: pd.DataFrame, columns: set[str], *, name: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def _validate_manifest_files(bundle_dir: Path, manifest: dict[str, Any]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for item in manifest.get("files", []):
        relative = str(item.get("path", ""))
        expected = str(item.get("sha256", ""))
        if not relative or not expected:
            raise ValueError("release manifest contains an incomplete file entry")
        path = bundle_dir / relative
        if not path.is_file():
            raise ValueError(f"release bundle is missing manifest file {relative}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"release bundle hash mismatch for {relative}")
        validated[relative] = actual
    if not validated:
        raise ValueError("release manifest contains no payload hashes")
    return validated


def validate_recovery_inputs(
    policy_panel: pd.DataFrame,
    contrasts: pd.DataFrame,
    summary: dict[str, Any],
    manifest: dict[str, Any],
    failure: dict[str, Any],
) -> dict[str, Any]:
    """Validate the immutable raw release without relaxing the frozen analysis."""
    if manifest.get("protocol_version") != "confirmatory-release-v1":
        raise ValueError("unexpected H81 release protocol")
    if manifest.get("study") != "h81" or not manifest.get("first_access_marker_commit"):
        raise ValueError("recovery requires the marker-bound H81 release")
    if not bool(summary.get("outcomes_released")):
        raise ValueError("recovery requires released H81 raw analysis")
    if summary.get("evidence_status") != "randomized_decomposition_ready":
        raise ValueError("H81 randomized decomposition gate did not pass")
    if not bool(summary.get("terminal_gate_block_excluded")):
        raise ValueError("H81 terminal gate block was not excluded")
    if failure.get("status") != "failed_closed_raw_release_preserved":
        raise ValueError("recovery requires the preserved failed-closed presentation artifact")
    if bool(failure.get("automatic_outcome_requery_permitted")):
        raise ValueError("H81 recovery may not permit source outcome requery")

    _require_columns(
        policy_panel,
        {
            "policy",
            "first_position_attempts",
            "success_outcomes_observed",
            "success_outcomes_missing",
            "success_mean_lower_bound",
            "success_mean_upper_bound",
            "success_design_simultaneous_ci_low",
            "success_design_simultaneous_ci_high",
            "treatment_metadata_passes",
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
            "success_difference_design_simultaneous_ci_low",
            "success_difference_design_simultaneous_ci_high",
            "success_difference_treatment_outcome_lower_bound",
            "success_difference_treatment_outcome_upper_bound",
            "randomization_p_greater",
            "holm_p_greater",
        },
        name="contrasts",
    )

    policies = policy_panel.set_index("policy", drop=False)
    estimates = contrasts.set_index("estimand", drop=False)
    if set(POLICY_ORDER) - set(policies.index):
        raise ValueError("H81 recovery is missing a frozen policy arm")
    if set(ESTIMAND_ORDER) - set(estimates.index):
        raise ValueError("H81 recovery is missing a frozen contrast")

    missing_outcomes = 0
    for policy in POLICY_ORDER:
        row = policies.loc[policy]
        n = int(row["first_position_attempts"])
        observed = int(row["success_outcomes_observed"])
        missing = int(row["success_outcomes_missing"])
        if n <= 0 or observed + missing != n:
            raise ValueError(f"H81 recovery has inconsistent outcome counts for {policy}")
        low = float(row["success_mean_lower_bound"])
        high = float(row["success_mean_upper_bound"])
        if not (0.0 <= low <= high <= 1.0):
            raise ValueError(f"H81 recovery has invalid arm bounds for {policy}")
        missing_outcomes += missing
    if missing_outcomes <= 0:
        raise ValueError("missingness recovery must not replace the complete-data renderer")

    primary = estimates[estimates["primary"].astype(bool)]
    if set(primary.index) != {"fallback_option", "hidden_selection"}:
        raise ValueError("H81 recovery does not contain the frozen two-test family")
    if primary["holm_p_greater"].map(_finite).any():
        raise ValueError("H81 recovery cannot promote a partial Holm family")

    for estimand in ESTIMAND_ORDER:
        row = estimates.loc[estimand]
        low = float(row["success_difference_treatment_outcome_lower_bound"])
        high = float(row["success_difference_treatment_outcome_upper_bound"])
        if not (-1.0 <= low <= high <= 1.0):
            raise ValueError(f"H81 recovery has invalid contrast bounds for {estimand}")

    fallback = estimates.loc["fallback_option"]
    selection = estimates.loc["hidden_selection"]
    total = estimates.loc["total_delegation"]
    for suffix in ("lower_bound", "upper_bound"):
        column = f"success_difference_treatment_outcome_{suffix}"
        identity_error = float(total[column]) - float(fallback[column]) - float(selection[column])
        if not math.isclose(identity_error, 0.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"H81 recovery bound identity fails for {suffix}")

    release_blocks = int(summary.get("release_gate_prefix_blocks", 0))
    preterminal_blocks = int(summary.get("confirmatory_prefix_blocks", 0))
    if release_blocks != preterminal_blocks + 1:
        raise ValueError("H81 recovery must exclude exactly one terminal gate block")
    if int(policy_panel["first_position_attempts"].sum()) != preterminal_blocks:
        raise ValueError("H81 recovery arm counts do not sum to the frozen prefix")

    return {
        "schema_version": SCHEMA_VERSION,
        "release_gate_prefix_blocks": release_blocks,
        "confirmatory_prefix_blocks": preterminal_blocks,
        "terminal_gate_block_policy": summary.get("terminal_gate_block_policy"),
        "binary_outcomes_missing": missing_outcomes,
        "primary_holm_family_complete": False,
        "formal_primary_decision_available": False,
        "source_outcome_requery_permitted": False,
        "claim_boundary": (
            "The recovery reports immutable missing-outcome identified sets for the frozen "
            "owned-account prefix. It does not create complete-data point inference, a Holm "
            "decision, market-wide routing, provider intent, equivalence, or welfare evidence."
        ),
    }


def _fmt_set(low: Any, high: Any, *, percentage_points: bool = True) -> str:
    if not (_finite(low) and _finite(high)):
        return "not available"
    scale = 100.0 if percentage_points else 1.0
    left = scale * float(low)
    right = scale * float(high)
    if math.isclose(left, right, rel_tol=0.0, abs_tol=5e-13):
        return f"{left:.1f}"
    return f"[{left:.1f}, {right:.1f}]"


def _write_recovery_table(contrasts: pd.DataFrame, path: Path) -> None:
    indexed = contrasts.set_index("estimand")
    lines = [
        r"\begin{tabular}{lrrlll}",
        r"\toprule",
        r"Estimand & $n_+$ & $n_-$ & ITT identified set (pp) & Design 95\% set & Primary test \\",
        r"\midrule",
    ]
    for estimand in ESTIMAND_ORDER:
        row = indexed.loc[estimand]
        identified = _fmt_set(
            row["success_difference_treatment_outcome_lower_bound"],
            row["success_difference_treatment_outcome_upper_bound"],
        )
        design = _fmt_set(
            row["success_difference_design_simultaneous_ci_low"],
            row["success_difference_design_simultaneous_ci_high"],
        )
        test = "not released" if bool(row["primary"]) else "--"
        lines.append(
            f"{ESTIMAND_LABELS[estimand]} & {int(row['positive_n'])} & "
            f"{int(row['negative_n'])} & {identified} & {design} & {test} \\\\"
        )
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            "% Identified sets assign the one unknown binary outcome to both endpoints. "
            "The frozen primary randomization/Holm family was suppressed and is not reconstructed.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_recovery_paragraph(
    policy_panel: pd.DataFrame,
    contrasts: pd.DataFrame,
    summary: dict[str, Any],
    path: Path,
) -> None:
    policies = policy_panel.set_index("policy")
    estimates = contrasts.set_index("estimand")
    n_row = policies.loc["price_only_no_fallback"]
    f_row = policies.loc["price_order_fallback"]
    d_row = policies.loc["delegated_default"]
    fallback = estimates.loc["fallback_option"]
    selection = estimates.loc["hidden_selection"]
    total = estimates.loc["total_delegation"]
    fallback_set = _fmt_set(
        fallback["success_difference_treatment_outcome_lower_bound"],
        fallback["success_difference_treatment_outcome_upper_bound"],
    )
    selection_set = _fmt_set(
        selection["success_difference_treatment_outcome_lower_bound"],
        selection["success_difference_treatment_outcome_upper_bound"],
    )
    total_set = _fmt_set(
        total["success_difference_treatment_outcome_lower_bound"],
        total["success_difference_treatment_outcome_upper_bound"],
    )
    sentences = [
        "The frozen H81 gate opened after "
        f"{int(summary['release_gate_prefix_blocks'])} intended assignments; the terminal "
        "price-order-fallback block is excluded, leaving "
        f"{int(summary['confirmatory_prefix_blocks'])} preterminal assignments.",
        "No-fallback has "
        f"{int(n_row['success_outcomes_observed'])} observed outcomes among "
        f"{int(n_row['first_position_attempts'])} intended assignments and one unknown binary "
        "outcome, so its success mean is identified only on "
        f"{_fmt_set(n_row['success_mean_lower_bound'], n_row['success_mean_upper_bound'])}"
        r"\%. "
        f"All {int(f_row['first_position_attempts'])} price-order-fallback and all "
        f"{int(d_row['first_position_attempts'])} delegated-default assignments succeeded.",
        "Assigning the unknown outcome to both endpoints places the fallback ITT estimator in "
        f"{fallback_set} percentage points, hidden selection at {selection_set} percentage "
        f"points, and total delegation in {total_set} percentage points.",
        "Under the frozen missing-outcome rule, complete-data randomization tails and the two-test "
        "Holm family are not released; therefore the experiment makes no formal primary rejection "
        "and the zero hidden-selection contrast is not an equivalence result.",
        "These are finite-prefix intention-to-treat results for one owned account and two repeated "
        "models; they do not identify market-wide routing, provider intent, or welfare.",
    ]
    path.write_text("\n".join(sentences) + "\n", encoding="utf-8")


def _plot(policy_panel: pd.DataFrame, contrasts: pd.DataFrame, out_dir: Path) -> None:
    policies = policy_panel.set_index("policy")
    estimates = contrasts.set_index("estimand")
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.1), constrained_layout=True)

    y_policy = np.arange(len(POLICY_ORDER))[::-1]
    colors = ["#4b5563", "#1d4ed8", "#6d28d9"]
    for y, policy, color in zip(y_policy, POLICY_ORDER, colors, strict=True):
        row = policies.loc[policy]
        low = 100.0 * float(row["success_mean_lower_bound"])
        high = 100.0 * float(row["success_mean_upper_bound"])
        axes[0].hlines(y, low, high, color=color, linewidth=5, zorder=2)
        axes[0].plot([low, high], [y, y], "|", color=color, markersize=11, zorder=3)
        axes[0].text(
            min(high + 0.35, 100.25),
            y,
            _fmt_set(row["success_mean_lower_bound"], row["success_mean_upper_bound"]),
            va="center",
            fontsize=8,
        )
    axes[0].set_yticks(
        y_policy,
        [
            f"{POLICY_LABELS[p]}  n={int(policies.loc[p, 'first_position_attempts'])}"
            for p in POLICY_ORDER
        ],
    )
    axes[0].set_xlim(91.5, 101.0)
    axes[0].set_xlabel("Success probability (%)")
    axes[0].set_title("A. Arm success identified sets", loc="left", fontweight="bold")
    axes[0].grid(axis="x", color="#e5e7eb", linewidth=0.8)
    axes[0].spines[["top", "right", "left"]].set_visible(False)
    axes[0].tick_params(axis="y", length=0)

    y_effect = np.arange(len(ESTIMAND_ORDER))[::-1]
    for y, estimand in zip(y_effect, ESTIMAND_ORDER, strict=True):
        row = estimates.loc[estimand]
        low = 100.0 * float(row["success_difference_treatment_outcome_lower_bound"])
        high = 100.0 * float(row["success_difference_treatment_outcome_upper_bound"])
        color = "#b45309" if estimand != "hidden_selection" else "#374151"
        axes[1].hlines(y, low, high, color=color, linewidth=5, zorder=2)
        axes[1].plot([low, high], [y, y], "|", color=color, markersize=11, zorder=3)
        axes[1].text(
            high + 0.18,
            y,
            _fmt_set(
                row["success_difference_treatment_outcome_lower_bound"],
                row["success_difference_treatment_outcome_upper_bound"],
            ),
            va="center",
            fontsize=8,
        )
    axes[1].axvline(0.0, color="#111827", linestyle="--", linewidth=1)
    axes[1].set_yticks(y_effect, [ESTIMAND_LABELS[e] for e in ESTIMAND_ORDER])
    axes[1].set_xlim(-1.5, 8.0)
    axes[1].set_xlabel("Success difference (percentage points)")
    axes[1].set_title("B. Contrast identified sets", loc="left", fontweight="bold")
    axes[1].grid(axis="x", color="#e5e7eb", linewidth=0.8)
    axes[1].spines[["top", "right", "left"]].set_visible(False)
    axes[1].tick_params(axis="y", length=0)
    axes[1].text(
        0.0,
        -0.24,
        "One unknown N-arm outcome; primary randomization/Holm family not released.",
        transform=axes[1].transAxes,
        fontsize=8,
        color="#4b5563",
    )

    fig.savefig(out_dir / "h81_release_recovery.png", dpi=240, bbox_inches="tight")
    fig.savefig(out_dir / "h81_release_recovery.pdf", bbox_inches="tight")
    plt.close(fig)


def recover_release_report(bundle_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Render a missingness-aware report from one immutable release bundle."""
    bundle_dir = Path(bundle_dir)
    out_dir = Path(out_dir)
    manifest_path = bundle_dir / "release_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads((bundle_dir / "h81_summary.json").read_text(encoding="utf-8"))
    failure = json.loads(
        (bundle_dir / "h81_release_report_error.json").read_text(encoding="utf-8")
    )
    policy_panel = pd.read_parquet(bundle_dir / "h81_policy_panel.parquet")
    contrasts = pd.read_parquet(bundle_dir / "h81_contrasts.parquet")
    validated_hashes = _validate_manifest_files(bundle_dir, manifest)
    validation = validate_recovery_inputs(
        policy_panel,
        contrasts,
        summary,
        manifest,
        failure,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_recovery_table(contrasts, out_dir / "h81_release_recovery_table.tex")
    _write_recovery_paragraph(
        policy_panel,
        contrasts,
        summary,
        out_dir / "h81_release_recovery_paragraph.tex",
    )
    _plot(policy_panel, contrasts, out_dir)

    policies = policy_panel.set_index("policy")
    estimates = contrasts.set_index("estimand")
    report = {
        **validation,
        "status": "missingness_aware_recovery_rendered",
        "paper_promotion_scope": "identified_sets_and_missingness_boundary_only",
        "paper_promotion_permitted_under_dated_recovery_amendment": True,
        "source_manifest_sha256": _sha256(manifest_path),
        "source_dataset_revision": manifest["dataset"]["revision"],
        "source_code_commit": manifest["code_commit"],
        "source_first_access_marker_commit": manifest["first_access_marker_commit"],
        "source_release_commit": manifest.get("release_commit"),
        "validated_source_file_hashes": validated_hashes,
        "policy_identified_sets": {
            policy: {
                "n": int(policies.loc[policy, "first_position_attempts"]),
                "outcomes_observed": int(policies.loc[policy, "success_outcomes_observed"]),
                "outcomes_missing": int(policies.loc[policy, "success_outcomes_missing"]),
                "lower": float(policies.loc[policy, "success_mean_lower_bound"]),
                "upper": float(policies.loc[policy, "success_mean_upper_bound"]),
            }
            for policy in POLICY_ORDER
        },
        "contrast_identified_sets": {
            estimand: {
                "positive_n": int(estimates.loc[estimand, "positive_n"]),
                "negative_n": int(estimates.loc[estimand, "negative_n"]),
                "lower": float(
                    estimates.loc[
                        estimand, "success_difference_treatment_outcome_lower_bound"
                    ]
                ),
                "upper": float(
                    estimates.loc[
                        estimand, "success_difference_treatment_outcome_upper_bound"
                    ]
                ),
                "design_simultaneous_ci_low": (
                    float(estimates.loc[estimand, "success_difference_design_simultaneous_ci_low"])
                    if _finite(
                        estimates.loc[
                            estimand, "success_difference_design_simultaneous_ci_low"
                        ]
                    )
                    else None
                ),
                "design_simultaneous_ci_high": (
                    float(
                        estimates.loc[
                            estimand, "success_difference_design_simultaneous_ci_high"
                        ]
                    )
                    if _finite(
                        estimates.loc[
                            estimand, "success_difference_design_simultaneous_ci_high"
                        ]
                    )
                    else None
                ),
                "randomization_p_greater": None,
                "holm_p_greater": None,
            }
            for estimand in ESTIMAND_ORDER
        },
        "files": [
            "h81_release_recovery.pdf",
            "h81_release_recovery.png",
            "h81_release_recovery_table.tex",
            "h81_release_recovery_paragraph.tex",
        ],
    }
    (out_dir / "h81_release_recovery_audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
