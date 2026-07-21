"""Prospective dynamic score-memory measurement on exact owned-request menus.

The module deliberately separates a current reduced-form provider score from a
law of motion.  Current price always enters as a frozen inverse-power offset.
Only features available before a block may enter a memory model; same-block
pinned outcomes update state after that block's choices.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp


@dataclass(frozen=True)
class MemoryConfig:
    eta: float = 1.6482780609377246
    ridge: float = 1.0
    lag_blocks: tuple[int, ...] = (1, 4, 16, 48, 96, 288, 672)
    finite_runs: tuple[int, ...] = (1, 4, 16, 48)
    hmm_stay: float = 0.95
    hmm_low_emission: float = 0.80
    hmm_high_emission: float = 0.20


DEFAULT_CONFIG = MemoryConfig()


def _provider(value: Any) -> str:
    return str(value or "").strip().casefold()


def _decay(half_life: int) -> float:
    return math.exp(-math.log(2.0) / max(1, int(half_life)))


def _quality_signal(event: Mapping[str, Any]) -> tuple[float, float, float, float]:
    succeeded = event.get("success")
    if succeeded is None:
        succeeded = event.get("outcome") == "succeeded"
    success = float(bool(succeeded)) - 1.0
    latency = event.get("latency_ms")
    try:
        latency_signal = -math.log(max(float(latency), 1.0) / 1000.0)
    except (TypeError, ValueError):
        latency_signal = 0.0
    correct = event.get("correct")
    fidelity = float(bool(correct)) - 0.5 if correct is not None else 0.0
    return success, latency_signal, fidelity, 1.0


def build_history_panel(
    observations: Sequence[Mapping[str, Any]],
    quality_events: Sequence[Mapping[str, Any]] = (),
    *,
    config: MemoryConfig = DEFAULT_CONFIG,
) -> list[dict[str, Any]]:
    """Build choice rows with strictly lagged price and quality features."""

    cleaned = []
    for row in observations:
        providers = [_provider(value) for value in row.get("providers", [])]
        costs = np.asarray(row.get("costs", []), dtype=float)
        selected = row.get("selected_index")
        observed_at = pd.to_datetime(row.get("observed_at"), utc=True, errors="coerce")
        if (
            selected is None
            or not providers
            or len(providers) != len(costs)
            or len(set(providers)) != len(providers)
            or np.any(~np.isfinite(costs))
            or np.any(costs <= 0)
            or pd.isna(observed_at)
        ):
            continue
        cleaned.append(
            {
                **dict(row),
                "providers": providers,
                "costs": costs,
                "selected_index": int(selected),
                "observed_at": observed_at,
                "block_id": str(row.get("block_id") or ""),
            }
        )
    cleaned.sort(key=lambda row: (row["observed_at"], row["block_id"], str(row.get("task_id"))))
    if not cleaned:
        return []

    events = []
    for event in quality_events:
        provider = _provider(event.get("provider") or event.get("requested_provider"))
        timestamp = pd.to_datetime(event.get("observed_at"), utc=True, errors="coerce")
        if provider and pd.notna(timestamp):
            events.append((timestamp, provider, _quality_signal(event)))
    events.sort(key=lambda item: item[0])
    event_index = 0

    price_state: dict[int, defaultdict[str, float]] = {
        h: defaultdict(float) for h in config.lag_blocks
    }
    quality_state: dict[int, dict[str, defaultdict[str, float]]] = {
        h: {
            "success": defaultdict(float),
            "latency": defaultdict(float),
            "fidelity": defaultdict(float),
            "seen": defaultdict(float),
        }
        for h in config.lag_blocks
    }
    undercut_run: defaultdict[str, int] = defaultdict(int)
    regime_belief: defaultdict[str, float] = defaultdict(lambda: 0.5)
    panel: list[dict[str, Any]] = []

    grouped: dict[tuple[pd.Timestamp, str], list[dict[str, Any]]] = defaultdict(list)
    for row in cleaned:
        grouped[(row["observed_at"], row["block_id"])].append(row)

    for (timestamp, _block_id), choices in sorted(grouped.items(), key=lambda item: item[0]):
        # External quality observations strictly before the current block may
        # update state. Events at the same timestamp are intentionally delayed.
        pending_quality: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
        while event_index < len(events) and events[event_index][0] < timestamp:
            _, provider, signal = events[event_index]
            pending_quality[provider].append(signal)
            event_index += 1
        known = set(undercut_run)
        for states in price_state.values():
            known.update(states)
        for h in config.lag_blocks:
            decay = _decay(h)
            for provider in known | set(pending_quality):
                for name in ("success", "latency", "fidelity", "seen"):
                    quality_state[h][name][provider] *= decay
            for provider, signals in pending_quality.items():
                signal = np.asarray(signals, dtype=float).mean(axis=0)
                for index, name in enumerate(("success", "latency", "fidelity", "seen")):
                    quality_state[h][name][provider] += (1 - decay) * float(signal[index])

        menu = choices[0]
        providers = menu["providers"]
        costs = menu["costs"]
        benchmark = float(np.median(costs))
        current_ratio = np.log(costs / benchmark)
        features: dict[str, np.ndarray] = {"current_price_ratio": current_ratio.copy()}
        for h in config.lag_blocks:
            features[f"price_h{h}"] = np.asarray([price_state[h][p] for p in providers])
            for name in ("success", "latency", "fidelity", "seen"):
                features[f"{name}_h{h}"] = np.asarray(
                    [quality_state[h][name][p] for p in providers]
                )
        for run in config.finite_runs:
            features[f"run_ge_{run}"] = np.asarray(
                [float(undercut_run[p] >= run) for p in providers]
            )
        features["regime_low_prob"] = np.asarray([regime_belief[p] for p in providers])

        for choice in choices:
            panel.append(
                {
                    **choice,
                    "features": {name: values.copy() for name, values in features.items()},
                    "date": timestamp.strftime("%Y-%m-%d"),
                }
            )

        # Current menu information becomes available only after the block has
        # been scored. Missing providers decay toward the neutral price state.
        all_known = known | set(providers)
        for h in config.lag_blocks:
            decay = _decay(h)
            local = dict(zip(providers, current_ratio, strict=True))
            for provider in all_known:
                price_state[h][provider] = decay * price_state[h][provider] + (
                    (1 - decay) * float(local[provider]) if provider in local else 0.0
                )
        for provider, ratio in zip(providers, current_ratio, strict=True):
            undercut = bool(ratio < -1e-9)
            undercut_run[provider] = undercut_run[provider] + 1 if undercut else 0
            prior = regime_belief[provider]
            predicted = config.hmm_stay * prior + (1 - config.hmm_stay) * (1 - prior)
            low_like = config.hmm_low_emission if undercut else 1 - config.hmm_low_emission
            high_like = config.hmm_high_emission if undercut else 1 - config.hmm_high_emission
            denominator = predicted * low_like + (1 - predicted) * high_like
            regime_belief[provider] = predicted * low_like / max(denominator, 1e-12)

    _add_placebos(panel, config=config)
    return panel


def _add_placebos(panel: list[dict[str, Any]], *, config: MemoryConfig) -> None:
    if not panel:
        return
    unique: dict[tuple[str, str], tuple[pd.Timestamp, float]] = {}
    for row in panel:
        current = row["features"]["current_price_ratio"]
        for provider, value in zip(row["providers"], current, strict=True):
            unique[(row["block_id"], provider)] = (row["observed_at"], float(value))
    by_provider: dict[str, list[tuple[pd.Timestamp, str, float]]] = defaultdict(list)
    for (block_id, provider), (timestamp, value) in unique.items():
        by_provider[provider].append((timestamp, block_id, value))
    future: dict[tuple[str, str], float] = {}
    shifted: dict[tuple[str, str], float] = {}
    source_name = "price_h48" if 48 in config.lag_blocks else f"price_h{config.lag_blocks[0]}"
    source: dict[tuple[str, str], float] = {}
    for row in panel:
        for provider, value in zip(row["providers"], row["features"][source_name], strict=True):
            source[(row["block_id"], provider)] = float(value)
    for provider, values in by_provider.items():
        values.sort()
        for index, (_, block_id, _) in enumerate(values):
            future[(block_id, provider)] = values[index + 1][2] if index + 1 < len(values) else 0.0
        history = [source.get((block_id, provider), 0.0) for _, block_id, _ in values]
        offset = max(1, len(history) // 2)
        rotated = history[offset:] + history[:offset]
        for (_, block_id, _), value in zip(values, rotated, strict=True):
            shifted[(block_id, provider)] = value
    for row in panel:
        row["features"]["future_price_lead"] = np.asarray(
            [future.get((row["block_id"], provider), 0.0) for provider in row["providers"]]
        )
        row["features"]["circular_price_placebo"] = np.asarray(
            [shifted.get((row["block_id"], provider), 0.0) for provider in row["providers"]]
        )


def model_specs(config: MemoryConfig = DEFAULT_CONFIG) -> dict[str, tuple[str, ...]]:
    specs: dict[str, tuple[str, ...]] = {"no_memory": ()}
    for h in config.lag_blocks:
        specs[f"geometric_price_h{h}"] = (f"price_h{h}",)
        specs[f"geometric_quality_h{h}"] = (
            f"success_h{h}",
            f"latency_h{h}",
            f"fidelity_h{h}",
            f"seen_h{h}",
        )
        specs[f"geometric_joint_h{h}"] = (f"price_h{h}",) + specs[f"geometric_quality_h{h}"]
    for run in config.finite_runs:
        specs[f"finite_run_m{run}"] = (f"run_ge_{run}",)
    specs["regime_memory"] = ("regime_low_prob",)
    specs["placebo_future_price"] = ("future_price_lead",)
    specs["placebo_circular_price"] = ("circular_price_placebo",)
    return specs


def _fit(
    rows: Sequence[Mapping[str, Any]],
    feature_names: Sequence[str],
    *,
    config: MemoryConfig,
) -> tuple[dict[str, float], np.ndarray, bool]:
    providers = sorted({provider for row in rows for provider in row["providers"]})
    locations = {provider: index for index, provider in enumerate(providers)}
    dimension = len(providers) + len(feature_names)

    def objective(parameters: np.ndarray) -> tuple[float, np.ndarray]:
        alpha = parameters[: len(providers)]
        beta = parameters[len(providers) :]
        value = 0.5 * config.ridge * float(parameters @ parameters)
        gradient = config.ridge * parameters.copy()
        for row in rows:
            indices = np.asarray([locations[p] for p in row["providers"]], dtype=int)
            matrix = (
                np.column_stack([row["features"][name] for name in feature_names])
                if feature_names
                else np.empty((len(indices), 0))
            )
            logits = -config.eta * np.log(row["costs"]) + alpha[indices]
            if feature_names:
                logits = logits + matrix @ beta
            probabilities = np.exp(logits - logsumexp(logits))
            selected = int(row["selected_index"])
            value += float(logsumexp(logits) - logits[selected])
            np.add.at(gradient, indices, probabilities)
            gradient[indices[selected]] -= 1.0
            if feature_names:
                gradient[len(providers) :] += matrix.T @ probabilities - matrix[selected]
        return value, gradient

    result = minimize(
        objective,
        np.zeros(dimension),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": 1000, "ftol": 1e-11, "gtol": 1e-7},
    )
    alpha = np.asarray(result.x[: len(providers)], dtype=float)
    alpha -= float(alpha.mean()) if len(alpha) else 0.0
    return (
        dict(zip(providers, alpha, strict=True)),
        np.asarray(result.x[len(providers) :]),
        bool(result.success),
    )


def _loss(
    row: Mapping[str, Any],
    alpha: Mapping[str, float],
    beta: np.ndarray,
    feature_names: Sequence[str],
    *,
    eta: float,
) -> float:
    logits = -eta * np.log(row["costs"]) + np.asarray(
        [alpha.get(provider, 0.0) for provider in row["providers"]]
    )
    if feature_names:
        matrix = np.column_stack([row["features"][name] for name in feature_names])
        logits = logits + matrix @ beta
    selected = int(row["selected_index"])
    return float(logsumexp(logits) - logits[selected])


def _splits(panel: Sequence[Mapping[str, Any]]) -> list[tuple[set[str], set[str]]]:
    blocks: dict[str, pd.Timestamp] = {}
    for row in panel:
        blocks[str(row["block_id"])] = row["observed_at"]
    ordered = [block for block, _ in sorted(blocks.items(), key=lambda item: item[1])]
    if len(ordered) < 30:
        return []
    boundaries = sorted({max(20, int(len(ordered) * fraction)) for fraction in (0.60, 0.70, 0.80)})
    output = []
    for index, boundary in enumerate(boundaries):
        end = boundaries[index + 1] if index + 1 < len(boundaries) else len(ordered)
        if end - boundary >= 5:
            output.append((set(ordered[:boundary]), set(ordered[boundary:end])))
    return output


def compare_models(
    panel: Sequence[Mapping[str, Any]],
    *,
    config: MemoryConfig = DEFAULT_CONFIG,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare frozen model classes on whole-block future folds."""

    splits = _splits(panel)
    specs = model_specs(config)
    records = []
    if not splits:
        return pd.DataFrame(), pd.DataFrame()
    for fold, (train_blocks, test_blocks) in enumerate(splits):
        train = [row for row in panel if row["block_id"] in train_blocks]
        test = [row for row in panel if row["block_id"] in test_blocks]
        for model, features in specs.items():
            alpha, beta, success = _fit(train, features, config=config)
            if not success:
                continue
            for row in test:
                records.append(
                    {
                        "fold": fold,
                        "model": model,
                        "block_id": row["block_id"],
                        "task_id": str(row.get("task_id") or ""),
                        "date": row["date"],
                        "loss": _loss(row, alpha, beta, features, eta=config.eta),
                        "features": ",".join(features),
                    }
                )
    losses = pd.DataFrame(records)
    if losses.empty:
        return pd.DataFrame(), losses
    expected_choices = sum(
        sum(row["block_id"] in test_blocks for row in panel)
        for _, test_blocks in splits
    )
    complete_models = set(
        losses.groupby("model").size().loc[lambda values: values == expected_choices].index
    )
    losses = losses[losses["model"].isin(complete_models)].copy()
    if "no_memory" not in complete_models:
        return pd.DataFrame(), pd.DataFrame()
    baseline = losses[losses["model"] == "no_memory"][
        ["fold", "block_id", "task_id", "loss"]
    ].rename(columns={"loss": "baseline_loss"})
    losses = losses.merge(
        baseline,
        on=["fold", "block_id", "task_id"],
        how="inner",
        validate="many_to_one",
    )
    losses["gain_bits"] = (losses["baseline_loss"] - losses["loss"]) / math.log(2)
    summary = (
        losses.groupby(["model", "features"], as_index=False)
        .agg(
            choices=("loss", "size"),
            folds=("fold", "nunique"),
            log_loss=("loss", "mean"),
            baseline_log_loss=("baseline_loss", "mean"),
            gain_bits_per_choice=("gain_bits", "mean"),
        )
        .sort_values(["log_loss", "model"])
    )
    intervals = []
    rng = np.random.default_rng(20260722)
    for model, group in losses.groupby("model", sort=True):
        by_day = group.groupby("date")["gain_bits"].mean().to_numpy(dtype=float)
        if len(by_day) < 2:
            intervals.append((model, np.nan, np.nan))
            continue
        draws = by_day[rng.integers(0, len(by_day), size=(2000, len(by_day)))].mean(axis=1)
        low, high = np.quantile(draws, [0.025, 0.975])
        intervals.append((model, float(low), float(high)))
    interval_frame = pd.DataFrame(
        intervals, columns=["model", "gain_bits_ci_low", "gain_bits_ci_high"]
    )
    return summary.merge(interval_frame, on="model", how="left"), losses


def support_summary(
    panel: Sequence[Mapping[str, Any]],
    quality_events: Sequence[Mapping[str, Any]],
    model_table: pd.DataFrame,
    *,
    minimum_choices: int = 800,
    minimum_blocks: int = 100,
    minimum_days: float = 28.0,
    minimum_providers: int = 3,
) -> dict[str, Any]:
    blocks = {row["block_id"] for row in panel}
    providers = {row["providers"][int(row["selected_index"])] for row in panel if row["providers"]}
    timestamps = [row["observed_at"] for row in panel]
    days = (
        float((max(timestamps) - min(timestamps)).total_seconds() / 86400)
        if len(timestamps) >= 2
        else 0.0
    )
    price_events = 0
    prior: dict[str, float] = {}
    seen_blocks: set[str] = set()
    for row in sorted(panel, key=lambda item: (item["observed_at"], item["block_id"])):
        if row["block_id"] in seen_blocks:
            continue
        seen_blocks.add(row["block_id"])
        for provider, cost in zip(row["providers"], row["costs"], strict=True):
            if provider in prior and not math.isclose(float(cost), prior[provider], rel_tol=1e-9):
                price_events += 1
            prior[provider] = float(cost)
    failures = []
    for failed, name in (
        (len(panel) < minimum_choices, "choices"),
        (len(blocks) < minimum_blocks, "blocks"),
        (days < minimum_days, "duration"),
        (len(providers) < minimum_providers, "selected_providers"),
        (price_events < 30, "price_events"),
        (len(quality_events) < 30, "quality_events"),
    ):
        if failed:
            failures.append(name)
    primary = pd.DataFrame()
    if not model_table.empty:
        primary = model_table[
            ~model_table["model"].str.startswith("placebo") & model_table["model"].ne("no_memory")
        ]
    best = primary.iloc[0].to_dict() if not primary.empty else None
    return {
        "support_status": "ready" if not failures else "accruing",
        "support_failures": failures,
        "covered_choices": len(panel),
        "blocks": len(blocks),
        "duration_days": days,
        "selected_providers": len(providers),
        "price_events": price_events,
        "quality_events": len(quality_events),
        "future_folds_ready": not model_table.empty,
        "best_dynamic_model": best,
        "claim_boundary": (
            "Dynamic estimates are predictive owned-choice contrasts until a randomized "
            "owned-router or partner-log transition test passes; they do not identify "
            "market-wide share or a proprietary router state."
        ),
    }
