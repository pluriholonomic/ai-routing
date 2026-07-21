"""Cross-model incidence of benchmark undercutting under a price routing rule.

This module is deterministic accounting on public quotes.  It compares the
observed quote menu with a counterfactual in which frozen WF-16 active
undercutters who currently quote below the model-author benchmark are reset to
that benchmark.  If an author quote is unavailable, the contemporaneous median
quote of frozen anchor adopters is used and disclosed.

The resulting ``shadow_share`` fields are not realized OpenRouter flow.  The
elasticity interval varies the routing exponent; it is not a sampling
confidence interval.
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import data
from .pm9_author_anchor import is_author_provider

POINT_EXPONENT = 1.6482780609377246
LOW_EXPONENT = 1.26
HIGH_EXPONENT = 2.04
DOCUMENTED_EXPONENT = 2.0
EXPONENTS = (LOW_EXPONENT, POINT_EXPONENT, DOCUMENTED_EXPONENT, HIGH_EXPONENT)
SHORT_CHAT_INPUT_TOKENS = 1_000
SHORT_CHAT_OUTPUT_TOKENS = 256


def eligible_models(labels: pd.DataFrame) -> tuple[str, ...]:
    """Models with at least one frozen active undercutter and anchor adopter."""
    models = []
    for model_id, group in labels.groupby("model_id", sort=True):
        kinds = set(group["provider_type"].dropna().astype(str))
        if {"active_undercutter", "anchor_adopter"}.issubset(kinds):
            models.append(str(model_id))
    return tuple(models)


def load_short_chat_quotes(labels: pd.DataFrame) -> pd.DataFrame:
    """Load provider-best public quotes for one fixed short-chat request shape."""
    models = eligible_models(labels)
    if not models:
        return pd.DataFrame()
    literals = ", ".join("'" + model.replace("'", "''") + "'" for model in models)
    endpoint_glob = data.table_glob("endpoints_snapshots")
    frame = data.q(
        f"""
        with eligible as (
          select run_ts, cast(dt as varchar) as dt, model_id, provider_name,
            price_prompt * {SHORT_CHAT_INPUT_TOKENS}
              + price_completion * {SHORT_CHAT_OUTPUT_TOKENS}
              + coalesce(price_request, 0) as expected_quote_usd
          from read_parquet('{endpoint_glob}', union_by_name=true)
          where model_id in ({literals})
            and provider_name is not null
            and price_prompt >= 0
            and price_completion >= 0
            and coalesce(price_request, 0) >= 0
            and price_prompt * {SHORT_CHAT_INPUT_TOKENS}
              + price_completion * {SHORT_CHAT_OUTPUT_TOKENS}
              + coalesce(price_request, 0) > 0
            and (context_length is null or context_length >= {
            SHORT_CHAT_INPUT_TOKENS + SHORT_CHAT_OUTPUT_TOKENS
        })
            and (max_prompt_tokens is null or max_prompt_tokens >= {SHORT_CHAT_INPUT_TOKENS})
            and (max_completion_tokens is null or max_completion_tokens >= {
            SHORT_CHAT_OUTPUT_TOKENS
        })
        )
        select run_ts, dt, model_id, provider_name,
               min(expected_quote_usd) as expected_quote_usd
        from eligible
        group by all
        order by run_ts, model_id, provider_name
        """
    ).df()
    if frame.empty:
        return frame
    frame["ts"] = pd.to_datetime(
        frame["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    frame["expected_quote_usd"] = pd.to_numeric(frame["expected_quote_usd"], errors="coerce")
    return frame.dropna(subset=["ts", "model_id", "provider_name", "expected_quote_usd"])


def _sum_by_group(values: pd.Series, groups: list[pd.Series]) -> pd.Series:
    return values.groupby(groups, sort=False).transform("sum")


def build_relative_elasticity_panel(
    quotes: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    exponents: tuple[float, ...] = EXPONENTS,
    benchmark_rtol: float = 1e-9,
) -> pd.DataFrame:
    """Build one row per timestamp/model/exponent benchmark-reset comparison."""
    if quotes.empty or labels.empty:
        return pd.DataFrame()
    required = {"run_ts", "model_id", "provider_name", "expected_quote_usd"}
    missing = required - set(quotes.columns)
    if missing:
        raise ValueError(f"quote panel lacks required columns: {sorted(missing)}")

    label_columns = labels[["model_id", "provider_name", "provider_type"]].drop_duplicates(
        ["model_id", "provider_name"]
    )
    frame = quotes.merge(
        label_columns,
        on=["model_id", "provider_name"],
        how="left",
        validate="many_to_one",
    )
    frame["provider_type"] = frame["provider_type"].fillna("unclassified")
    frame["is_author"] = [
        is_author_provider(model, provider)
        for model, provider in zip(frame["model_id"], frame["provider_name"], strict=True)
    ]
    frame["is_active"] = (~frame["is_author"]) & frame["provider_type"].eq("active_undercutter")
    frame["is_anchor"] = (~frame["is_author"]) & frame["provider_type"].eq("anchor_adopter")
    frame["is_other"] = ~(frame["is_author"] | frame["is_active"] | frame["is_anchor"])
    keys = [frame["run_ts"], frame["model_id"]]
    quote = frame["expected_quote_usd"].astype(float)
    author_benchmark = quote.where(frame["is_author"]).groupby(keys, sort=False).transform("median")
    anchor_benchmark = quote.where(frame["is_anchor"]).groupby(keys, sort=False).transform("median")
    frame["benchmark_quote_usd"] = author_benchmark.fillna(anchor_benchmark)
    frame["benchmark_source"] = np.where(
        author_benchmark.notna(), "model_author", "median_anchor_adopter"
    )
    active_count = frame["is_active"].astype(int).groupby(keys, sort=False).transform("sum")
    anchor_count = frame["is_anchor"].astype(int).groupby(keys, sort=False).transform("sum")
    frame = frame[
        (active_count > 0)
        & (anchor_count > 0)
        & frame["benchmark_quote_usd"].notna()
        & (frame["benchmark_quote_usd"] > 0)
    ].copy()
    if frame.empty:
        return pd.DataFrame()

    keys = [frame["run_ts"], frame["model_id"]]
    price = frame["expected_quote_usd"].astype(float)
    benchmark = frame["benchmark_quote_usd"].astype(float)
    frame["is_current_undercut"] = frame["is_active"] & (price < benchmark * (1.0 - benchmark_rtol))
    frame["counterfactual_quote_usd"] = price.where(~frame["is_current_undercut"], benchmark)
    frame["undercut_fraction"] = np.where(
        frame["is_current_undercut"], 1.0 - price / benchmark, np.nan
    )

    group_meta = frame.groupby(["run_ts", "model_id"], as_index=False, sort=False).agg(
        dt=("dt", "first") if "dt" in frame else ("run_ts", "first"),
        benchmark_quote_usd=("benchmark_quote_usd", "first"),
        benchmark_source=("benchmark_source", "first"),
        providers=("provider_name", "nunique"),
        active_providers=("is_active", "sum"),
        anchor_adopters=("is_anchor", "sum"),
        author_providers=("is_author", "sum"),
        current_undercutters=("is_current_undercut", "sum"),
        median_undercut_fraction=("undercut_fraction", "median"),
        maximum_undercut_fraction=("undercut_fraction", "max"),
    )
    outputs: list[pd.DataFrame] = []
    masks = {
        "active": frame["is_active"],
        "anchor": frame["is_anchor"],
        "author": frame["is_author"],
        "other": frame["is_other"],
    }
    for exponent in dict.fromkeys(float(value) for value in exponents):
        actual_weight = price.pow(-exponent)
        counterfactual_weight = frame["counterfactual_quote_usd"].pow(-exponent)
        actual_share = actual_weight / _sum_by_group(actual_weight, keys)
        counterfactual_share = counterfactual_weight / _sum_by_group(counterfactual_weight, keys)
        work = frame[["run_ts", "model_id"]].copy()
        for kind, mask in masks.items():
            work[f"actual_{kind}_share"] = actual_share.where(mask, 0.0)
            work[f"counterfactual_{kind}_share"] = counterfactual_share.where(mask, 0.0)
        work["active_actual_weight"] = actual_weight.where(frame["is_active"], 0.0)
        work["active_counterfactual_weight"] = counterfactual_weight.where(frame["is_active"], 0.0)
        totals = work.groupby(["run_ts", "model_id"], as_index=False, sort=False).sum()
        totals = totals.merge(
            group_meta, on=["run_ts", "model_id"], how="left", validate="one_to_one"
        )
        totals["routing_exponent"] = exponent
        totals["active_excess_shadow_share"] = (
            totals["actual_active_share"] - totals["counterfactual_active_share"]
        )
        for kind in ("anchor", "author", "other"):
            totals[f"{kind}_shadow_share_loss"] = (
                totals[f"counterfactual_{kind}_share"] - totals[f"actual_{kind}_share"]
            )
        totals["share_conservation_error"] = totals["active_excess_shadow_share"] - (
            totals["anchor_shadow_share_loss"]
            + totals["author_shadow_share_loss"]
            + totals["other_shadow_share_loss"]
        )
        totals["equivalent_active_quote_usd"] = (
            totals["active_actual_weight"] / totals["active_providers"]
        ).pow(-1.0 / exponent)
        totals["counterfactual_equivalent_active_quote_usd"] = (
            totals["active_counterfactual_weight"] / totals["active_providers"]
        ).pow(-1.0 / exponent)
        totals["equivalent_active_discount_fraction"] = 1.0 - (
            totals["equivalent_active_quote_usd"]
            / totals["counterfactual_equivalent_active_quote_usd"]
        )
        numerator = np.log(totals["actual_active_share"] / totals["counterfactual_active_share"])
        denominator = np.log(
            totals["equivalent_active_quote_usd"]
            / totals["counterfactual_equivalent_active_quote_usd"]
        )
        totals["group_arc_price_elasticity"] = np.where(
            denominator.abs() > 1e-12, numerator / denominator, np.nan
        )
        totals["local_group_price_elasticity_at_counterfactual"] = -exponent * (
            1.0 - totals["counterfactual_active_share"]
        )
        totals["active_relative_shadow_share_lift"] = np.where(
            totals["counterfactual_active_share"] > 0,
            totals["active_excess_shadow_share"] / totals["counterfactual_active_share"],
            np.nan,
        )
        loss = totals["active_excess_shadow_share"]
        totals["anchor_fraction_of_nonactive_loss"] = np.where(
            loss > 1e-15, totals["anchor_shadow_share_loss"] / loss, np.nan
        )
        totals["author_fraction_of_nonactive_loss"] = np.where(
            loss > 1e-15, totals["author_shadow_share_loss"] / loss, np.nan
        )
        totals["other_fraction_of_nonactive_loss"] = np.where(
            loss > 1e-15, totals["other_shadow_share_loss"] / loss, np.nan
        )
        totals.drop(columns=["active_actual_weight", "active_counterfactual_weight"], inplace=True)
        outputs.append(totals)
    panel = pd.concat(outputs, ignore_index=True)
    panel["ts"] = pd.to_datetime(
        panel["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    return panel.sort_values(["ts", "model_id", "routing_exponent"]).reset_index(drop=True)


def summarize_relative_elasticity(panel: pd.DataFrame) -> dict[str, Any]:
    boundary = (
        "Benchmark-reset effects are deterministic price-rule shadow-share accounting, not "
        "realized market share or causal estimates. Exponent sensitivity is not a sampling "
        "confidence interval. Frozen provider types describe quote behavior, not intent."
    )
    if panel.empty:
        return {"evidence_status": "no_eligible_cross_model_quotes", "boundary": boundary}
    point = panel[np.isclose(panel["routing_exponent"], POINT_EXPONENT)].copy()
    by_model: list[dict[str, Any]] = []
    for model_id, group in point.groupby("model_id", sort=True):
        moving = group[group["current_undercutters"] > 0]
        latest = group.sort_values("ts").iloc[-1]
        if moving.empty:
            by_model.append(
                {
                    "model_id": model_id,
                    "snapshots": int(len(group)),
                    "snapshots_with_benchmark_undercut": 0,
                    "latest_active_excess_shadow_share_percentage_points": 0.0,
                }
            )
            continue
        by_model.append(
            {
                "model_id": model_id,
                "snapshots": int(len(group)),
                "snapshots_with_benchmark_undercut": int(len(moving)),
                "coverage_start": group["ts"].min().isoformat(),
                "coverage_end": group["ts"].max().isoformat(),
                "median_equivalent_active_discount_fraction": float(
                    moving["equivalent_active_discount_fraction"].median()
                ),
                "median_active_excess_shadow_share_percentage_points": float(
                    100.0 * moving["active_excess_shadow_share"].median()
                ),
                "maximum_active_excess_shadow_share_percentage_points": float(
                    100.0 * moving["active_excess_shadow_share"].max()
                ),
                "median_anchor_shadow_share_loss_percentage_points": float(
                    100.0 * moving["anchor_shadow_share_loss"].median()
                ),
                "mean_anchor_fraction_of_nonactive_loss": float(
                    moving["anchor_fraction_of_nonactive_loss"].mean()
                ),
                "mean_author_fraction_of_nonactive_loss": float(
                    moving["author_fraction_of_nonactive_loss"].mean()
                ),
                "mean_other_fraction_of_nonactive_loss": float(
                    moving["other_fraction_of_nonactive_loss"].mean()
                ),
                "median_group_arc_price_elasticity": float(
                    moving["group_arc_price_elasticity"].median()
                ),
                "latest_active_excess_shadow_share_percentage_points": float(
                    100.0 * latest["active_excess_shadow_share"]
                ),
                "latest_anchor_shadow_share_loss_percentage_points": float(
                    100.0 * latest["anchor_shadow_share_loss"]
                ),
            }
        )
    return {
        "evidence_status": "descriptive_cross_model_price_rule_accounting",
        "request_shape": {
            "name": "short_chat",
            "input_tokens": SHORT_CHAT_INPUT_TOKENS,
            "output_tokens": SHORT_CHAT_OUTPUT_TOKENS,
        },
        "point_routing_exponent": POINT_EXPONENT,
        "routing_exponent_sensitivity": [LOW_EXPONENT, HIGH_EXPONENT],
        "documented_price_rule_exponent": DOCUMENTED_EXPONENT,
        "models": int(point["model_id"].nunique()),
        "snapshots": int(point[["run_ts", "model_id"]].drop_duplicates().shape[0]),
        "coverage_start": point["ts"].min().isoformat(),
        "coverage_end": point["ts"].max().isoformat(),
        "maximum_absolute_share_conservation_error": float(
            panel["share_conservation_error"].abs().max()
        ),
        "by_model": by_model,
        "interpretation": (
            "Resetting current active-undercutter quotes to the contemporaneous benchmark "
            "removes their price-rule advantage. The lost active share is allocated exactly "
            "between frozen anchor adopters, model-author providers, and all other providers."
        ),
        "boundary": boundary,
    }


def _display_model(model_id: str) -> str:
    return model_id.split("/", 1)[-1]


def _hourly(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.copy()
    frame["hour"] = frame["ts"].dt.floor("h")
    numeric = [
        "active_excess_shadow_share",
        "anchor_shadow_share_loss",
        "author_shadow_share_loss",
        "other_shadow_share_loss",
        "equivalent_active_discount_fraction",
        "group_arc_price_elasticity",
        "current_undercutters",
    ]
    return (
        frame.groupby(["hour", "model_id", "routing_exponent"], as_index=False)[numeric]
        .median()
        .sort_values("hour")
    )


def render_cross_model_figures(out_dir: Any, panel: pd.DataFrame) -> None:
    """Write comparable time-series and cross-sectional publication figures."""
    if panel.empty:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    hourly = _hourly(panel)
    point = hourly[np.isclose(hourly["routing_exponent"], POINT_EXPONENT)]
    low = hourly[np.isclose(hourly["routing_exponent"], LOW_EXPONENT)][
        ["hour", "model_id", "active_excess_shadow_share", "group_arc_price_elasticity"]
    ].rename(
        columns={
            "active_excess_shadow_share": "excess_low",
            "group_arc_price_elasticity": "elasticity_low",
        }
    )
    high = hourly[np.isclose(hourly["routing_exponent"], HIGH_EXPONENT)][
        ["hour", "model_id", "active_excess_shadow_share", "group_arc_price_elasticity"]
    ].rename(
        columns={
            "active_excess_shadow_share": "excess_high",
            "group_arc_price_elasticity": "elasticity_high",
        }
    )
    time = point.merge(low, on=["hour", "model_id"], how="left").merge(
        high, on=["hour", "model_id"], how="left"
    )
    models = sorted(time["model_id"].unique())
    fig, axes = plt.subplots(
        len(models),
        2,
        figsize=(14.5, 2.05 * len(models)),
        sharex="col",
        sharey="col",
        constrained_layout=True,
    )
    axes = np.atleast_2d(axes)
    for index, model_id in enumerate(models):
        group = time[time["model_id"] == model_id]
        price_axis, share_axis = axes[index]
        price_axis.plot(
            group["hour"],
            100.0 * group["equivalent_active_discount_fraction"],
            color="#6A51A3",
            linewidth=1.5,
            label="equivalent active undercut" if index == 0 else None,
        )
        price_axis.set_ylabel(_display_model(model_id), rotation=0, ha="right", va="center")
        price_axis.grid(axis="y", alpha=0.2)
        share_axis.fill_between(
            group["hour"],
            100.0 * group["excess_low"],
            100.0 * group["excess_high"],
            color="#D55E00",
            alpha=0.16,
            linewidth=0,
            label="exponent sensitivity [1.26, 2.04]" if index == 0 else None,
        )
        share_axis.plot(
            group["hour"],
            100.0 * group["active_excess_shadow_share"],
            color="#D55E00",
            linewidth=1.6,
            label="undercutter excess share" if index == 0 else None,
        )
        share_axis.plot(
            group["hour"],
            100.0 * group["anchor_shadow_share_loss"],
            color="#0072B2",
            linewidth=1.25,
            label="anchor-adopter loss" if index == 0 else None,
        )
        share_axis.grid(axis="y", alpha=0.2)
        if index == 0:
            price_axis.set_title("A. Active-provider discount from benchmark (%)")
            price_axis.legend(loc="upper left", frameon=False, fontsize=8)
            share_axis.set_title("B. Price-rule shadow share (percentage points)")
            share_axis.legend(loc="upper left", ncol=3, frameon=False, fontsize=8)
    axes[-1, 0].set_xlabel("Public quote timestamp (UTC)")
    axes[-1, 1].set_xlabel("Public quote timestamp (UTC)")
    fig.suptitle(
        "Undercutter share advantage and anchor-adopter displacement by model\n"
        "Fixed short-chat quote; point exponent 1.648; shaded range is rule sensitivity",
        fontsize=13,
    )
    for extension in ("png", "pdf"):
        fig.savefig(out_dir / f"wf19_cross_model_timeseries.{extension}", dpi=220)
    plt.close(fig)

    moving = point[point["current_undercutters"] > 0].copy()
    summary_rows = []
    for model_id, group in moving.groupby("model_id", sort=True):
        lo_group = low[low["model_id"] == model_id]
        hi_group = high[high["model_id"] == model_id]
        summary_rows.append(
            {
                "model_id": model_id,
                "discount": float(group["equivalent_active_discount_fraction"].median()),
                "excess": float(group["active_excess_shadow_share"].median()),
                "excess_low": float(lo_group["excess_low"].median()),
                "excess_high": float(hi_group["excess_high"].median()),
                "elasticity": float(-group["group_arc_price_elasticity"].median()),
                "elasticity_low": float(-lo_group["elasticity_low"].median()),
                "elasticity_high": float(-hi_group["elasticity_high"].median()),
                "anchor": float(group["anchor_shadow_share_loss"].sum()),
                "author": float(group["author_shadow_share_loss"].sum()),
                "other": float(group["other_shadow_share_loss"].sum()),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values("excess", ascending=True)
    fig, axes = plt.subplots(1, 3, figsize=(15.0, 5.2), constrained_layout=True)
    axes[0].errorbar(
        100.0 * summary["discount"],
        100.0 * summary["excess"],
        yerr=np.vstack(
            [
                100.0 * (summary["excess"] - summary["excess_low"]),
                100.0 * (summary["excess_high"] - summary["excess"]),
            ]
        ),
        fmt="o",
        color="#D55E00",
        ecolor="#D55E00",
        capsize=3,
    )
    for row in summary.itertuples():
        axes[0].annotate(
            _display_model(row.model_id),
            (100.0 * row.discount, 100.0 * row.excess),
            xytext=(4, 3),
            textcoords="offset points",
            fontsize=8,
        )
    axes[0].set_xlabel("Median equivalent undercut from benchmark (%)")
    axes[0].set_ylabel("Median excess undercutter shadow share (pp)")
    axes[0].set_title("A. Price gap translates into share advantage")
    axes[0].grid(alpha=0.2)

    y = np.arange(len(summary))
    axes[1].hlines(
        y,
        summary["elasticity_low"],
        summary["elasticity_high"],
        color="#D55E00",
        linewidth=2,
    )
    axes[1].scatter(summary["elasticity"], y, color="#D55E00", s=36, zorder=3)
    axes[1].set_yticks(y, [_display_model(value) for value in summary["model_id"]])
    axes[1].set_xlabel("Median |arc elasticity| of undercutter-group share")
    axes[1].set_title(
        "B. Relative elasticity differs with concentration\n"
        "Horizontal ranges vary the routing exponent, not sampling uncertainty"
    )
    axes[1].grid(axis="x", alpha=0.2)

    losses = summary[["anchor", "author", "other"]].clip(lower=0)
    totals = losses.sum(axis=1).replace(0, np.nan)
    shares = losses.div(totals, axis=0).fillna(0)
    left = np.zeros(len(summary))
    for column, label, color in (
        ("anchor", "anchor adopters", "#0072B2"),
        ("author", "model author", "#009E73"),
        ("other", "other providers", "#999999"),
    ):
        axes[2].barh(y, 100.0 * shares[column], left=100.0 * left, label=label, color=color)
        left += shares[column].to_numpy(float)
    axes[2].set_yticks(y, [_display_model(value) for value in summary["model_id"]])
    axes[2].set_xlim(0, 100)
    axes[2].set_xlabel("Share of non-active displacement (%)")
    axes[2].set_title("C. Who funds the undercutter advantage?")
    axes[2].legend(frameon=False, fontsize=8, loc="lower right")
    axes[2].grid(axis="x", alpha=0.2)
    fig.suptitle(
        "Cross-model benchmark-undercutting incidence\n"
        "Public price-rule accounting; not realized routing or provider profit",
        fontsize=13,
    )
    for extension in ("png", "pdf"):
        fig.savefig(out_dir / f"wf19_cross_model_elasticity.{extension}", dpi=220)
    plt.close(fig)
