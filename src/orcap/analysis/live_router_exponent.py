"""Rolling price-exponent analysis for owned OpenRouter routing choices."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..capture_api import write_partition
from ..config import DATA_DIR, dt_partition, run_timestamp
from ..price_experiments import provider_key
from .router_exponent import (
    PRIMARY_POLICIES,
    block_bootstrap_interval,
    fit_exponent,
    probabilities,
    score,
    support_status,
)

STUDY_ID = "openrouter-live-price-exponent-v1"
OWNED_STUDIES = {
    "openrouter-route-calibration-v1",
    "openrouter-price-response-v1",
    "openrouter-market-measurement-v1",
    "openrouter-glm52-routing-v1",
}


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_observations(
    candidates: pd.DataFrame, assignments: pd.DataFrame, attempts: pd.DataFrame
) -> list[dict[str, Any]]:
    """Join frozen public menus to redacted owned selections by planned task."""
    if candidates.empty or assignments.empty or attempts.empty:
        return []
    attempts = attempts[attempts["study_id"].isin(OWNED_STUDIES)].copy()
    if attempts.empty:
        return []
    attempts["_metadata"] = attempts["metadata_json"].map(_metadata)
    attempts["task_id"] = attempts["_metadata"].map(lambda item: item.get("task_id"))
    attempts = (
        attempts.dropna(subset=["task_id"])
        .sort_values("observed_at")
        .drop_duplicates(["study_id", "task_id"], keep="last")
    )
    assignments = assignments[assignments["policy"].isin(PRIMARY_POLICIES)].copy()
    assignments = assignments.drop_duplicates("task_id", keep="last")
    attempts = attempts.rename(columns={"observed_at": "attempt_observed_at"})
    joined = assignments.merge(
        attempts[
            [
                "task_id",
                "attempt_observed_at",
                "selected_provider",
                "outcome",
                "cost_usd",
                "latency_ms",
            ]
        ],
        on="task_id",
        how="inner",
        validate="one_to_one",
    )
    menus: dict[str, list[dict[str, Any]]] = {}
    for block_id, group in candidates.groupby("block_id", sort=True):
        compatible = group[group["compatible"].fillna(False)].copy()
        compatible["provider_key"] = compatible["provider_name"].map(provider_key)
        compatible = compatible.dropna(subset=["expected_quote_usd"])
        compatible = compatible[compatible["expected_quote_usd"] > 0]
        compatible = compatible.sort_values(["expected_quote_usd", "provider_key"])
        compatible = compatible.drop_duplicates("provider_key", keep="first")
        menus[str(block_id)] = compatible.to_dict("records")
    rows = []
    for row in joined.to_dict("records"):
        menu = menus.get(str(row["block_id"]), [])
        providers = [provider_key(item.get("provider_name")) for item in menu]
        selected = provider_key(row.get("selected_provider"))
        rows.append(
            {
                "task_id": row["task_id"],
                "run_id": row.get("run_id"),
                "block_id": row["block_id"],
                "model_id": row.get("model_id"),
                "shape_id": row.get("shape_id"),
                "policy": row.get("policy"),
                "observed_at": row["attempt_observed_at"],
                "providers": providers,
                "costs": np.asarray(
                    [float(item["expected_quote_usd"]) for item in menu], dtype=float
                ),
                "selected_provider": selected or None,
                "selected_index": providers.index(selected) if selected in providers else None,
                "outcome": row.get("outcome"),
                "realized_cost_usd": row.get("cost_usd"),
                "latency_ms": row.get("latency_ms"),
            }
        )
    return rows


def _windows(
    observations: list[dict[str, Any]], *, now: datetime
) -> list[tuple[str, list[dict[str, Any]]]]:
    parsed = []
    for row in observations:
        at = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
        parsed.append((at.astimezone(UTC), row))
    windows = [("expanding", observations)]
    for label, delta in (
        ("trailing_24h", timedelta(hours=24)),
        ("trailing_7d", timedelta(days=7)),
        ("trailing_28d", timedelta(days=28)),
    ):
        cutoff = now - delta
        windows.append((label, [row for at, row in parsed if at >= cutoff]))
    return windows


def estimate_windows(
    observations: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    bootstrap_draws: int = 200,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    estimates, scores = [], []
    for window_id, rows in _windows(observations, now=now):
        support = support_status(rows)
        fit = fit_exponent(rows, minimum=20)
        bootstrap_low, bootstrap_high = block_bootstrap_interval(
            rows, draws=bootstrap_draws, minimum=20
        )
        eta = fit.get("eta_hat")
        published_eta = eta if support["status"] == "ready" else None
        reference = {}
        if published_eta is not None:
            for size in (2, 3, 5):
                costs = np.asarray([1.25**index for index in range(size)], dtype=float)
                reference[f"cheapest_probability_n{size}"] = float(
                    probabilities(costs, float(published_eta))[0]
                )
        estimates.append(
            {
                "study_id": STUDY_ID,
                "analysis_at": now.isoformat(),
                "window_id": window_id,
                "support_status": support["status"],
                "support_failures": ",".join(support["failures"]),
                "observations": support["observations"],
                "covered_choices": support["covered_choices"],
                "models": support["models"],
                "providers": support["providers"],
                "blocks": support["blocks"],
                "candidate_coverage": support["candidate_coverage"],
                "provider_concentration": support["selected_provider_concentration"],
                "log_price_ratio_iqr": support["log_price_ratio_iqr"],
                "eta_exploratory": eta,
                "eta_published": published_eta,
                "eta_profile_ci_low": fit.get("eta_profile_ci_low"),
                "eta_profile_ci_high": fit.get("eta_profile_ci_high"),
                "eta_block_bootstrap_low": bootstrap_low,
                "eta_block_bootstrap_high": bootstrap_high,
                **reference,
                "claim_boundary": (
                    "Price sensitivity for owned default-policy probes conditional on the "
                    "frozen public menu; not market-wide demand elasticity."
                ),
            }
        )
        if fit.get("fit_ready"):
            scores.append(
                {
                    "study_id": STUDY_ID,
                    "analysis_at": now.isoformat(),
                    "window_id": window_id,
                    "model_spec": "inverse_price_global",
                    **score(rows, float(eta)),
                }
            )
    return pd.DataFrame(estimates), pd.DataFrame(scores)


def render_dashboard(estimates: pd.DataFrame, scores: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    for row in estimates.to_dict("records"):
        value = (
            f"{row['eta_published']:.3f}"
            if row.get("eta_published") is not None and not pd.isna(row["eta_published"])
            else "withheld"
        )
        cards.append(
            "<section><h2>"
            + str(row["window_id"])
            + "</h2><p class='eta'>eta: "
            + value
            + "</p><p>"
            + str(row["support_status"])
            + " | choices "
            + str(row["covered_choices"])
            + " | models "
            + str(row["models"])
            + " | providers "
            + str(row["providers"])
            + "</p></section>"
        )
    score_table = scores.to_html(index=False, border=0) if not scores.empty else "<p>No scores.</p>"
    html = (
        """<!doctype html><meta charset="utf-8"><title>Router price exponent</title>
<style>body{font:15px system-ui;max-width:1100px;margin:40px auto;padding:0 20px;color:#17202a}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
section{border:1px solid #ccd3da;border-radius:8px;padding:16px}.eta{font-size:26px;margin:8px 0}
table{border-collapse:collapse;width:100%;margin-top:24px}
th,td{padding:7px;border-bottom:1px solid #ddd}
</style><h1>Live owned-routing price exponent</h1><p>Unsupported windows withhold eta by design.</p>
<main>"""
        + "".join(cards)
        + "</main><h2>Predictive scores</h2>"
        + score_table
    )
    output.write_text(html, encoding="utf-8")


def _read_tables(root: Path, names: tuple[str, ...]) -> pd.DataFrame:
    frames = []
    for name in names:
        paths = sorted((root / "curated" / name).glob("dt=*/*.parquet"))
        for path in paths:
            frames.append(pq.ParquetFile(path).read().to_pandas())
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def run(data_root: Path = DATA_DIR) -> dict[str, Any]:
    candidates = _read_tables(
        data_root,
        (
            "router_calibration_candidates",
            "price_response_candidates",
            "market_measurement_candidates",
            "glm52_routing_candidates",
        ),
    )
    assignments = _read_tables(
        data_root,
        (
            "router_calibration_assignments",
            "price_response_assignments",
            "market_measurement_assignments",
            "glm52_routing_assignments",
        ),
    )
    attempts = _read_tables(
        data_root,
        ("router_route_attempts", "market_measurement_attempts"),
    )
    observations = build_observations(candidates, assignments, attempts)
    estimates, scores = estimate_windows(observations)
    run_id, dt = run_timestamp(), dt_partition()
    source_revision = os.environ.get("ORCAP_HF_REVISION")
    estimates["analysis_run_id"] = run_id
    estimates["source_mode"] = "pinned_hf_snapshot"
    estimates["source_revision"] = source_revision
    if not scores.empty:
        scores["analysis_run_id"] = run_id
        scores["source_mode"] = "pinned_hf_snapshot"
        scores["source_revision"] = source_revision
    analysis_dir = data_root / "analysis"
    estimate_path = write_partition(
        pa.Table.from_pandas(estimates, preserve_index=False),
        "router_exponent_estimates",
        run_id,
        dt,
        analysis_dir,
    )
    score_path = None
    if not scores.empty:
        score_path = write_partition(
            pa.Table.from_pandas(scores, preserve_index=False),
            "router_exponent_scores",
            run_id,
            dt,
            analysis_dir,
        )
    dashboard = data_root / "reports" / "router-price-exponent.html"
    render_dashboard(estimates, scores, dashboard)
    return {
        "observations": len(observations),
        "source_revision": source_revision,
        "estimate_path": str(estimate_path),
        "score_path": str(score_path) if score_path else None,
        "dashboard": str(dashboard),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    print(json.dumps(run(args.data_root), indent=2))


if __name__ == "__main__":
    main()
