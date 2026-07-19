"""Aggregate monitor for the isolated paid market-measurement campaign."""

from __future__ import annotations

import argparse
import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..market_measurement import STUDY_ID

MIN_RANKABLE_CELL = 20


def _read_table(data_root: Path, table: str) -> pd.DataFrame:
    paths = sorted((data_root / "curated" / table).glob("dt=*/*.parquet"))
    frames = []
    for path in paths:
        try:
            frames.append(pq.ParquetFile(path).read())
        except (OSError, pa.ArrowInvalid):
            continue
    if not frames:
        return pd.DataFrame()
    return pa.concat_tables(frames, promote_options="permissive").to_pandas()


def _task_id_from_metadata(value: Any) -> str | None:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    task_id = parsed.get("task_id")
    return str(task_id) if task_id else None


def _hhi(series: pd.Series) -> float | None:
    values = series.dropna().astype(str)
    if values.empty:
        return None
    shares = values.value_counts(normalize=True)
    return float((shares**2).sum())


def _quantile(series: pd.Series, q: float) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.quantile(q)) if not values.empty else None


def _joined(data_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    assignments = _read_table(data_root, "market_measurement_assignments")
    attempts = _read_table(data_root, "market_measurement_attempts")
    quality = _read_table(data_root, "market_measurement_quality")
    for frame in (assignments, attempts, quality):
        if not frame.empty and "study_id" in frame:
            frame.drop(frame[frame["study_id"] != STUDY_ID].index, inplace=True)
    if assignments.empty:
        return assignments, attempts, quality
    assignments = assignments.drop_duplicates("task_id", keep="last")
    if attempts.empty:
        joined = assignments.copy()
        joined["attempt_observed_at"] = None
        joined["outcome"] = None
        joined["selected_provider"] = None
        joined["latency_ms"] = None
        joined["cost_usd"] = None
        return joined, attempts, quality
    attempts = attempts.copy()
    attempts["task_id"] = attempts["metadata_json"].map(_task_id_from_metadata)
    attempts = attempts.dropna(subset=["task_id"]).drop_duplicates("task_id", keep="last")
    attempts = attempts.rename(columns={"observed_at": "attempt_observed_at"})
    keep = [
        "task_id",
        "attempt_observed_at",
        "outcome",
        "selected_provider",
        "latency_ms",
        "cost_usd",
        "input_tokens",
        "output_tokens",
        "retry_reason",
    ]
    joined = assignments.merge(attempts[keep], on="task_id", how="left")
    return joined, attempts, quality


def _health(joined: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "run_id",
        "planned",
        "attempted",
        "succeeded",
        "completion_rate",
        "success_rate",
        "realized_cost_usd",
        "manifest_count",
        "integrity_status",
    ]
    if joined.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for run_id, group in joined.groupby("run_id", dropna=False):
        attempted = int(group["attempt_observed_at"].notna().sum())
        succeeded = int((group["outcome"] == "succeeded").sum())
        manifests = int(group["manifest_sha256"].dropna().nunique())
        planned = int(len(group))
        rows.append(
            {
                "run_id": run_id,
                "planned": planned,
                "attempted": attempted,
                "succeeded": succeeded,
                "completion_rate": attempted / planned if planned else None,
                "success_rate": succeeded / attempted if attempted else None,
                "realized_cost_usd": float(
                    pd.to_numeric(group["cost_usd"], errors="coerce").fillna(0).sum()
                ),
                "manifest_count": manifests,
                "integrity_status": (
                    "complete" if attempted == planned and manifests == 1 else "incomplete"
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("run_id")


def _policy_metrics(joined: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "model_id",
        "experiment_axis",
        "policy",
        "assigned",
        "attempted",
        "succeeded",
        "success_rate",
        "selected_provider_count",
        "selected_provider_hhi",
        "median_latency_ms",
        "p95_latency_ms",
        "mean_cost_usd",
        "rankable",
    ]
    if joined.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for keys, group in joined.groupby(
        ["model_id", "experiment_axis", "policy"], dropna=False
    ):
        attempted = int(group["attempt_observed_at"].notna().sum())
        succeeded = int((group["outcome"] == "succeeded").sum())
        successful = group[group["outcome"] == "succeeded"]
        costs = pd.to_numeric(group["cost_usd"], errors="coerce").dropna()
        rows.append(
            {
                "model_id": keys[0],
                "experiment_axis": keys[1],
                "policy": keys[2],
                "assigned": int(len(group)),
                "attempted": attempted,
                "succeeded": succeeded,
                "success_rate": succeeded / attempted if attempted else None,
                "selected_provider_count": int(
                    successful["selected_provider"].dropna().nunique()
                ),
                "selected_provider_hhi": _hhi(successful["selected_provider"]),
                "median_latency_ms": _quantile(successful["latency_ms"], 0.5),
                "p95_latency_ms": _quantile(successful["latency_ms"], 0.95),
                "mean_cost_usd": float(costs.mean()) if not costs.empty else None,
                "rankable": attempted >= MIN_RANKABLE_CELL,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _liquidity_metrics(joined: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "run_id",
        "model_id",
        "requested_provider",
        "concurrency_level",
        "execution_batch",
        "assigned",
        "attempted",
        "succeeded",
        "executable_depth_lower_bound",
        "success_rate",
        "median_latency_ms",
        "p95_latency_ms",
        "quote_cap_usd",
        "realized_cost_usd",
    ]
    liquidity = joined[joined.get("experiment_axis") == "liquidity"] if not joined.empty else joined
    if liquidity.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    keys = [
        "run_id",
        "model_id",
        "requested_provider",
        "concurrency_level",
        "execution_batch",
    ]
    for values, group in liquidity.groupby(keys, dropna=False):
        attempted = int(group["attempt_observed_at"].notna().sum())
        succeeded = int((group["outcome"] == "succeeded").sum())
        rows.append(
            {
                **dict(zip(keys, values, strict=True)),
                "assigned": int(len(group)),
                "attempted": attempted,
                "succeeded": succeeded,
                "executable_depth_lower_bound": succeeded,
                "success_rate": succeeded / attempted if attempted else None,
                "median_latency_ms": _quantile(group["latency_ms"], 0.5),
                "p95_latency_ms": _quantile(group["latency_ms"], 0.95),
                "quote_cap_usd": float(
                    pd.to_numeric(group["task_quote_cap_usd"], errors="coerce")
                    .fillna(0)
                    .sum()
                ),
                "realized_cost_usd": float(
                    pd.to_numeric(group["cost_usd"], errors="coerce").fillna(0).sum()
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _memory_metrics(joined: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "run_id",
        "model_id",
        "seed_provider",
        "repeat_provider",
        "both_observed",
        "same_provider",
    ]
    memory = joined[joined.get("experiment_axis") == "memory"] if not joined.empty else joined
    if memory.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for keys, group in memory.groupby(["run_id", "model_id"], dropna=False):
        providers = group.set_index("policy")["selected_provider"].to_dict()
        seed = providers.get("default_sticky_seed")
        repeat = providers.get("default_sticky_repeat")
        both = pd.notna(seed) and pd.notna(repeat)
        rows.append(
            {
                "run_id": keys[0],
                "model_id": keys[1],
                "seed_provider": seed,
                "repeat_provider": repeat,
                "both_observed": bool(both),
                "same_provider": bool(seed == repeat) if both else None,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _quality_metrics(quality: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "model_id",
        "policy",
        "requested_provider",
        "rows",
        "answered",
        "correct",
        "accuracy_answered",
        "success_rate",
        "median_latency_ms",
        "mean_cost_usd",
        "rankable",
    ]
    if quality.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for keys, group in quality.groupby(
        ["model_id", "policy", "requested_provider"], dropna=False
    ):
        answered = int(group["correct"].notna().sum())
        correct = int((group["correct"] == True).sum())  # noqa: E712
        costs = pd.to_numeric(group["cost_usd"], errors="coerce").dropna()
        rows.append(
            {
                "model_id": keys[0],
                "policy": keys[1],
                "requested_provider": keys[2],
                "rows": int(len(group)),
                "answered": answered,
                "correct": correct,
                "accuracy_answered": correct / answered if answered else None,
                "success_rate": float(group["http_status"].eq(200).mean()),
                "median_latency_ms": _quantile(group["latency_ms"], 0.5),
                "mean_cost_usd": float(costs.mean()) if not costs.empty else None,
                "rankable": answered >= MIN_RANKABLE_CELL,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _table_html(frame: pd.DataFrame, *, empty: str) -> str:
    if frame.empty:
        return f"<p class='empty'>{html.escape(empty)}</p>"
    shown = frame.copy()
    for column in shown.select_dtypes(include="float").columns:
        shown[column] = shown[column].map(lambda value: f"{value:.4g}" if pd.notna(value) else "")
    return shown.to_html(index=False, escape=True, border=0, classes="data")


def run(data_root: Path, output_dir: Path, *, source_revision: str | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    joined, attempts, quality = _joined(data_root)
    health = _health(joined)
    policy = _policy_metrics(joined)
    liquidity = _liquidity_metrics(joined)
    memory = _memory_metrics(joined)
    quality_metrics = _quality_metrics(quality)
    outputs = {
        "measurement-health.parquet": health,
        "policy-metrics.parquet": policy,
        "liquidity-metrics.parquet": liquidity,
        "memory-metrics.parquet": memory,
        "quality-metrics.parquet": quality_metrics,
    }
    for name, frame in outputs.items():
        frame.to_parquet(output_dir / name, index=False)
    summary = {
        "study_id": STUDY_ID,
        "analysis_at": datetime.now(UTC).isoformat(),
        "source_revision": source_revision,
        "assignment_rows": int(len(joined)),
        "attempt_rows": int(len(attempts)),
        "quality_rows": int(len(quality)),
        "complete_runs": int((health.get("integrity_status") == "complete").sum())
        if not health.empty
        else 0,
        "realized_cost_usd": float(health.get("realized_cost_usd", pd.Series(dtype=float)).sum()),
        "minimum_rankable_cell": MIN_RANKABLE_CELL,
        "claim_boundaries": {
            "causal": (
                "Randomized controls identify effects on this account's owned requests only."
            ),
            "liquidity": (
                "Successful synchronized probes are an executable-depth lower bound, not "
                "total provider capacity."
            ),
            "quality": (
                "Accuracy, success, latency, and cost are reported as a vector; no welfare "
                "scalar is identified without external valuations."
            ),
            "excluded": (
                "No market share, cross-user ordering, provider costs, private scores, intent, "
                "front-running, or collusion is identified."
            ),
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    revision_label = html.escape(source_revision or "local")
    health_html = _table_html(health, empty="No paid execution has landed yet.")
    policy_html = _table_html(policy, empty="No policy outcomes yet.")
    liquidity_html = _table_html(liquidity, empty="No synchronized batches yet.")
    memory_html = _table_html(memory, empty="No completed memory pairs yet.")
    quality_html = _table_html(quality_metrics, empty="No graded outcomes yet.")
    excluded = html.escape(summary["claim_boundaries"]["excluded"])
    dashboard = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenRouter market measurement</title><style>
body{{font:14px/1.45 system-ui,sans-serif;max-width:1280px;margin:32px auto;
padding:0 18px;color:#17202a}}
h1{{font-size:25px}}h2{{margin-top:32px}}.meta,.boundary{{background:#f5f7f9;
padding:12px;border-radius:6px}}
.boundary{{border-left:4px solid #b66a00}}table.data{{border-collapse:collapse;
width:100%;font-size:12px}}
.data th,.data td{{padding:7px;border-bottom:1px solid #d8dee4;text-align:left}}
.data th{{background:#eef2f5}}.empty{{color:#667085;font-style:italic}}
code{{background:#eef2f5;padding:2px 4px}}</style></head><body>
<h1>OpenRouter owned-market measurement</h1>
<p class="meta">Study <code>{STUDY_ID}</code>; source revision <code>{revision_label}</code>.
Assignments: {len(joined)}. Attempts: {len(attempts)}. Quality rows: {len(quality)}.</p>
<h2>Run integrity and spend</h2>{health_html}
<h2>Policy outcomes</h2>{policy_html}
<h2>Executable-liquidity batches</h2>{liquidity_html}
<h2>Session-memory pairs</h2>{memory_html}
<h2>Paired quality and generalized-cost components</h2>{quality_html}
<p class="boundary">{excluded}</p>
</body></html>"""
    (output_dir / "market-measurement.html").write_text(dashboard, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("input-data"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/analysis/market-measurement")
    )
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
