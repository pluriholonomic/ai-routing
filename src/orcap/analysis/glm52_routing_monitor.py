"""Aggregate, support-gated analysis for the prospective GLM-5.2 panel."""

from __future__ import annotations

import argparse
import base64
import html
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..glm52_routing import BENCHMARK_KEY, PAIR_KEYS, STUDY_ID
from ..price_experiments import collapse_provider_candidates, provider_key
from .nonprice_scoring import estimate_nonprice_scoring, price_sort_rule_contrast
from .router_exponent import fit_exponent, probabilities

ETA_LOW = 1.26
ETA_FROZEN = 1.6482780609377246
ETA_HIGH = 2.04
MIN_DEFAULT_CHOICES = 800
MIN_BLOCKS = 100
MIN_DAYS = 7.0
MIN_COVERAGE = 0.90
BOOTSTRAP_DRAWS = 5_000
NONPRICE_PROSPECTIVE_START_UTC = "2026-07-21T22:00:00Z"


def _read_table(root: Path, table: str) -> pd.DataFrame:
    frames = []
    for path in sorted((root / "curated" / table).glob("dt=*/*.parquet")):
        try:
            frames.append(pq.ParquetFile(path).read())
        except (OSError, pa.ArrowInvalid):
            continue
    return (
        pa.concat_tables(frames, promote_options="permissive").to_pandas()
        if frames
        else pd.DataFrame()
    )


def _task_id(value: Any) -> str | None:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return str(parsed.get("task_id")) if parsed.get("task_id") else None


def _wilson(successes: int, trials: int, z: float = 1.959963984540054) -> list[float | None]:
    if trials <= 0:
        return [None, None]
    p = successes / trials
    denom = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return [float(max(0.0, center - half)), float(min(1.0, center + half))]


def _bootstrap(
    choices: pd.DataFrame, *, draws: int = BOOTSTRAP_DRAWS, seed: int = 20260721
) -> dict[str, list[float] | None]:
    if choices.empty:
        return {"pair_share_ci95": None, "calibration_error_ci95": None}
    grouped = choices.groupby("block_id", sort=True).agg(
        pair_successes=("selected_pair", "sum"),
        trials=("selected_pair", "count"),
        predicted_sum=("predicted_pair_eta_frozen", "sum"),
    )
    if len(grouped) < 2:
        return {"pair_share_ci95": None, "calibration_error_ci95": None}
    values = grouped.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    sampled = rng.integers(0, len(values), size=(draws, len(values)))
    resampled = values[sampled].sum(axis=1)
    pair_share = resampled[:, 0] / resampled[:, 1]
    predicted = resampled[:, 2] / resampled[:, 1]
    error = pair_share - predicted
    return {
        "pair_share_ci95": [float(v) for v in np.quantile(pair_share, [0.025, 0.975])],
        "calibration_error_ci95": [float(v) for v in np.quantile(error, [0.025, 0.975])],
    }


def _frames(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidates = _read_table(root, "glm52_routing_candidates")
    assignments = _read_table(root, "glm52_routing_assignments")
    attempts = _read_table(root, "glm52_routing_attempts")
    for frame in (candidates, assignments, attempts):
        if not frame.empty and "study_id" in frame:
            frame.drop(frame[frame["study_id"] != STUDY_ID].index, inplace=True)
    if assignments.empty:
        return candidates, assignments, attempts
    assignments = assignments.drop_duplicates("task_id", keep="last")
    if attempts.empty:
        joined = assignments.copy()
        for column in (
            "attempt_observed_at",
            "outcome",
            "selected_provider",
            "latency_ms",
            "cost_usd",
        ):
            joined[column] = None
        return candidates, joined, attempts
    attempts = attempts.copy()
    attempts["task_id"] = attempts["metadata_json"].map(_task_id)
    attempts = attempts.dropna(subset=["task_id"]).drop_duplicates("task_id", keep="last")
    attempts = attempts.rename(columns={"observed_at": "attempt_observed_at"})
    keep = [
        "task_id",
        "attempt_observed_at",
        "outcome",
        "selected_provider",
        "latency_ms",
        "cost_usd",
        "fallback_triggered",
        "retry_reason",
    ]
    return candidates, assignments.merge(attempts[keep], on="task_id", how="left"), attempts


def analyze(
    candidates: pd.DataFrame, joined: pd.DataFrame
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    candidate_menus: dict[str, list[dict[str, Any]]] = {}
    if not candidates.empty:
        for block_id, group in candidates.groupby("block_id", sort=True):
            candidate_menus[str(block_id)] = collapse_provider_candidates(group.to_dict("records"))

    run_rows: list[dict[str, Any]] = []
    choice_rows: list[dict[str, Any]] = []
    rule_choice_rows: list[dict[str, Any]] = []
    for block_id, menu in candidate_menus.items():
        providers = [provider_key(row.get("provider_name")) for row in menu]
        costs = np.asarray([float(row["expected_quote_usd"]) for row in menu], dtype=float)
        by_key = {provider_key(row.get("provider_name")): row for row in menu}
        block_assignments = (
            joined[joined["block_id"].astype(str) == block_id] if not joined.empty else joined
        )
        defaults = block_assignments[block_assignments["policy"] == "default_broad"]
        observed_at = pd.to_datetime(
            next((row.get("observed_at") for row in menu if row.get("observed_at")), None),
            utc=True,
            errors="coerce",
        )
        predicted: dict[float, float] = {}
        for eta in (ETA_LOW, ETA_FROZEN, ETA_HIGH):
            p = probabilities(costs, eta)
            predicted[eta] = float(
                sum(p[index] for index, key in enumerate(providers) if key in PAIR_KEYS)
            )
        pair_quotes = [
            float(by_key[key]["expected_quote_usd"]) if key in by_key else np.nan
            for key in PAIR_KEYS
        ]
        benchmark = (
            float(by_key[BENCHMARK_KEY]["expected_quote_usd"])
            if BENCHMARK_KEY in by_key
            else np.nan
        )
        successful_defaults = defaults[
            defaults["outcome"].eq("succeeded") & defaults["selected_provider"].notna()
        ]
        pair_count = int(
            successful_defaults["selected_provider"].map(provider_key).isin(PAIR_KEYS).sum()
        )
        run_rows.append(
            {
                "run_id": str(menu[0].get("run_id") or ""),
                "block_id": block_id,
                "observed_at": observed_at,
                "candidate_providers": len(menu),
                "streamlake_quote_usd": pair_quotes[0],
                "novita_quote_usd": pair_quotes[1],
                "zai_quote_usd": benchmark,
                "streamlake_to_zai": pair_quotes[0] / benchmark if benchmark > 0 else np.nan,
                "novita_to_zai": pair_quotes[1] / benchmark if benchmark > 0 else np.nan,
                "predicted_pair_eta_low": predicted[ETA_LOW],
                "predicted_pair_eta_frozen": predicted[ETA_FROZEN],
                "predicted_pair_eta_high": predicted[ETA_HIGH],
                "default_attempts": int(defaults["attempt_observed_at"].notna().sum()),
                "default_covered": int(len(successful_defaults)),
                "default_pair_selected": pair_count,
                "default_pair_share": (
                    pair_count / len(successful_defaults) if len(successful_defaults) else np.nan
                ),
            }
        )
        for row in defaults.to_dict("records"):
            selected = provider_key(row.get("selected_provider"))
            covered = row.get("outcome") == "succeeded" and selected in providers
            choice_rows.append(
                {
                    "run_id": row.get("run_id"),
                    "block_id": block_id,
                    "task_id": row.get("task_id"),
                    "observed_at": row.get("attempt_observed_at"),
                    "selected_provider": selected or None,
                    "covered": bool(covered),
                    "selected_pair": bool(selected in PAIR_KEYS) if covered else np.nan,
                    "predicted_pair_eta_low": predicted[ETA_LOW],
                    "predicted_pair_eta_frozen": predicted[ETA_FROZEN],
                    "predicted_pair_eta_high": predicted[ETA_HIGH],
                    "providers": providers,
                    "costs": costs,
                    "selected_index": providers.index(selected) if covered else None,
                }
            )
        for row in block_assignments[
            block_assignments["policy"].isin(["default_broad", "price_sorted"])
        ].to_dict("records"):
            selected = provider_key(row.get("selected_provider"))
            covered_policy = row.get("outcome") == "succeeded" and selected in providers
            rule_choice_rows.append(
                {
                    "run_id": row.get("run_id"),
                    "block_id": block_id,
                    "task_id": row.get("task_id"),
                    "observed_at": row.get("attempt_observed_at"),
                    "policy": row.get("policy"),
                    "selected_provider": selected or None,
                    "providers": providers,
                    "costs": costs,
                    "selected_index": providers.index(selected) if covered_policy else None,
                }
            )

    run_panel = pd.DataFrame(run_rows).sort_values("observed_at") if run_rows else pd.DataFrame()
    choices = pd.DataFrame(choice_rows)
    covered = choices[choices["covered"]].copy() if not choices.empty else choices

    policy_rows = []
    if not joined.empty:
        for policy, group in joined.groupby("policy", sort=True):
            attempted = int(group["attempt_observed_at"].notna().sum())
            successful = group[group["outcome"] == "succeeded"]
            selected = successful["selected_provider"].dropna().map(provider_key)
            latencies = pd.to_numeric(successful["latency_ms"], errors="coerce").dropna()
            costs_seen = pd.to_numeric(successful["cost_usd"], errors="coerce").dropna()
            requested = group["requested_provider"].dropna().map(provider_key)
            matched = (
                selected.eq(requested.iloc[0]).mean()
                if not requested.empty and not selected.empty
                else np.nan
            )
            policy_rows.append(
                {
                    "policy": policy,
                    "assigned": int(len(group)),
                    "attempted": attempted,
                    "succeeded": int(len(successful)),
                    "success_rate": len(successful) / attempted if attempted else np.nan,
                    "selected_pair_share": float(selected.isin(PAIR_KEYS).mean())
                    if len(selected)
                    else np.nan,
                    "requested_provider_match": matched,
                    "median_latency_ms": float(latencies.median()) if len(latencies) else np.nan,
                    "p95_latency_ms": float(latencies.quantile(0.95)) if len(latencies) else np.nan,
                    "mean_cost_usd": float(costs_seen.mean()) if len(costs_seen) else np.nan,
                }
            )
    policy_panel = pd.DataFrame(policy_rows)

    provider_panel = pd.DataFrame()
    if not covered.empty:
        provider_panel = (
            covered.groupby("selected_provider", as_index=False)
            .size()
            .rename(columns={"size": "selections"})
        )
        provider_panel["share"] = provider_panel["selections"] / len(covered)

    n = int(len(covered))
    pair_successes = (
        int(pd.to_numeric(covered.get("selected_pair"), errors="coerce").sum()) if n else 0
    )
    blocks = int(covered["block_id"].nunique()) if n else 0
    coverage = n / len(choices) if len(choices) else 0.0
    timestamps = pd.to_datetime(run_panel.get("observed_at"), utc=True, errors="coerce").dropna()
    duration_days = (
        float((timestamps.max() - timestamps.min()).total_seconds() / 86_400)
        if len(timestamps) >= 2
        else 0.0
    )
    failures = []
    if n < MIN_DEFAULT_CHOICES:
        failures.append("default_choices")
    if blocks < MIN_BLOCKS:
        failures.append("blocks")
    if duration_days < MIN_DAYS:
        failures.append("duration")
    if coverage < MIN_COVERAGE:
        failures.append("candidate_coverage")
    boot = _bootstrap(covered)
    fit_rows = [
        {
            "block_id": row["block_id"],
            "model_id": "z-ai/glm-5.2",
            "selected_provider": row["selected_provider"],
            "costs": row["costs"],
            "selected_index": row["selected_index"],
        }
        for row in covered.to_dict("records")
    ]
    fit = fit_exponent(fit_rows, minimum=20)
    actual_share = pair_successes / n if n else None
    predicted = float(covered["predicted_pair_eta_frozen"].mean()) if n else None
    # Temporal identification needs between-block movement. Do not mistake the
    # within-block StreamLake/Novita cross-section for time-series support.
    gap_values = (
        run_panel[["streamlake_to_zai", "novita_to_zai"]].mean(axis=1).dropna()
        if not run_panel.empty
        else pd.Series(dtype=float)
    )
    prospective_start = pd.Timestamp(NONPRICE_PROSPECTIVE_START_UTC)
    scoring_rows = []
    if not covered.empty:
        scoring_times = pd.to_datetime(covered["observed_at"], utc=True, errors="coerce")
        scoring_rows = covered[scoring_times >= prospective_start].to_dict("records")
    nonprice_summary, nonprice_provider, manipulation_panel = estimate_nonprice_scoring(
        scoring_rows,
        eta=ETA_FROZEN,
        benchmark_provider=BENCHMARK_KEY,
    )
    prospective_rule_rows = []
    if rule_choice_rows:
        prospective_rule_rows = [
            row
            for row in rule_choice_rows
            if pd.notna(pd.to_datetime(row.get("observed_at"), utc=True, errors="coerce"))
            and pd.to_datetime(row.get("observed_at"), utc=True, errors="coerce")
            >= prospective_start
        ]
    rule_summary, rule_panel = price_sort_rule_contrast(prospective_rule_rows)
    summary = {
        "study_id": STUDY_ID,
        "analysis_at": datetime.now(UTC).isoformat(),
        "support_status": "ready" if not failures else "accruing",
        "support_failures": failures,
        "planned_support_gates": {
            "default_choices": MIN_DEFAULT_CHOICES,
            "blocks": MIN_BLOCKS,
            "duration_days": MIN_DAYS,
            "candidate_coverage": MIN_COVERAGE,
        },
        "candidate_blocks": int(len(run_panel)),
        "default_assignments": int(len(choices)),
        "covered_default_choices": n,
        "covered_blocks": blocks,
        "duration_days": duration_days,
        "candidate_coverage": coverage,
        "observed_pair_selections": pair_successes,
        "observed_pair_share": actual_share,
        "observed_pair_share_wilson_95ci": _wilson(pair_successes, n),
        "observed_pair_share_block_bootstrap_95ci": boot["pair_share_ci95"],
        "frozen_eta": ETA_FROZEN,
        "mean_predicted_pair_share_frozen_eta": predicted,
        "mean_predicted_pair_share_eta_sensitivity": (
            {
                "eta_low": float(covered["predicted_pair_eta_low"].mean()),
                "eta_high": float(covered["predicted_pair_eta_high"].mean()),
            }
            if n
            else {"eta_low": None, "eta_high": None}
        ),
        "observed_minus_predicted_pair_share": (
            actual_share - predicted if actual_share is not None and predicted is not None else None
        ),
        "calibration_error_block_bootstrap_95ci": boot["calibration_error_ci95"],
        "glm52_price_exponent": fit,
        "pair_to_benchmark_quote_ratio_iqr": (
            float(gap_values.quantile(0.75) - gap_values.quantile(0.25))
            if len(gap_values)
            else None
        ),
        "nonprice_prospective_start_utc": NONPRICE_PROSPECTIVE_START_UTC,
        "nonprice_scoring": nonprice_summary,
        "price_sort_rule_contrast": rule_summary,
        "claim_boundary": (
            "The primary share and calibration estimates cover fresh owned GLM-5.2 "
            "requests and frozen public menus. They do not identify market-wide flow, "
            "provider revenue or profit, intent, front-running, or collusion. The inferred "
            "non-price score is a reduced-form residual, not a direct quality measure."
        ),
    }
    return (
        run_panel,
        choices.drop(columns=["providers", "costs"], errors="ignore"),
        policy_panel,
        provider_panel,
        nonprice_provider,
        manipulation_panel,
        rule_panel,
        summary,
    )


def _plot(run_panel: pd.DataFrame, output: Path) -> None:
    if run_panel.empty:
        return
    frame = run_panel.dropna(subset=["observed_at"]).sort_values("observed_at")
    if frame.empty:
        return
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    axes[0].plot(frame["observed_at"], frame["streamlake_to_zai"], label="StreamLake / Z.AI")
    axes[0].plot(frame["observed_at"], frame["novita_to_zai"], label="Novita / Z.AI")
    axes[0].axhline(1.0, color="black", linewidth=1, linestyle="--", label="Z.AI benchmark")
    axes[0].set_ylabel("Quote ratio")
    axes[0].set_title("GLM-5.2 public quote gap")
    axes[0].legend(frameon=False, ncol=3)
    observed = frame["default_pair_share"]
    axes[1].scatter(frame["observed_at"], observed, s=16, alpha=0.45, label="Owned default block")
    rolling = observed.rolling(48, min_periods=12).mean()
    axes[1].plot(frame["observed_at"], rolling, linewidth=2, label="48-block rolling realized")
    axes[1].fill_between(
        frame["observed_at"],
        frame["predicted_pair_eta_low"],
        frame["predicted_pair_eta_high"],
        alpha=0.2,
        label="Price-rule sensitivity",
    )
    axes[1].plot(
        frame["observed_at"],
        frame["predicted_pair_eta_frozen"],
        linewidth=1.5,
        label="Frozen eta prediction",
    )
    axes[1].set_ylim(-0.03, 1.03)
    axes[1].set_ylabel("Pair selection share")
    axes[1].set_title("Realized owned selections versus public-price prediction")
    axes[1].legend(frameon=False, ncol=2)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    fig.savefig(output.with_suffix(".pdf"))
    plt.close(fig)


def _plot_nonprice(
    provider_scores: pd.DataFrame,
    manipulation: pd.DataFrame,
    output: Path,
) -> None:
    if provider_scores.empty:
        return
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    shown = provider_scores.copy()
    stable = shown[shown["stable_provider_support"]]
    if not stable.empty:
        shown = stable
    shown = shown.sort_values("relative_log_score").tail(14)
    positions = np.arange(len(shown))
    values = shown["price_equivalent_discount_vs_reference"].to_numpy(dtype=float)
    low = pd.to_numeric(
        shown["price_equivalent_discount_ci_low"], errors="coerce"
    ).to_numpy(dtype=float)
    high = pd.to_numeric(
        shown["price_equivalent_discount_ci_high"], errors="coerce"
    ).to_numpy(dtype=float)
    if np.all(np.isfinite(low)) and np.all(np.isfinite(high)):
        errors = np.vstack([values - low, high - values])
        axes[0].errorbar(values, positions, xerr=errors, fmt="o", color="#2b6f92", capsize=3)
    else:
        axes[0].scatter(values, positions, color="#2b6f92")
    axes[0].axvline(0, color="black", linewidth=1)
    axes[0].set_yticks(positions, shown["provider"])
    axes[0].set_xlabel("Price-equivalent score discount vs Z.AI")
    axes[0].set_title("Latent non-price routing score")
    axes[0].xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")

    if manipulation.empty:
        axes[1].text(0.5, 0.5, "No below-benchmark provider observations", ha="center")
        axes[1].set_axis_off()
    else:
        ordered = manipulation.sort_values("mean_price_only_unilateral_share_gain")
        positions = np.arange(len(ordered))
        before = ordered["mean_price_only_unilateral_share_gain"].to_numpy(dtype=float)
        after = ordered["mean_score_adjusted_unilateral_share_gain"].to_numpy(dtype=float)
        for y, start, end in zip(positions, before, after, strict=True):
            axes[1].plot([start, end], [y, y], color="#9aa1a6", linewidth=1.5)
        axes[1].scatter(before, positions, label="Price only", color="#d16d3a", marker="o")
        axes[1].scatter(after, positions, label="With inferred score", color="#2b6f92", marker="D")
        axes[1].set_yticks(positions, ordered["provider"])
        axes[1].set_xlabel("Unilateral share gain from undercutting benchmark")
        axes[1].set_title("Does scoring attenuate share manipulation?")
        axes[1].xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
        axes[1].legend(frameon=False)
    fig.suptitle("GLM-5.2: observable price manipulation and latent router scoring", y=1.01)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def _table(frame: pd.DataFrame, empty: str) -> str:
    if frame.empty:
        return f"<p>{html.escape(empty)}</p>"
    shown = frame.copy()
    for column in shown.select_dtypes(include="float").columns:
        shown[column] = shown[column].map(lambda value: f"{value:.4g}" if pd.notna(value) else "")
    return shown.to_html(index=False, escape=True, border=0)


def run(data_root: Path, output_dir: Path, *, source_revision: str | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, joined, _ = _frames(data_root)
    (
        run_panel,
        choices,
        policy,
        provider,
        nonprice_provider,
        manipulation,
        rule_panel,
        summary,
    ) = analyze(candidates, joined)
    summary["source_revision"] = source_revision
    for name, frame in (
        ("glm52_run_panel.parquet", run_panel),
        ("glm52_default_choices.parquet", choices),
        ("glm52_policy_metrics.parquet", policy),
        ("glm52_provider_selections.parquet", provider),
        ("glm52_nonprice_provider_scores.parquet", nonprice_provider),
        ("glm52_score_adjusted_undercutting.parquet", manipulation),
        ("glm52_price_sort_rule_contrast.parquet", rule_panel),
    ):
        frame.to_parquet(output_dir / name, index=False)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    plot_path = output_dir / "glm52_routing_monitor.png"
    _plot(run_panel, plot_path)
    nonprice_plot_path = output_dir / "glm52_nonprice_scoring.png"
    _plot_nonprice(nonprice_provider, manipulation, nonprice_plot_path)
    image_html = ""
    if plot_path.exists():
        encoded = base64.b64encode(plot_path.read_bytes()).decode("ascii")
        image_html = f'<img alt="GLM-5.2 routing monitor" src="data:image/png;base64,{encoded}">'
    nonprice_image_html = ""
    if nonprice_plot_path.exists():
        encoded = base64.b64encode(nonprice_plot_path.read_bytes()).decode("ascii")
        nonprice_image_html = (
            f'<img alt="GLM-5.2 non-price scoring" src="data:image/png;base64,{encoded}">'
        )
    scoring_summary = summary["nonprice_scoring"]
    rule_summary = summary["price_sort_rule_contrast"]
    reallocated = scoring_summary.get("mean_probability_mass_reallocated_by_scoring")
    cv_bits = (scoring_summary.get("cross_validated") or {}).get(
        "nonprice_information_bits_per_choice"
    )
    rule_effect = rule_summary.get("price_sorted_minus_default_cheapest_rate")

    def percentage(value: Any) -> str:
        return f"{float(value):.1%}" if value is not None and pd.notna(value) else "not estimated"

    def number(value: Any) -> str:
        return f"{float(value):.3f}" if value is not None and pd.notna(value) else "not estimated"

    dashboard = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>GLM-5.2 routing</title>
<style>
body{{font:14px/1.45 system-ui;max-width:1280px;margin:30px auto;padding:0 18px;
color:#17202a}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
th,td{{padding:7px;border-bottom:1px solid #ddd}}
th{{background:#eef2f5}}img{{width:100%;height:auto}}
.boundary{{border-left:4px solid #b66a00;padding:10px;background:#fff8ed}}
</style></head><body>
<h1>Prospective GLM-5.2 owned-routing panel</h1>
<p>Support: <b>{html.escape(summary["support_status"])}</b>; covered default choices:
{summary["covered_default_choices"]}; blocks: {summary["covered_blocks"]}; duration:
{summary["duration_days"]:.2f} days.</p>{image_html}
<h2>Price manipulation × latent scoring</h2>
<p>Prospective scoring support: <b>{html.escape(scoring_summary["status"])}</b>, beginning
{html.escape(NONPRICE_PROSPECTIVE_START_UTC)}. Mean within-menu probability mass moved by
the fitted score: <b>{percentage(reallocated)}</b>. Cross-validated incremental information:
<b>{number(cv_bits)} bits/choice</b>. Explicit price-sort effect on cheapest-provider selection:
<b>{percentage(rule_effect)}</b>.</p>{nonprice_image_html}
<h3>Relative provider score wedges</h3>
{_table(nonprice_provider, "Score estimation is accruing toward its prospective support gate.")}
<h3>Score-adjusted unilateral undercutting gains</h3>
{_table(manipulation, "Undercutting interaction estimates are not yet support-ready.")}
<h2>Provider selections</h2>{_table(provider, "No covered default selections yet.")}
<h2>Policy and pinned QoS</h2>{_table(policy, "No paid outcomes yet.")}
<p class="boundary">{html.escape(summary["claim_boundary"])}</p></body></html>"""
    (output_dir / "glm52-routing.html").write_text(dashboard, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("input-data"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/analysis/glm52-routing-v1"))
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.data_root, args.output_dir, source_revision=args.source_revision),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
