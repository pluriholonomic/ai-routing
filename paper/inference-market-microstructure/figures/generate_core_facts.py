"""Render the four-panel paper summary from the frozen paper estimates.

The script deliberately refuses to read ``analysis/h80_summary.json`` because
the local copy is the superseded fixed-order pilot.  The all-position randomized-
order block screen is frozen in ``paper_estimates.json``; carryover-robust
first-position outcomes remain masked until the registered 500-per-arm gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from statsmodels.stats.proportion import proportion_confint


HERE = Path(__file__).resolve().parent


def _bar_panel(ax, rows, title, color, ymax=100.0):
    labels = [row["label"] for row in rows]
    values = [float(row["value_pct"]) for row in rows]
    x = np.arange(len(rows))
    bars = ax.bar(x, values, color=color, width=0.68)
    ax.set_xticks(x, labels, rotation=18, ha="right")
    ax.set_ylim(0, ymax)
    ax.set_ylabel("Percent")
    ax.set_title(title, loc="left", fontweight="bold")
    ax.grid(axis="y", alpha=0.22)
    for bar, value in zip(bars, values, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + ymax * 0.025,
            f"{value:.1f}%",
            ha="center",
            va="bottom",
            fontsize=9,
        )


def main() -> None:
    payload = json.loads((HERE / "paper_estimates.json").read_text())
    panels = payload["panels"]

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 160,
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 6.8), constrained_layout=True)

    _bar_panel(
        axes[0, 0],
        panels["pricing_state"],
        "A. Money quotes are sticky; operational state moves",
        "#4C78A8",
    )
    _bar_panel(
        axes[0, 1],
        panels["tie_null"],
        "B. Minimum-price ties exceed grid nulls",
        ["#E45756", "#9D9D9D", "#B8B8B8"],
        ymax=60.0,
    )

    rows = panels["probe_success"]
    labels = [row["label"] for row in rows]
    successes = np.asarray([int(row["success"]) for row in rows])
    attempts = np.asarray([int(row["attempts"]) for row in rows])
    rates = successes / attempts
    lows, highs = proportion_confint(successes, attempts, alpha=0.05, method="wilson")
    x = np.arange(len(rows))
    bars = axes[1, 0].bar(x, 100 * rates, color=["#59A14F", "#F28E2B", "#F28E2B", "#F28E2B"])
    axes[1, 0].errorbar(
        x,
        100 * rates,
        yerr=np.vstack((100 * (rates - lows), 100 * (highs - rates))),
        fmt="none",
        ecolor="#222222",
        capsize=3,
        linewidth=1,
    )
    axes[1, 0].set_xticks(x, labels, rotation=18, ha="right")
    axes[1, 0].set_ylim(60, 106)
    axes[1, 0].set_ylabel("Success rate (%)")
    axes[1, 0].set_title(
        "C. Randomized-order block success (secondary)",
        loc="left",
        fontweight="bold",
    )
    axes[1, 0].grid(axis="y", alpha=0.22)
    for bar, success, attempts_i, rate in zip(bars, successes, attempts, rates, strict=True):
        axes[1, 0].text(
            bar.get_x() + bar.get_width() / 2,
            100 * rate + 0.8,
            f"{100 * rate:.1f}%\n({success}/{attempts_i})",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    _bar_panel(
        axes[1, 1],
        panels["steering"],
        "D. Default selection penalizes recent cutters",
        ["#76B7B2", "#E15759"],
        ymax=30.0,
    )

    fig.suptitle(
        "Inference-market microstructure: frozen evidence and audits",
        fontsize=14,
        fontweight="bold",
    )
    fig.savefig(HERE / "core_facts.pdf", bbox_inches="tight")
    fig.savefig(HERE / "core_facts.png", bbox_inches="tight")


if __name__ == "__main__":
    main()
