"""Build the EC paper's audit figure from checked-in aggregate evidence.

The figure deliberately excludes request-level rows and unobserved welfare
quantities.  Every plotted point comes from one of the immutable aggregate
summaries named below.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HOSTED = Path(__file__).with_name("hosted-evidence.json")
ADAPTIVE = (
    ROOT
    / "data/analysis/adaptive-router-counterfactual/adaptive-router-summary.json"
)


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    wf16 = read_json(HOSTED)["wf16"]
    adaptive = read_json(ADAPTIVE)

    order = [
        "active_undercutter",
        "anchor_adopter",
        "premium_differentiated",
        "static_discounter",
    ]
    labels = ["Active\nundercutter", "Anchor\nadopter", "Premium", "Static\ndiscounter"]
    colors = ["#a44a3f", "#577590", "#6a4c93", "#2a9d8f"]

    persistence = wf16["persistence_by_type"]
    rates = np.array([persistence[key]["rate"] for key in order])
    intervals = np.array([persistence[key]["rate_95ci"] for key in order])
    errors = np.vstack((rates - intervals[:, 0], intervals[:, 1] - rates))

    response = wf16["active_response_vs_shifted_placebo"]
    response_rates = np.array(
        [response["observed"]["response_rate"], response["shifted_placebo"]["response_rate"]]
    )
    response_ci = np.array(
        [
            response["observed"]["response_rate_95ci"],
            response["shifted_placebo"]["response_rate_95ci"],
        ]
    )
    response_err = np.vstack(
        (response_rates - response_ci[:, 0], response_ci[:, 1] - response_rates)
    )

    plt.rcParams.update(
        {
            "font.size": 8,
            "axes.titlesize": 9,
            "axes.labelsize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "figure.dpi": 180,
        }
    )
    fig, axes = plt.subplots(1, 3, figsize=(7.15, 2.35), constrained_layout=True)

    x = np.arange(len(order))
    axes[0].bar(x, rates, color=colors, width=0.72)
    axes[0].errorbar(x, rates, yerr=errors, fmt="none", color="black", capsize=2, lw=0.8)
    axes[0].set_xticks(x, labels)
    axes[0].set_ylim(0, 1.08)
    axes[0].set_ylabel("Holdout persistence")
    axes[0].set_title("A. Regimes, not provider types")
    axes[0].axhline(0.5, color="#999999", lw=0.6, ls="--")

    x2 = np.arange(2)
    axes[1].bar(x2, response_rates, color=["#a44a3f", "#b8b8b8"], width=0.62)
    axes[1].errorbar(
        x2,
        response_rates,
        yerr=response_err,
        fmt="none",
        color="black",
        capsize=2,
        lw=0.8,
    )
    axes[1].set_xticks(x2, ["Registered\nwindow", "Shifted\nplacebo"])
    axes[1].set_ylim(0, 0.56)
    axes[1].set_ylabel("Rival response rate")
    axes[1].set_title("B. No detectable active response")
    axes[1].text(
        0.5,
        0.525,
        r"diff. $=0.0019$, one-sided $p=0.468$",
        ha="center",
        va="top",
        fontsize=7,
    )

    metrics = np.array(
        [
            adaptive["holdout_coupling_reduction_pct"],
            adaptive["holdout_quote_premium_pct"],
            adaptive["holdout_reliability_change_pp"],
        ]
    )
    axes[2].barh(
        np.arange(3),
        metrics,
        color=["#2a9d8f", "#e9c46a", "#577590"],
        height=0.6,
    )
    axes[2].set_yticks(
        np.arange(3),
        ["Coupling proxy\nreduction (%)", "Quote premium\n(%)", "Reliability\nchange (pp)"],
    )
    axes[2].invert_yaxis()
    axes[2].set_xlabel("Held-out mechanical replay")
    axes[2].set_title("C. Adaptive score: trade-off, not welfare")
    for index, value in enumerate(metrics):
        axes[2].text(value + 0.8, index, f"{value:.3g}", va="center", fontsize=7)
    axes[2].set_xlim(0, 56)

    for axis in axes:
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.grid(axis="y", color="#dddddd", lw=0.5, alpha=0.7)
        axis.set_axisbelow(True)

    output = Path(__file__).with_name("empirical-audit.pdf")
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
