"""Run and package the preregistered WF-18 signal-coupling simulation."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from .signal_coupling import SignalCouplingConfig, run_factorial, stage_payoffs

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "hmp_signal_coupling_v1.toml"
DEFAULT_OUT = ROOT / "analysis" / "hmp-signal-coupling-v1" / "simulation"


def run(
    out_dir: Path = DEFAULT_OUT,
    *,
    config_path: Path = DEFAULT_CONFIG,
    seeds: int | None = None,
) -> dict:
    payload = config_path.read_bytes()
    protocol = tomllib.loads(payload.decode("utf-8"))
    frame = run_factorial(protocol, seeds=seeds)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out_dir / "wf18_simulation_factorial.parquet", index=False)
    paired = frame.pivot_table(
        index=[
            "signal_to_noise",
            "common_correlation",
            "reward_memory",
            "router_eta",
            "algorithms",
            "seed",
        ],
        columns="arm",
        values=[
            "exploration_innovation_correlation",
            "innovation_correlation",
            "all_high_share",
            "mean_price",
            "mean_provider_reward",
        ],
    ).reset_index()
    paired.columns = [
        "__".join(str(part) for part in column if str(part))
        if isinstance(column, tuple)
        else str(column)
        for column in paired.columns
    ]
    for outcome in (
        "exploration_innovation_correlation",
        "innovation_correlation",
        "all_high_share",
        "mean_price",
        "mean_provider_reward",
    ):
        paired[f"{outcome}__coupled_minus_shuffled"] = (
            paired[f"{outcome}__coupled"] - paired[f"{outcome}__marginal_preserving_shuffle"]
        )
    paired.to_parquet(out_dir / "wf18_simulation_paired_interventions.parquet", index=False)
    grouped = paired.groupby(
        ["signal_to_noise", "common_correlation", "algorithms"], as_index=False
    )[
        [
            "exploration_innovation_correlation__coupled_minus_shuffled",
            "innovation_correlation__coupled_minus_shuffled",
            "all_high_share__coupled_minus_shuffled",
            "mean_price__coupled_minus_shuffled",
        ]
    ].mean()
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 3.8), constrained_layout=True)
    outcomes = [
        (
            "exploration_innovation_correlation__coupled_minus_shuffled",
            "Exploration coupling",
        ),
        ("all_high_share__coupled_minus_shuffled", "All-high state share"),
        ("mean_price__coupled_minus_shuffled", "Buyer price"),
    ]
    for axis, (column, title) in zip(axes, outcomes, strict=True):
        for (correlation, algorithms), group in grouped.groupby(
            ["common_correlation", "algorithms"]
        ):
            axis.plot(
                group["signal_to_noise"],
                group[column],
                marker="o",
                alpha=0.75,
                label=f"rho={correlation:g}, {algorithms}",
            )
        axis.axhline(0, color="black", lw=0.8)
        axis.set_xscale("log", base=2)
        axis.set_xlabel("reward signal-to-noise")
        axis.set_title(title)
    axes[0].set_ylabel("coupled minus marginal-preserving shuffle")
    axes[-1].legend(frameon=False, fontsize=6, bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.suptitle("WF-18 calibrated simulation: exact signal-order intervention")
    fig.savefig(out_dir / "wf18_signal_coupling_simulation.png", dpi=180)
    fig.savefig(out_dir / "wf18_signal_coupling_simulation.pdf")
    plt.close(fig)
    focal = stage_payoffs(SignalCouplingConfig())
    effects = {
        column: {
            "mean": float(paired[column].mean()),
            "positive_share": float((paired[column] > 0).mean()),
        }
        for column in (
            "exploration_innovation_correlation__coupled_minus_shuffled",
            "innovation_correlation__coupled_minus_shuffled",
            "all_high_share__coupled_minus_shuffled",
            "mean_price__coupled_minus_shuffled",
            "mean_provider_reward__coupled_minus_shuffled",
        )
    }
    focal_rows = paired[
        (paired["algorithms"] == "ucb_ucb")
        & (paired["router_eta"] == 5.0)
        & (paired["common_correlation"] > 0)
        & (paired["signal_to_noise"] >= 2.0)
    ]
    heterogeneous_rows = paired[
        (paired["algorithms"] != "ucb_ucb")
        & (paired["common_correlation"] > 0)
        & (paired["signal_to_noise"] >= 2.0)
    ]

    def screen(rows: pd.DataFrame) -> dict:
        columns = (
            "exploration_innovation_correlation__coupled_minus_shuffled",
            "all_high_share__coupled_minus_shuffled",
            "mean_price__coupled_minus_shuffled",
        )
        return {
            column: {
                "mean": float(rows[column].mean()) if not rows.empty else None,
                "positive_share": float((rows[column] > 0).mean()) if not rows.empty else None,
            }
            for column in columns
        }

    focal_screen = screen(focal_rows)
    heterogeneous_screen = screen(heterogeneous_rows)
    primary_pass = bool(
        focal_screen["exploration_innovation_correlation__coupled_minus_shuffled"]["mean"]
        is not None
        and focal_screen["exploration_innovation_correlation__coupled_minus_shuffled"]["mean"] > 0
        and focal_screen["all_high_share__coupled_minus_shuffled"]["mean"] > 0
        and focal_screen["mean_price__coupled_minus_shuffled"]["mean"] > 0
        and focal_screen["mean_price__coupled_minus_shuffled"]["positive_share"] >= 0.60
    )
    heterogeneous_pass = bool(
        heterogeneous_screen["mean_price__coupled_minus_shuffled"]["mean"] is not None
        and heterogeneous_screen["mean_price__coupled_minus_shuffled"]["mean"] > 0
        and heterogeneous_screen["mean_price__coupled_minus_shuffled"]["positive_share"] >= 0.60
    )
    summary = {
        "study_id": protocol["study"]["id"],
        "protocol_sha256": hashlib.sha256(payload).hexdigest(),
        "factorial_rows": int(len(frame)),
        "paired_cells": int(len(paired)),
        "focal_stage_payoffs": focal,
        "paired_effects": effects,
        "focal_hmp_screen": focal_screen,
        "heterogeneous_algorithm_screen": heterogeneous_screen,
        "primary_mechanism_screen_passed": primary_pass,
        "heterogeneous_robustness_passed": heterogeneous_pass,
        "mechanism_validated": bool(primary_pass and heterogeneous_pass),
        "claim_boundary": (
            "The causal signal-order intervention is simulated. Transport to live providers "
            "requires the separately gated WF18 empirical property tests."
        ),
    }
    (out_dir / "wf18_simulation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--seeds", type=int)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.out, config_path=args.config, seeds=args.seeds), indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
