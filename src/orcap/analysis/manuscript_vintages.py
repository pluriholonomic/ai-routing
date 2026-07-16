"""Execute the manuscript's frozen nine-day and earliest 30-day vintages.

The promotion gate names five analyses whose short-panel and confirmatory
estimates must be released side by side.  This module makes that contract
executable.  It selects date prefixes without reading an outcome, runs the
same code at both cutoffs, copies versioned artifacts into the publishable
analysis root, and records hashes plus a fixed metric comparison.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from . import data
from .bm1_pricing_technology import run as run_bm1
from .bm2_fast_slow_reactions import run as run_bm2
from .bm3_quality_adjusted_premium import run as run_bm3
from .bm4_reaction_rules import run as run_bm4
from .bm_common import completion_events
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes
from .pm1_hazard_baseline import run as run_pm1
from .vintage import observed_dates

FROZEN_DAYS = 9
CONFIRMATORY_DAYS = 30
SIGN_METRICS = {
    "pm1_abs_gap_coef": "positive",
    "bm2_fast_after_slow_uplift": "positive",
    "bm3_cadence_beta_fast": "negative",
    "bm3_quality_beta_fast": "negative",
    "bm4_paired_mse_improvement": "positive",
    "bm4_brown_mackay_rmse_gain": "positive",
}


def registered_vintage_specs(values: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """Select outcome-free calendar prefixes fixed by the manuscript."""
    dates = observed_dates(values)

    def spec(label: str, target: int) -> dict[str, Any]:
        ready = len(dates) >= target
        selected = dates[:target] if ready else []
        return {
            "label": label,
            "ready": ready,
            "target_days": target,
            "observed_days": len(dates),
            "remaining_days": max(0, target - len(dates)),
            "dates": selected,
            "start_date": selected[0] if selected else None,
            "end_date": selected[-1] if selected else None,
        }

    return {
        "frozen_9d": spec("frozen_9d", FROZEN_DAYS),
        "confirmatory_30d": spec("confirmatory_30d", CONFIRMATORY_DAYS),
    }


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return round(parsed, 12) if pd.notna(parsed) else None


def _number_list(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)):
        return None
    parsed = [_number(item) for item in value]
    return [item for item in parsed if item is not None] if all(
        item is not None for item in parsed
    ) else None


def precommitted_metrics(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Extract the fixed side-by-side estimands; no metric discovery is allowed."""
    pm1 = results["pm1_hazard_baseline"]
    bm1 = results["bm1_pricing_technology"]
    bm2 = results["bm2_fast_slow_reactions"]
    bm3 = results["bm3_quality_adjusted_premium"]
    bm4 = results["bm4_reaction_rules"]
    pm1_l3 = ((pm1.get("ladder") or {}).get("L3") or {}).get("key_coefs") or {}
    bm2_focal = bm2.get("fast_response_after_slow_initiator") or {}
    bm3_cadence = bm3.get("cadence_only") or {}
    bm3_quality = bm3.get("quality_adjusted") or {}
    state_rmse = _number((bm4.get("state_only_holdout") or {}).get("rmse"))
    brown_rmse = _number((bm4.get("brown_mackay_holdout") or {}).get("rmse"))
    paired = bm4.get("paired_predictive_test") or {}
    rmse_gain = (
        state_rmse - brown_rmse
        if state_rmse is not None and brown_rmse is not None
        else None
    )
    cadence = bm1.get("cadence_counts") or {}
    active = sum(int(cadence.get(name, 0)) for name in ("intraday", "daily", "weekly", "episodic"))
    fast = int(cadence.get("intraday", 0)) + int(cadence.get("daily", 0))
    return {
        "pm1_pair_days": int(pm1.get("n_pair_days", 0)),
        "pm1_events": int(pm1.get("n_events", 0)),
        "pm1_base_daily_hazard": _number(pm1.get("base_daily_hazard")),
        "pm1_abs_gap_coef": _number(pm1_l3.get("abs_gap")),
        "bm1_price_changes": int(bm1.get("n_price_changes", 0)),
        "bm1_repricing_providers": int(bm1.get("n_repricing_providers", 0)),
        "bm1_fast_share_active": fast / active if active else None,
        "bm2_independent_waves": int(bm2.get("n_independent_waves", 0)),
        "bm2_slow_risk_pairs": int(bm2_focal.get("n", 0)),
        "bm2_fast_after_slow_uplift": _number(bm2_focal.get("uplift")),
        "bm2_fast_after_slow_ci95": _number_list(bm2_focal.get("ci95")),
        "bm3_cadence_beta_fast": _number(bm3_cadence.get("beta_fast")),
        "bm3_cadence_ci95": _number_list(bm3_cadence.get("ci95")),
        "bm3_quality_beta_fast": _number(bm3_quality.get("beta_fast")),
        "bm3_quality_ci95": _number_list(bm3_quality.get("ci95")),
        "bm4_linked_reactions": int(bm4.get("n_linked_reactions", 0)),
        "bm4_paired_mse_improvement": _number(paired.get("mse_improvement")),
        "bm4_paired_mse_ci95": _number_list(
            paired.get("model_cluster_bootstrap_ci95")
        ),
        "bm4_exact_sign_flip_p_positive": _number(
            paired.get("exact_sign_flip_p_positive")
        ),
        "bm4_predictive_verdict": paired.get("verdict"),
        "bm4_state_only_rmse": state_rmse,
        "bm4_brown_mackay_rmse": brown_rmse,
        "bm4_brown_mackay_rmse_gain": rmse_gain,
    }


def compare_precommitted_metrics(
    frozen: dict[str, Any], confirmatory: dict[str, Any]
) -> list[dict[str, Any]]:
    """Fixed metric-by-metric comparison for the registered release."""
    rows = []
    for metric in frozen:
        old = frozen.get(metric)
        new = confirmatory.get(metric)
        old_number = _number(old)
        new_number = _number(new)
        direction = SIGN_METRICS.get(metric)
        sign_preserved = None
        if direction and old_number is not None and new_number is not None:
            sign_preserved = (old_number >= 0) == (new_number >= 0)
        relative_change = None
        if old_number not in (None, 0.0) and new_number is not None:
            relative_change = (new_number - old_number) / abs(old_number)
        rows.append(
            {
                "metric": metric,
                "frozen_9d": old,
                "confirmatory_30d": new,
                "registered_direction": direction,
                "sign_preserved": sign_preserved,
                "relative_change": relative_change,
            }
        )
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical_json(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_canonical_json(item) for item in value]
    if isinstance(value, float):
        return _number(value)
    return value


def _canonical_copy(source: Path, target: Path) -> None:
    if source.suffix == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        target.write_text(
            json.dumps(_canonical_json(payload), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return
    frame = pd.read_parquet(source)

    def stable_float(value: Any) -> Any:
        if pd.isna(value) or not math.isfinite(float(value)):
            return value
        value = float(value)
        if abs(value) < 1e-6:
            return 0.0
        decimal_places = 8 - int(math.floor(math.log10(abs(value))))
        return round(value, decimal_places)

    for column in frame.select_dtypes(include=["floating"]).columns:
        frame[column] = frame[column].map(stable_float)
    if not frame.empty:
        sort_key = frame.astype(str).agg("\x1f".join, axis=1)
        frame = frame.iloc[sort_key.sort_values(kind="mergesort").index].reset_index(
            drop=True
        )
    frame.to_parquet(target, index=False)


def _publish_artifacts(run_dir: Path, out_dir: Path, label: str) -> list[dict[str, Any]]:
    artifacts = []
    for source in sorted([*run_dir.glob("*.json"), *run_dir.glob("*.parquet")]):
        target = out_dir / f"mv_{label}_{source.name}"
        _canonical_copy(source, target)
        artifacts.append(
            {
                "path": target.name,
                "sha256": _sha256(target),
                "bytes": target.stat().st_size,
            }
        )
    return artifacts


def _run_vintage(
    out_dir: Path,
    spec: dict[str, Any],
    *,
    events: pd.DataFrame,
    quotes: pd.DataFrame,
) -> dict[str, Any]:
    label = str(spec["label"])
    start_date = str(spec["start_date"])
    end_date = str(spec["end_date"])
    run_dir = out_dir / ".manuscript_vintages" / label
    results = {
        "pm1_hazard_baseline": run_pm1(
            run_dir, start_date=start_date, end_date=end_date
        ),
        "bm1_pricing_technology": run_bm1(
            run_dir,
            start_date=start_date,
            end_date=end_date,
            events=events,
            quotes=quotes,
        ),
        "bm2_fast_slow_reactions": run_bm2(
            run_dir,
            start_date=start_date,
            end_date=end_date,
            events=events,
            quotes=quotes,
        ),
        "bm3_quality_adjusted_premium": run_bm3(
            run_dir,
            start_date=start_date,
            end_date=end_date,
            events=events,
            quotes=quotes,
        ),
        "bm4_reaction_rules": run_bm4(
            run_dir,
            start_date=start_date,
            end_date=end_date,
            events=events,
            quotes=quotes,
        ),
    }
    return {
        **spec,
        "metrics": precommitted_metrics(results),
        "artifacts": _publish_artifacts(run_dir, out_dir, label),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    endpoint_dates = data.q(
        f"""
        select distinct cast(dt as varchar) as dt
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        order by 1
        """
    ).df()["dt"].tolist()
    specs = registered_vintage_specs(endpoint_dates)
    events = completion_events()
    quotes = daily_quotes()
    completed: dict[str, Any] = {}
    for label, spec in specs.items():
        completed[label] = (
            _run_vintage(out_dir, spec, events=events, quotes=quotes)
            if spec["ready"]
            else spec
        )

    comparison: list[dict[str, Any]] = []
    if completed["frozen_9d"].get("metrics") and completed["confirmatory_30d"].get(
        "metrics"
    ):
        comparison = compare_precommitted_metrics(
            completed["frozen_9d"]["metrics"],
            completed["confirmatory_30d"]["metrics"],
        )
    save(pd.DataFrame(comparison), out_dir, "manuscript_vintage_comparison")
    summary = {
        "evidence_status": (
            "side_by_side_ready" if comparison else "frozen_vintage_only"
        ),
        "vintages": completed,
        "comparison": comparison,
        "registered_sign_metrics": SIGN_METRICS,
        "selection_rule": (
            "Run the same five analysis programs on the earliest nine observed quote dates and "
            "the earliest 30 observed quote dates. Later dates are continuation data."
        ),
        "claim_boundary": (
            "The nine-day vintage is descriptive. No 30-day estimate is computed before the "
            "calendar gate, and the fixed comparison table cannot add metrics after seeing the "
            "confirmatory vintage."
        ),
    }
    save_json(summary, out_dir, "manuscript_vintage_summary")
    return summary
