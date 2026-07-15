"""Generate explicitly synthetic illustrations for the theory manuscript.

The instances are unit tests made visual: they demonstrate theorem mechanisms
under declared primitives. They are not fitted to public router data and do not
estimate real provider reliability, capacity, cost, or welfare.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

from orcap.mechanism import (
    CollateralizedCapacityCurveOffer,
    OutageScenario,
    ProviderOffer,
    collateralized_capacity_reliability_minimum_score_scale,
    collateralized_capacity_reliability_product_report_diagnostic,
    robust_outage_counterfactual,
)

OUTPUT_DIR = Path(__file__).resolve().parent


def robust_example() -> dict[str, float]:
    offers = [
        ProviderOffer("cheap vulnerable", 1.0, 1.0, 10.0, 0.5),
        ProviderOffer("costly independent", 2.0, 1.0, 10.0, 0.5),
    ]
    scenarios = [
        OutageScenario(0.8, frozenset()),
        OutageScenario(0.2, frozenset({"cheap vulnerable"})),
    ]
    diagnostic = robust_outage_counterfactual(offers, demand=10.0, scenarios=scenarios)
    row = diagnostic.iloc[0]
    return {
        "score_cheap": float(
            diagnostic.loc[
                diagnostic["provider"] == "cheap vulnerable", "score_waterfill_allocation"
            ].iat[0]
        ),
        "score_independent": float(
            diagnostic.loc[
                diagnostic["provider"] == "costly independent", "score_waterfill_allocation"
            ].iat[0]
        ),
        "robust_cheap": float(
            diagnostic.loc[
                diagnostic["provider"] == "cheap vulnerable", "robust_outage_allocation"
            ].iat[0]
        ),
        "robust_independent": float(
            diagnostic.loc[
                diagnostic["provider"] == "costly independent", "robust_outage_allocation"
            ].iat[0]
        ),
        "score_worst_case": float(row["score_worst_case_delivered"]),
        "robust_worst_case": float(row["robust_worst_case_delivered"]),
        "score_expected": float(row["score_expected_delivered"]),
        "robust_expected": float(row["robust_expected_delivered"]),
    }


def audited_example() -> tuple[dict[str, float], float]:
    sentinel = 100.0
    offers = [
        CollateralizedCapacityCurveOffer("a", 4, (1.0, 6.0, sentinel, sentinel)),
        CollateralizedCapacityCurveOffer("b", 4, (3.0, 5.0, 9.0, sentinel)),
    ]
    scale = collateralized_capacity_reliability_minimum_score_scale(
        offers,
        provider="a",
        true_marginal_costs=(1.0, 6.0, sentinel, sentinel),
        reliability_grid=(0.3, 0.8),
        other_reported_reliability={"b": 0.5},
        demand=3,
        value_per_success=10.0,
        shortfall_sentinel_cost=sentinel,
        audit_probability=0.2,
        strict_advantage=1e-5,
    )
    diagnostic = collateralized_capacity_reliability_product_report_diagnostic(
        offers,
        provider="a",
        true_marginal_costs=(1.0, 6.0, sentinel, sentinel),
        capacity_cost_report_schedules=[
            (0.0, 0.0, sentinel, sentinel),
            (1.0, 6.0, sentinel, sentinel),
            (1.0, 6.0, 6.0, sentinel),
        ],
        reliability_grid=(0.3, 0.8),
        other_reported_reliability={"b": 0.5},
        demand=3,
        value_per_success=10.0,
        shortfall_sentinel_cost=sentinel,
        audit_probability=0.2,
        audit_score_scale=scale,
    )
    true_q = 0.8
    lower_envelope = (
        diagnostic.loc[diagnostic["true_reliability"] == true_q]
        .groupby("reported_reliability", as_index=True)["truthful_joint_payoff_advantage"]
        .min()
    )
    return {str(report): float(value) for report, value in lower_envelope.items()}, float(scale)


def main() -> None:
    robust = robust_example()
    advantage, scale = audited_example()

    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "figure.dpi": 150,
        }
    )
    figure, axes = plt.subplots(1, 3, figsize=(10.5, 3.1), constrained_layout=True)
    colors = {"score": "#4C78A8", "robust": "#F58518"}

    providers = ["cheap\nvulnerable", "costly\nindependent"]
    x = [0, 1]
    width = 0.36
    axes[0].bar(
        [value - width / 2 for value in x],
        [robust["score_cheap"], robust["score_independent"]],
        width,
        label="score water-fill",
        color=colors["score"],
    )
    axes[0].bar(
        [value + width / 2 for value in x],
        [robust["robust_cheap"], robust["robust_independent"]],
        width,
        label="robust LP",
        color=colors["robust"],
    )
    axes[0].set_xticks(x, providers)
    axes[0].set_ylim(0, 11)
    axes[0].set_ylabel("assigned requests")
    axes[0].set_title("Allocation")
    axes[0].legend(frameon=False, loc="upper center")

    states = ["worst-case", "expected"]
    axes[1].bar(
        [value - width / 2 for value in x],
        [robust["score_worst_case"], robust["score_expected"]],
        width,
        color=colors["score"],
    )
    axes[1].bar(
        [value + width / 2 for value in x],
        [robust["robust_worst_case"], robust["robust_expected"]],
        width,
        color=colors["robust"],
    )
    axes[1].set_xticks(x, states)
    axes[1].set_ylim(0, 11)
    axes[1].set_ylabel("delivered requests")
    axes[1].set_title("Declared-outage delivery")

    reports = sorted(advantage, key=float)
    axes[2].bar(
        reports,
        [advantage[report] for report in reports],
        color=[colors["score"] if report == "0.8" else colors["robust"] for report in reports],
    )
    axes[2].axhline(0.0, color="black", linewidth=0.7)
    axes[2].set_ylabel("minimum truthful-payoff advantage")
    axes[2].set_xlabel("reported reliability; true reliability = 0.8")
    axes[2].set_title("Audited finite-grid report")
    axes[2].ticklabel_format(axis="y", style="sci", scilimits=(-3, 3))

    for axis, label in zip(axes, ["(a)", "(b)", "(c)"], strict=True):
        axis.text(0.02, 0.95, label, transform=axis.transAxes, va="top", fontweight="bold")
        axis.spines[["top", "right"]].set_visible(False)

    figure.savefig(OUTPUT_DIR / "synthetic_mechanism_examples.pdf", bbox_inches="tight")
    figure.savefig(OUTPUT_DIR / "synthetic_mechanism_examples.png", bbox_inches="tight")
    (OUTPUT_DIR / "synthetic_mechanism_examples.json").write_text(
        json.dumps(
            {"robust_outage": robust, "audited_grid": {"scale": scale, "advantage": advantage}},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
