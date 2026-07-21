"""Aggregate monitor for the prospective routed-share/quality/memory study."""

from __future__ import annotations

import argparse
import base64
import html
import json
import tomllib
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..glm52_routing import STUDY_ID as GLM_STUDY_ID
from ..price_experiments import collapse_provider_candidates, provider_key
from .score_memory import MemoryConfig, build_history_panel, compare_models, support_summary

ROUTING_STUDY_IDS = {GLM_STUDY_ID, "openrouter-score-memory-routing-v1"}


def _read(root: Path, table: str) -> pd.DataFrame:
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
    task_id = parsed.get("task_id")
    return str(task_id) if task_id else None


def _load_config(path: Path) -> tuple[MemoryConfig, dict[str, Any]]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    memory = raw["memory"]
    study = raw["study"]
    config = MemoryConfig(
        eta=float(study["frozen_eta"]),
        ridge=float(study["ridge"]),
        lag_blocks=tuple(int(value) for value in memory["lag_blocks"]),
        finite_runs=tuple(int(value) for value in memory["finite_runs"]),
        hmm_stay=float(memory["hmm_stay_probability"]),
        hmm_low_emission=float(memory["hmm_undercut_probability_low"]),
        hmm_high_emission=float(memory["hmm_undercut_probability_high"]),
    )
    return config, raw


def _frames(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidates = _read(root, "glm52_routing_candidates")
    assignments = _read(root, "glm52_routing_assignments")
    attempts = _read(root, "glm52_routing_attempts")
    quality = _read(root, "score_memory_quality")
    for frame in (candidates, assignments, attempts):
        if not frame.empty and "study_id" in frame:
            frame.drop(frame[~frame["study_id"].isin(ROUTING_STUDY_IDS)].index, inplace=True)
    if not attempts.empty:
        attempts = attempts.copy()
        attempts["task_id"] = attempts["metadata_json"].map(_task_id)
        attempts = attempts.dropna(subset=["task_id"]).drop_duplicates("task_id", keep="last")
    if not assignments.empty:
        assignments = assignments.drop_duplicates("task_id", keep="last")
    return candidates, assignments, attempts, quality


def build_inputs(
    candidates: pd.DataFrame,
    assignments: pd.DataFrame,
    attempts: pd.DataFrame,
    quality: pd.DataFrame,
    *,
    prospective_start: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], pd.DataFrame]:
    if candidates.empty or assignments.empty:
        return [], [], pd.DataFrame()
    attempts_keep = pd.DataFrame()
    if not attempts.empty:
        keep = [
            column
            for column in (
                "task_id",
                "observed_at",
                "outcome",
                "selected_provider",
                "latency_ms",
                "cost_usd",
            )
            if column in attempts
        ]
        attempts_keep = attempts[keep]
    if attempts_keep.empty:
        joined = assignments.copy()
        for column in (
            "observed_at",
            "outcome",
            "selected_provider",
            "latency_ms",
            "cost_usd",
        ):
            joined[column] = None
    else:
        joined = assignments.merge(attempts_keep, on="task_id", how="left")
    cutoff = pd.Timestamp(prospective_start)
    menus: dict[str, list[dict[str, Any]]] = {}
    menu_times: dict[str, pd.Timestamp] = {}
    for block_id, group in candidates.groupby("block_id", sort=True):
        menu = collapse_provider_candidates(group.to_dict("records"))
        if not menu:
            continue
        timestamp = pd.to_datetime(menu[0].get("observed_at"), utc=True, errors="coerce")
        if pd.isna(timestamp) or timestamp < cutoff:
            continue
        menus[str(block_id)] = menu
        menu_times[str(block_id)] = timestamp

    observations = []
    quality_events = []
    price_rows = []
    for block_id, menu in menus.items():
        providers = [provider_key(row.get("provider_name")) for row in menu]
        costs = np.asarray([float(row["expected_quote_usd"]) for row in menu], dtype=float)
        timestamp = menu_times[block_id]
        for provider, cost in zip(providers, costs, strict=True):
            price_rows.append(
                {
                    "block_id": block_id,
                    "observed_at": timestamp,
                    "provider": provider,
                    "expected_quote_usd": cost,
                }
            )
        block = joined[joined["block_id"].astype(str) == block_id]
        for row in block[block["policy"] == "default_broad"].to_dict("records"):
            selected = provider_key(row.get("selected_provider"))
            if row.get("outcome") != "succeeded" or selected not in providers:
                continue
            observations.append(
                {
                    "block_id": block_id,
                    "task_id": row.get("task_id"),
                    "observed_at": timestamp,
                    "model_id": row.get("model_id"),
                    "providers": providers,
                    "costs": costs,
                    "selected_index": providers.index(selected),
                }
            )
        for row in block[block["policy"].astype(str).str.startswith("pinned_")].to_dict("records"):
            observed = pd.to_datetime(row.get("observed_at"), utc=True, errors="coerce")
            requested = provider_key(row.get("requested_provider"))
            if requested and pd.notna(observed):
                quality_events.append(
                    {
                        "observed_at": observed,
                        "provider": requested,
                        "success": row.get("outcome") == "succeeded",
                        "latency_ms": row.get("latency_ms"),
                        "source": "glm52_pinned_operational",
                    }
                )
    if not quality.empty:
        for row in quality.to_dict("records"):
            if str(row.get("policy") or "").startswith("router_"):
                continue
            observed = pd.to_datetime(row.get("observed_at"), utc=True, errors="coerce")
            if pd.isna(observed) or observed < cutoff:
                continue
            requested = provider_key(row.get("requested_provider") or row.get("selected_provider"))
            if requested:
                quality_events.append(
                    {
                        "observed_at": observed,
                        "provider": requested,
                        "success": row.get("http_status") == 200,
                        "latency_ms": row.get("latency_ms"),
                        "correct": row.get("correct"),
                        "source": "score_memory_quality_bank",
                    }
                )
    return observations, quality_events, pd.DataFrame(price_rows)


def _quality_aggregate(events: list[dict[str, Any]]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame()
    frame = pd.DataFrame(events)
    frame["success"] = frame["success"].astype(float)
    frame["correct_numeric"] = (
        frame["correct"].map(lambda value: float(bool(value)) if pd.notna(value) else np.nan)
        if "correct" in frame
        else np.nan
    )
    return (
        frame.groupby(["provider", "source"], as_index=False)
        .agg(
            observations=("success", "size"),
            success_rate=("success", "mean"),
            fidelity_rate=("correct_numeric", "mean"),
            median_latency_ms=("latency_ms", "median"),
        )
        .sort_values(["source", "provider"])
    )


def _policy_aggregate(quality: pd.DataFrame) -> pd.DataFrame:
    if quality.empty or "policy" not in quality:
        return pd.DataFrame()
    frame = quality[quality["policy"].astype(str).str.startswith("router_")].copy()
    if frame.empty:
        return frame
    frame["success"] = frame["http_status"].eq(200).astype(float)
    frame["correct_numeric"] = frame["correct"].map(
        lambda value: float(bool(value)) if pd.notna(value) else np.nan
    )
    frame["qualified"] = frame["success"] * frame["correct_numeric"].fillna(0.0)
    frame["cost_usd"] = pd.to_numeric(frame["cost_usd"], errors="coerce")
    output = (
        frame.groupby("policy", as_index=False)
        .agg(
            assigned=("task_id", "size"),
            blocks=("run_id", "nunique"),
            success_rate=("success", "mean"),
            fidelity_rate=("correct_numeric", "mean"),
            qualified_completions=("qualified", "sum"),
            spend_usd=("cost_usd", "sum"),
            median_latency_ms=("latency_ms", "median"),
        )
        .sort_values("policy")
    )
    output["qualified_completions_per_dollar"] = output["qualified_completions"] / output[
        "spend_usd"
    ].replace(0, np.nan)
    return output


def _plots(models: pd.DataFrame, prices: pd.DataFrame, quality: pd.DataFrame, output: Path) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, axes = plt.subplots(3, 1, figsize=(12, 12))
    if models.empty:
        axes[0].text(0.5, 0.5, "Future-fold model comparison is support-gated", ha="center")
        axes[0].set_axis_off()
    else:
        shown = (
            models[~models["model"].str.startswith("placebo")]
            .head(12)
            .sort_values("gain_bits_per_choice")
        )
        axes[0].barh(shown["model"], shown["gain_bits_per_choice"], color="#2b6f92")
        axes[0].axvline(0, color="black", linewidth=1)
        axes[0].set_xlabel("Held-out gain over no memory (bits / owned choice)")
        axes[0].set_title("Frozen dynamic model family")
    if prices.empty:
        axes[1].text(0.5, 0.5, "No prospective public-menu prices", ha="center")
        axes[1].set_axis_off()
    else:
        pivot = prices.pivot_table(
            index="observed_at", columns="provider", values="expected_quote_usd", aggfunc="last"
        )
        for provider in pivot.median().sort_values().index[:6]:
            axes[1].plot(pivot.index, pivot[provider], label=provider, linewidth=1.2)
        axes[1].set_yscale("log")
        axes[1].set_ylabel("Request-shaped quote (USD, log scale)")
        axes[1].set_title("Prospective exact-menu price histories")
        axes[1].legend(frameon=False, ncol=3)
    if quality.empty:
        axes[2].text(0.5, 0.5, "Quality bank is accruing", ha="center")
        axes[2].set_axis_off()
    else:
        shown = quality.sort_values("observations", ascending=False).head(12)
        axes[2].scatter(shown["success_rate"], shown["median_latency_ms"], s=40)
        for row in shown.to_dict("records"):
            axes[2].annotate(
                row["provider"], (row["success_rate"], row["median_latency_ms"]), fontsize=8
            )
        axes[2].set_xlabel("Success rate")
        axes[2].set_ylabel("Median latency (ms)")
        axes[2].set_title("Lagged operational and fidelity support")
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
        shown[column] = shown[column].map(lambda value: f"{value:.5g}" if pd.notna(value) else "")
    return shown.to_html(index=False, escape=True, border=0)


def run(
    data_root: Path,
    output_dir: Path,
    *,
    config_path: Path = Path("config/score_memory_v1.toml"),
    source_revision: str | None = None,
) -> dict[str, Any]:
    config, raw = _load_config(config_path)
    candidates, assignments, attempts, quality = _frames(data_root)
    observations, quality_events, prices = build_inputs(
        candidates,
        assignments,
        attempts,
        quality,
        prospective_start=str(raw["study"]["prospective_start_utc"]),
    )
    panel = build_history_panel(observations, quality_events, config=config)
    model_table, _private_losses = compare_models(panel, config=config)
    gates = raw["support"]
    summary = support_summary(
        panel,
        quality_events,
        model_table,
        minimum_choices=int(gates["minimum_choices"]),
        minimum_blocks=int(gates["minimum_blocks"]),
        minimum_days=float(gates["minimum_days"]),
        minimum_providers=int(gates["minimum_providers"]),
    )
    summary.update(
        {
            "study_id": str(raw["study"]["study_id"]),
            "prospective_start_utc": str(raw["study"]["prospective_start_utc"]),
            "source_revision": source_revision,
            "frozen_eta": config.eta,
            "frozen_lag_blocks": list(config.lag_blocks),
            "frozen_finite_runs": list(config.finite_runs),
        }
    )
    quality_aggregate = _quality_aggregate(quality_events)
    policy_aggregate = _policy_aggregate(quality)
    policy_blocks = int(policy_aggregate["blocks"].min()) if not policy_aggregate.empty else 0
    summary["owned_router_policy_blocks_per_arm_min"] = policy_blocks
    summary["owned_router_policy_status"] = (
        "ready" if policy_blocks >= int(gates["minimum_randomized_blocks_per_arm"]) else "accruing"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    model_table.to_parquet(output_dir / "score_memory_model_comparison.parquet", index=False)
    quality_aggregate.to_parquet(output_dir / "score_memory_quality_aggregate.parquet", index=False)
    policy_aggregate.to_parquet(output_dir / "score_memory_policy_aggregate.parquet", index=False)
    (output_dir / "score_memory_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    plot = output_dir / "score_memory_panel.png"
    _plots(model_table, prices, quality_aggregate, plot)
    image_html = ""
    if plot.exists():
        image_html = (
            '<img alt="score memory panel" src="data:image/png;base64,'
            + base64.b64encode(plot.read_bytes()).decode("ascii")
            + '">'
        )
    model_html = _table(model_table, "Model comparison waits for 30 prospective blocks.")
    quality_html = _table(quality_aggregate, "Quality observations are accruing.")
    policy_html = _table(policy_aggregate, "Policy blocks are accruing.")
    dashboard = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Score memory</title>
<style>
body{{font:14px/1.45 system-ui;max-width:1280px;margin:30px auto;padding:0 18px;
color:#17202a}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
th,td{{padding:7px;border-bottom:1px solid #ddd}}
th{{background:#eef2f5}}img{{width:100%;height:auto}}
.boundary{{border-left:4px solid #b66a00;padding:10px;background:#fff8ed}}
</style></head><body><h1>Owned routed share × quality × memory</h1>
<p>Status: <b>{html.escape(summary["support_status"])}</b>;
choices: {summary["covered_choices"]}; blocks: {summary["blocks"]};
days: {summary["duration_days"]:.2f}; price events: {summary["price_events"]};
quality events: {summary["quality_events"]}.</p>{image_html}
<h2>Future-fold model comparison</h2>{model_html}
<h2>Quality support</h2>{quality_html}
<h2>Randomized owned-router policy trial</h2>{policy_html}
<p class="boundary">{html.escape(summary["claim_boundary"])}</p>
</body></html>"""
    (output_dir / "score-memory.html").write_text(dashboard, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("input-data"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/analysis/score-memory-v1"))
    parser.add_argument("--config", type=Path, default=Path("config/score_memory_v1.toml"))
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.data_root,
                args.output_dir,
                config_path=args.config,
                source_revision=args.source_revision,
            ),
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
