"""Build the NeurIPS environment audit figure from aggregate hosted results."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent


def main() -> None:
    evidence = json.loads((ROOT / "hosted-evidence.json").read_text(encoding="utf-8"))
    wf18 = evidence["wf18"]
    adversarial = evidence["adaptive_adversarial"]

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

    outcomes = ["exploration_coupling", "all_high_share", "buyer_price"]
    labels = ["Exploration\ncoupling", "All-high\nshare", "Buyer\nprice"]
    x = np.arange(3)
    width = 0.36
    focal = [wf18["focal"][key] for key in outcomes]
    heterogeneous = [wf18["heterogeneous"][key] for key in outcomes]
    axes[0].bar(x - width / 2, focal, width, label="UCB/UCB focal", color="#6a4c93")
    axes[0].bar(
        x + width / 2,
        heterogeneous,
        width,
        label="Heterogeneous",
        color="#b8b8b8",
    )
    axes[0].axhline(0, color="black", lw=0.7)
    axes[0].set_xticks(x, labels)
    axes[0].set_ylabel("Coupled minus shuffled")
    axes[0].set_title("A. Signal-order intervention")
    axes[0].legend(frameon=False, fontsize=6, loc="upper right")

    attack_keys = [
        "mean_max_allocation_gain",
        "mean_fading_quote_share",
        "mean_sybil_share_gain",
    ]
    attack_labels = ["Max gain", "Fade share", "Sybil gain"]
    baseline = [adversarial["inverse_square"][key] for key in attack_keys]
    hardened = [adversarial["hardened"][key] for key in attack_keys]
    axes[1].bar(x - width / 2, baseline, width, label="Inverse-square", color="#a44a3f")
    axes[1].bar(x + width / 2, hardened, width, label="Hardened", color="#2a9d8f")
    axes[1].set_xticks(x, attack_labels)
    axes[1].tick_params(axis="x", labelsize=6.5)
    axes[1].set_ylabel("Historical mechanical effect")
    axes[1].set_title("B. One-shot attack resistance")
    axes[1].legend(frameon=False, fontsize=6, loc="upper right")

    exploit_labels = ["Static\nunilateral", "Static two-\nprovider", "Post-UCB\nnormalized"]
    exploit_keys = [
        "mean_unilateral_exploitability",
        "mean_two_provider_exploitability",
        "post_ucb_normalized_exploitability",
    ]
    baseline_exploit = [adversarial["inverse_square"][key] for key in exploit_keys]
    hardened_exploit = [adversarial["hardened"][key] for key in exploit_keys]
    axes[2].bar(
        x - width / 2,
        baseline_exploit,
        width,
        label="Inverse-square",
        color="#a44a3f",
    )
    axes[2].bar(
        x + width / 2,
        hardened_exploit,
        width,
        label="Hardened",
        color="#2a9d8f",
    )
    axes[2].set_xticks(x, exploit_labels)
    axes[2].set_yscale("symlog", linthresh=0.05)
    axes[2].set_ylabel("Residual exploitability")
    axes[2].set_title("C. Static success, learning failure")
    axes[2].legend(frameon=False, fontsize=6, loc="upper left")

    for axis in axes:
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.grid(axis="y", color="#dddddd", lw=0.5, alpha=0.7)
        axis.set_axisbelow(True)

    fig.savefig(ROOT / "environment-audit.pdf", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
