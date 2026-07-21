"""Build the ICML critical-memory figure from theory and frozen E-SIM6 rows."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from orcap.market_env.critical_memory import expected_option_transitions, expected_run_wait

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    frame = pd.read_parquet(ROOT / "analysis/sm3_esim6_delayed_credit.parquet")
    grouped = (
        frame.groupby(["memory", "arm"], as_index=False)
        .agg(
            success=("first_action_agrees_exact", "mean"),
            normalized_regret=("normalized_regret", "mean"),
        )
        .sort_values(["memory", "arm"])
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

    memories = np.arange(1, 13)
    for q, color in [(0.1, "#a44a3f"), (0.2, "#6a4c93"), (0.3, "#577590")]:
        axes[0].plot(
            memories,
            [expected_run_wait(int(memory), q) for memory in memories],
            marker="o",
            ms=2.5,
            label=rf"primitive $q={q:g}$",
            color=color,
        )
    axes[0].plot(
        memories,
        [expected_option_transitions(int(memory), 0.1) for memory in memories],
        color="#2a9d8f",
        lw=2,
        label=r"option $q_o=0.1$",
    )
    axes[0].set_yscale("log")
    axes[0].set_xlabel("Router memory M")
    axes[0].set_ylabel("Expected primitive transitions")
    axes[0].set_title("A. Exponential discovery gap")
    axes[0].legend(frameon=False, fontsize=6)

    colors = {"Primitive Q": "#a44a3f", "Commit option Q": "#2a9d8f"}
    for arm, arm_frame in grouped.groupby("arm"):
        axes[1].plot(
            arm_frame["memory"],
            arm_frame["success"],
            marker="o",
            label=arm,
            color=colors[arm],
        )
        axes[2].plot(
            arm_frame["memory"],
            arm_frame["normalized_regret"],
            marker="o",
            label=arm,
            color=colors[arm],
        )
    for axis in axes[1:]:
        axis.axvline(9.2402, color="#555555", ls="--", lw=0.8)
        axis.text(9.35, axis.get_ylim()[1] * 0.92, r"$M^*$", fontsize=7, va="top")
        axis.set_xlabel("Router memory M")
        axis.legend(frameon=False, fontsize=6)
    axes[1].set_ylabel("Exact first-action rate")
    axes[1].set_ylim(-0.05, 1.08)
    axes[1].set_title("B. Frozen Q-learning sweep")
    axes[2].set_ylabel("Mean normalized regret")
    axes[2].set_title("C. Option helps, then overcorrects")

    for axis in axes:
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.grid(axis="y", color="#dddddd", lw=0.5, alpha=0.7)
        axis.set_axisbelow(True)

    fig.savefig(Path(__file__).with_name("critical-memory.pdf"), bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
