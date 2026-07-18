"""SM3 — exact and learned responses to a history-dependent routing penalty."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..market_env.state_aliasing import BinaryCutPenaltyMDP
from .common import DEFAULT_OUT, save, save_json

ESIM4 = Path("output/market_env/esim4/fc6f9c8656/results.json")
ESIM5 = Path("output/market_env/esim5/3e5a55405e/results.json")
ESIM6 = Path("output/market_env/esim6/93265b9b03/results.json")
ESIM7 = Path("output/market_env/esim7/bd74ab2eb7/results.json")
ESIM8 = Path("output/market_env/esim8/4d84b9b3a2/results.json")
ESIM9 = Path("output/market_env/esim9/179eca0f9d/results.json")

PRIMITIVE_COLOR = "#315D83"
OPTION_COLOR = "#D78328"
EXACT_COLOR = "#313131"
GRID_COLOR = "#D8D8D8"


def _bootstrap_mean_interval(
    values: np.ndarray, *, seed: int = 20260718, draws: int = 10_000
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(draws, len(values)))
    means = values[indices].mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return float(low), float(high)


def load_panels() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict, dict, dict, dict, dict]:
    esim4 = json.loads(ESIM4.read_text())
    esim5 = json.loads(ESIM5.read_text())
    esim6 = json.loads(ESIM6.read_text())
    esim7 = json.loads(ESIM7.read_text())
    esim8 = json.loads(ESIM8.read_text())
    esim9 = json.loads(ESIM9.read_text())
    sweep_rows: list[dict] = []
    for memory_arm in esim6["sweep"]:
        memory = int(memory_arm["memory"])
        for row in memory_arm["rows"]:
            for arm_key, arm_label in (
                ("primitive_q", "Primitive Q"),
                ("commit_option_q", "Commit option Q"),
            ):
                learned = row[arm_key]
                sweep_rows.append(
                    {
                        "memory": memory,
                        "seed": int(row["seed"]),
                        "arm": arm_label,
                        "exact_action": row["exact_initial_action_label"],
                        "first_action_agrees_exact": bool(learned["first_action_agrees_exact"]),
                        "normalized_regret": float(learned["normalized_discounted_regret"]),
                        "median_price": float(learned["median_price"]),
                        "low_action_share": float(learned["low_action_share"]),
                    }
                )
    esim5_rows: list[dict] = []
    for row in esim5["rows"]:
        for arm_key, arm_label in (
            ("history_aware_q", "Full history"),
            ("aliased_q", "Last action only"),
        ):
            learned = row[arm_key]
            esim5_rows.append(
                {
                    "seed": int(row["seed"]),
                    "arm": arm_label,
                    "first_action_agrees_exact": bool(learned["first_action_agrees_exact"]),
                    "normalized_regret": float(learned["normalized_discounted_regret"]),
                    "median_price": float(learned["median_price"]),
                }
            )
    return (
        pd.DataFrame(sweep_rows),
        pd.DataFrame(esim5_rows),
        esim4,
        esim5,
        esim6,
        esim7,
        esim8,
        esim9,
    )


def theoretical_panel(esim4: dict, memories: tuple[int, ...]) -> pd.DataFrame:
    source = esim4["arms"]["penalty_on"][0]
    audit = source["permanent_cut_audit"]
    rows = []
    for memory in memories:
        mdp = BinaryCutPenaltyMDP(
            low_price=float(audit["best_permanent_cut"]["price"]),
            high_price=float(source["learner_median_price"]),
            marginal_cost=0.2,
            rival_prices=(1.0, 1.0, float(np.exp(-0.4)), float(np.exp(0.34))),
            theta=float(esim4["theta"]),
            memory=memory,
            gamma=0.95,
        )
        rows.append(
            {
                "memory": memory,
                "stay_high_value": mdp.permanent_high_value(),
                "cut_low_value": mdp.permanent_low_value(),
                "rational_action": (
                    "cut low"
                    if mdp.permanent_low_value() > mdp.permanent_high_value()
                    else "stay high"
                ),
            }
        )
    return pd.DataFrame(rows)


def _style_axis(axis: plt.Axes) -> None:
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(axis="y", color=GRID_COLOR, linewidth=0.7)


def plot_esim5(panel: pd.DataFrame, out_dir: Path) -> tuple[Path, Path]:
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.25), constrained_layout=True)
    arms = ["Full history", "Last action only"]
    colors = [PRIMITIVE_COLOR, "#8A8A8A"]
    agreement = [
        100 * panel.loc[panel["arm"] == arm, "first_action_agrees_exact"].mean() for arm in arms
    ]
    axes[0].bar(arms, agreement, color=colors, width=0.58)
    for index, value in enumerate(agreement):
        axes[0].text(index, value + 3, f"{value:.0f}%", ha="center", va="bottom")
    axes[0].set_ylim(0, 108)
    axes[0].set_ylabel("Seeds matching exact initial cut (%)")
    axes[0].set_title("Observing router history is insufficient")

    rng = np.random.default_rng(20260718)
    for index, (arm, color) in enumerate(zip(arms, colors, strict=True)):
        values = 100 * panel.loc[panel["arm"] == arm, "normalized_regret"].to_numpy()
        jitter = rng.uniform(-0.08, 0.08, len(values))
        axes[1].scatter(
            np.full(len(values), index) + jitter,
            values,
            color=color,
            s=24,
            alpha=0.75,
            edgecolor="none",
        )
        axes[1].plot(
            [index - 0.18, index + 0.18],
            [values.mean(), values.mean()],
            color=EXACT_COLOR,
            linewidth=2,
        )
    axes[1].set_xticks(range(len(arms)), arms)
    axes[1].set_ylabel("Normalized discounted regret (%)")
    axes[1].set_title("Both learners usually stay high")
    for axis in axes:
        _style_axis(axis)
    fig.suptitle("E-SIM5: state information does not remove delayed credit")
    png = out_dir / "sm3_esim5_state_information.png"
    pdf = out_dir / "sm3_esim5_state_information.pdf"
    fig.savefig(png, dpi=220)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def plot_esim6(
    panel: pd.DataFrame,
    theory: pd.DataFrame,
    out_dir: Path,
) -> tuple[Path, Path]:
    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.55), constrained_layout=True)
    memories = sorted(panel["memory"].unique())

    axes[0].plot(
        theory["memory"],
        theory["cut_low_value"],
        marker="o",
        color=OPTION_COLOR,
        linewidth=2,
        label="Cut and remain low",
    )
    axes[0].plot(
        theory["memory"],
        theory["stay_high_value"],
        color=EXACT_COLOR,
        linewidth=2,
        label="Remain high",
    )
    axes[0].axvline(9.24, color="#777777", linestyle=":", linewidth=1.2)
    axes[0].text(9.1, 2.32, r"rational boundary $L^*=9.24$", ha="right", fontsize=8)
    axes[0].set_ylabel("Discounted provider profit")
    axes[0].set_title("Rational cut survives through $L=9$")
    axes[0].legend(frameon=False, fontsize=8)

    for arm, color, marker in (
        ("Primitive Q", PRIMITIVE_COLOR, "o"),
        ("Commit option Q", OPTION_COLOR, "s"),
    ):
        subset = panel[panel["arm"] == arm]
        success = subset.groupby("memory")["first_action_agrees_exact"].mean()
        low_regret = (
            subset.assign(
                success=(
                    subset["first_action_agrees_exact"] & (subset["normalized_regret"] <= 0.05)
                )
            )
            .groupby("memory")["success"]
            .mean()
        )
        axes[1].plot(
            memories,
            100 * low_regret.reindex(memories),
            marker=marker,
            color=color,
            linewidth=2,
            label=arm,
        )
        del success
    axes[1].axvspan(6.5, 9.5, color=OPTION_COLOR, alpha=0.08, linewidth=0)
    axes[1].set_ylim(-3, 103)
    axes[1].set_ylabel("Exact-action and low-regret seeds (%)")
    axes[1].set_title("Option closes the intermediate gap")
    axes[1].legend(frameon=False, fontsize=8)

    for arm, color, marker in (
        ("Primitive Q", PRIMITIVE_COLOR, "o"),
        ("Commit option Q", OPTION_COLOR, "s"),
    ):
        means, lows, highs = [], [], []
        subset = panel[panel["arm"] == arm]
        for memory in memories:
            values = 100 * subset.loc[subset["memory"] == memory, "normalized_regret"].to_numpy()
            low, high = _bootstrap_mean_interval(values, seed=20260718 + memory)
            means.append(float(values.mean()))
            lows.append(float(values.mean()) - low)
            highs.append(high - float(values.mean()))
        axes[2].errorbar(
            memories,
            means,
            yerr=np.asarray([lows, highs]),
            color=color,
            marker=marker,
            linewidth=2,
            capsize=3,
            label=arm,
        )
    axes[2].axhline(5, color="#777777", linestyle=":", linewidth=1.1)
    axes[2].set_ylabel("Mean normalized regret (%)")
    axes[2].set_title("Option overcorrects for long penalties")
    axes[2].legend(frameon=False, fontsize=8)

    for axis in axes:
        axis.set_xlabel("Router cut-memory $L$ (periods)")
        axis.set_xticks(memories)
        _style_axis(axis)
    fig.suptitle("E-SIM6: a payoff-equivalent option removes delayed credit, but can overcommit")
    png = out_dir / "sm3_esim6_delayed_credit.png"
    pdf = out_dir / "sm3_esim6_delayed_credit.pdf"
    fig.savefig(png, dpi=220)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def plot_esim7(esim7: dict, out_dir: Path) -> tuple[Path, Path]:
    labels = {
        "z-ai/glm-5.2": "GLM-5.2",
        "moonshotai/kimi-k2.6": "Kimi K2.6",
        "z-ai/glm-5.1": "GLM-5.1",
        "deepseek/deepseek-v4-flash": "DeepSeek V4",
    }
    rows = []
    for model_id, market in esim7["markets"].items():
        mean = 100 * market["option_minus_primitive_regret"]["paired_mean"]
        low, high = [
            100 * value
            for value in market["option_minus_primitive_regret"]["paired_bootstrap_ci95"]
        ]
        rows.append(
            {
                "model": labels[model_id],
                "boundary": market["profile"]["rational_memory_boundary"],
                "exact_action": market["profile"]["exact_initial_action"],
                "mean": mean,
                "low": low,
                "high": high,
                "primitive_success": market["primitive_success_profiles"],
                "option_success": market["option_success_profiles"],
            }
        )
    panel = pd.DataFrame(rows).sort_values("boundary")
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.65), constrained_layout=True)
    for _, row in panel.iterrows():
        color = OPTION_COLOR if row["exact_action"] == "low" else PRIMITIVE_COLOR
        axes[0].errorbar(
            row["boundary"],
            row["mean"],
            yerr=[[row["mean"] - row["low"]], [row["high"] - row["mean"]]],
            color=color,
            marker="o",
            markersize=7,
            capsize=3,
            linewidth=1.8,
        )
        label_offsets = {
            "GLM-5.2": (5, 10),
            "DeepSeek V4": (5, -14),
            "Kimi K2.6": (5, -14),
            "GLM-5.1": (5, -12),
        }
        axes[0].annotate(
            row["model"],
            (row["boundary"], row["mean"]),
            xytext=label_offsets[row["model"]],
            textcoords="offset points",
            fontsize=8,
        )
    axes[0].axvline(7, color="#777777", linestyle=":", linewidth=1.2)
    axes[0].axhline(0, color="#777777", linewidth=1)
    axes[0].text(7.4, 13, "router memory", fontsize=8)
    axes[0].set_xlabel(r"Rational cut boundary $M^*$")
    axes[0].set_ylabel("Option − primitive regret (pp)")
    axes[0].set_title("Effect sign follows the rational boundary")

    ordered = panel.sort_values("boundary", ascending=False).reset_index(drop=True)
    positions = np.arange(len(ordered))
    width = 0.35
    axes[1].bar(
        positions - width / 2,
        ordered["primitive_success"],
        width,
        color=PRIMITIVE_COLOR,
        label="Primitive Q",
    )
    axes[1].bar(
        positions + width / 2,
        ordered["option_success"],
        width,
        color=OPTION_COLOR,
        label="Commit option Q",
    )
    axes[1].set_xticks(positions, ordered["model"], rotation=18, ha="right")
    axes[1].set_ylim(0, 21)
    axes[1].set_ylabel("Exact-action and low-regret seeds (of 20)")
    axes[1].set_title("Trap severity does not fully transport")
    axes[1].legend(frameon=False, fontsize=8)
    for axis in axes:
        _style_axis(axis)
    fig.suptitle("E-SIM7: calibrated markets split at the predicted memory boundary")
    png = out_dir / "sm3_esim7_market_transport.png"
    pdf = out_dir / "sm3_esim7_market_transport.pdf"
    fig.savefig(png, dpi=220)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def plot_esim8(esim8: dict, out_dir: Path) -> tuple[Path, Path]:
    alphas = esim8["alpha_grid"]
    betas = esim8["beta_grid"]
    regret = np.zeros((len(alphas), len(betas)))
    success_gap = np.zeros_like(regret)
    passed = np.zeros_like(regret, dtype=bool)
    for cell in esim8["cells"]:
        row = alphas.index(cell["alpha"])
        column = betas.index(cell["beta"])
        regret[row, column] = -100 * cell["option_minus_primitive_regret"]["paired_mean"]
        success_gap[row, column] = (
            cell["option_success_profiles"] - cell["primitive_success_profiles"]
        )
        passed[row, column] = cell["cell_robustness_gate"]
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.6), constrained_layout=True)
    panels = (
        (regret, "Regret reduction (percentage points)", "Option lowers regret in all cells"),
        (
            success_gap,
            "Option − primitive successful seeds",
            "Primitive failure depends on learning rate",
        ),
    )
    for axis, (values, colorbar_label, title) in zip(axes, panels, strict=True):
        image = axis.imshow(values, cmap="cividis", aspect="auto")
        for row in range(len(alphas)):
            for column in range(len(betas)):
                suffix = "✓" if passed[row, column] else ""
                axis.text(
                    column,
                    row,
                    f"{values[row, column]:.1f}{suffix}",
                    ha="center",
                    va="center",
                    color="white" if values[row, column] < values.max() * 0.55 else "black",
                    fontsize=9,
                )
        axis.set_xticks(range(len(betas)), [r"$1$", r"$2$", r"$4$"])
        axis.set_yticks(range(len(alphas)), [f"{alpha:.2f}" for alpha in alphas])
        axis.set_xlabel(r"Exploration decay $\beta$ ($\times10^{-5}$)")
        axis.set_ylabel(r"Learning rate $\alpha$")
        axis.set_title(title)
        colorbar = fig.colorbar(image, ax=axis, shrink=0.78)
        colorbar.set_label(colorbar_label, fontsize=8)
    fig.suptitle("E-SIM8: payoff-equivalent commitment is locally robust")
    png = out_dir / "sm3_esim8_q_robustness.png"
    pdf = out_dir / "sm3_esim8_q_robustness.pdf"
    fig.savefig(png, dpi=220)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def plot_esim9(esim9: dict, out_dir: Path) -> tuple[Path, Path]:
    arms = (
        ("primitive_q", "One-step Q", PRIMITIVE_COLOR),
        ("n_step_q", "Eight-step TD", "#777777"),
        ("commit_option_q", "Commit option Q", OPTION_COLOR),
    )
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.45), constrained_layout=True)
    successes = []
    for key, _, _ in arms:
        successes.append(
            sum(
                row[key]["first_action_agrees_exact"]
                and row[key]["normalized_discounted_regret"] <= 0.05
                for row in esim9["rows"]
            )
        )
    labels = [label for _, label, _ in arms]
    colors = [color for _, _, color in arms]
    axes[0].bar(labels, successes, color=colors, width=0.62)
    for index, value in enumerate(successes):
        axes[0].text(index, value + 0.45, f"{value}/20", ha="center", va="bottom")
    axes[0].set_ylim(0, 21)
    axes[0].set_ylabel("Exact-action and low-regret seeds")
    axes[0].set_title("Only the option closes the learning gap")
    axes[0].tick_params(axis="x", rotation=15)

    rng = np.random.default_rng(20260718)
    for index, (key, _, color) in enumerate(arms):
        values = 100 * np.asarray(
            [row[key]["normalized_discounted_regret"] for row in esim9["rows"]]
        )
        jitter = rng.uniform(-0.08, 0.08, len(values))
        axes[1].scatter(
            np.full(len(values), index) + jitter,
            values,
            color=color,
            s=24,
            alpha=0.75,
            edgecolor="none",
        )
        axes[1].plot(
            [index - 0.18, index + 0.18],
            [values.mean(), values.mean()],
            color=EXACT_COLOR,
            linewidth=2,
        )
    axes[1].set_xticks(range(len(labels)), labels, rotation=15)
    axes[1].set_ylabel("Normalized discounted regret (%)")
    axes[1].set_title("Eight-step TD does not beat one-step Q")
    for axis in axes:
        _style_axis(axis)
    fig.suptitle("E-SIM9: multi-step TD is not a substitute for temporal abstraction")
    png = out_dir / "sm3_esim9_multistep_falsification.png"
    pdf = out_dir / "sm3_esim9_multistep_falsification.pdf"
    fig.savefig(png, dpi=220)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    sweep, state_panel, esim4, esim5, esim6, esim7, esim8, esim9 = load_panels()
    theory = theoretical_panel(esim4, tuple(range(1, 13)))
    save(sweep, out_dir, "sm3_esim6_delayed_credit")
    save(state_panel, out_dir, "sm3_esim5_state_information")
    save(theory, out_dir, "sm3_delayed_credit_theory")
    plot_esim5(state_panel, out_dir)
    plot_esim6(sweep, theory, out_dir)
    plot_esim7(esim7, out_dir)
    plot_esim8(esim8, out_dir)
    plot_esim9(esim9, out_dir)
    summary = {
        "experiment_id": "sm3-delayed-credit-v1",
        "esim5_run": ESIM5.parent.name,
        "esim6_run": ESIM6.parent.name,
        "esim7_run": ESIM7.parent.name,
        "esim8_run": ESIM8.parent.name,
        "esim9_run": ESIM9.parent.name,
        "esim5_state_aliasing_supported": esim5["state_aliasing_mechanism_supported"],
        "esim6_delayed_credit_supported": esim6["delayed_credit_intervention_supported"],
        "calibrated_regret_contrast": esim6["primary"],
        "rational_memory_threshold": 9.240163820889613,
        "esim7_confirmatory_transport_supported": esim7["cross_market_transport_supported"],
        "esim7_theory_aligned_effect_signs": all(
            (market["option_minus_primitive_regret"]["paired_mean"] < 0)
            == market["profile"]["delayed_credit_eligible"]
            for market in esim7["markets"].values()
        ),
        "esim8_q_robustness_gate": esim8["robustness_gate"],
        "esim9_multistep_credit_supported": esim9["multi_step_credit_supported"],
        "claim_boundary": esim6["claim_boundary"],
    }
    save_json(summary, out_dir, "sm3_delayed_credit_summary")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
