"""Render the frozen nine-day Brown-MacKay identification audit."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
DATA = json.loads((HERE / "frozen_brown_mackay_estimates.json").read_text())

BLUE = "#4C78A8"
ORANGE = "#F28E2B"
RED = "#E45756"
TEAL = "#72B7B2"
GRAY = "#9D9D9D"


def render() -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10.4, 6.7))
    fig.suptitle(
        "Frozen nine-day Brown–MacKay audit: association survives; mechanism is not identified",
        fontsize=14,
        fontweight="bold",
        y=0.985,
    )

    cadence = DATA["cadence_counts"]
    labels = list(cadence)
    values = list(cadence.values())
    axes[0, 0].barh(labels[::-1], values[::-1], color=[GRAY, TEAL, ORANGE, BLUE][::-1])
    for index, value in enumerate(values[::-1]):
        axes[0, 0].text(value + 0.7, index, str(value), va="center", fontsize=9)
    axes[0, 0].set_title("A. Observable repricing cadence")
    axes[0, 0].set_xlabel("Providers")
    axes[0, 0].set_xlim(0, max(values) * 1.18)

    associations = DATA["price_associations"]
    y = np.arange(len(associations))
    beta = np.asarray([item["beta_fast"] for item in associations])
    low = np.asarray([item["ci95"][0] for item in associations])
    high = np.asarray([item["ci95"][1] for item in associations])
    axes[0, 1].errorbar(
        beta,
        y,
        xerr=np.vstack([beta - low, high - beta]),
        fmt="o",
        color=BLUE,
        ecolor=BLUE,
        capsize=4,
        markersize=7,
    )
    axes[0, 1].axvline(0, color="black", linewidth=1, linestyle="--")
    axes[0, 1].set_yticks(y, [item["label"] for item in associations])
    axes[0, 1].invert_yaxis()
    axes[0, 1].set_title("B. Fast-provider log-price association")
    axes[0, 1].set_xlabel(r"$\widehat{\beta}_{fast}$ with 95% interval")
    axes[0, 1].text(
        0.98,
        0.42,
        "Negative = fast providers quote less",
        transform=axes[0, 1].transAxes,
        ha="right",
        fontsize=8.5,
        color="#444444",
    )

    support = DATA["support_counts"]
    support_labels = list(support)
    support_values = list(support.values())
    colors = [BLUE, RED, TEAL, ORANGE]
    axes[1, 0].bar(np.arange(len(support_values)), support_values, color=colors)
    axes[1, 0].set_xticks(
        np.arange(len(support_labels)),
        ["Waves", "Slow-risk\npairs", "Linked\nreactions", "Holdout"],
    )
    for index, value in enumerate(support_values):
        axes[1, 0].text(index, value + 4, str(value), ha="center", fontsize=9)
    axes[1, 0].set_ylim(0, max(support_values) * 1.18)
    axes[1, 0].set_title("C. Identification support after coarsening")
    axes[1, 0].set_ylabel("Count")
    timing = DATA["timing_identification"]
    _, upper = timing["sharp_named_rival_response_share_bounds"]
    axes[1, 0].text(
        0.02,
        0.95,
        f"Named-rival response share\nsharp set: [0, {upper:.1%}]",
        transform=axes[1, 0].transAxes,
        ha="left",
        va="top",
        fontsize=8.5,
        color="#444444",
    )

    predictive = DATA["predictive_test"]
    point = predictive["mse_improvement"]
    lo, hi = predictive["model_cluster_bootstrap_ci95"]
    axes[1, 1].errorbar(
        point,
        0,
        xerr=[[point - lo], [hi - point]],
        fmt="o",
        color=RED,
        ecolor=RED,
        capsize=5,
        markersize=8,
    )
    axes[1, 1].axvline(0, color="black", linewidth=1, linestyle="--")
    axes[1, 1].set_yticks([])
    axes[1, 1].set_title("D. Incremental predictive value")
    axes[1, 1].set_xlabel("State-only MSE minus Brown–MacKay MSE")
    axes[1, 1].set_ylim(-0.55, 0.55)
    axes[1, 1].text(
        0.03,
        0.12,
        "Cluster bootstrap interval is positive, but support is tiny\n"
        f"{predictive['model_clusters']} clusters; exact sign-flip p={predictive['exact_sign_flip_p_positive']:.3f}\n"
        "Verdict: predictively indistinguishable",
        transform=axes[1, 1].transAxes,
        fontsize=9,
        va="bottom",
    )

    for axis in axes.flat:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.18)
    fig.tight_layout(rect=[0, 0, 1, 0.95], h_pad=2.0, w_pad=2.2)
    fig.savefig(HERE / "brown_mackay_audit.pdf", bbox_inches="tight")
    fig.savefig(HERE / "brown_mackay_audit.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    render()
