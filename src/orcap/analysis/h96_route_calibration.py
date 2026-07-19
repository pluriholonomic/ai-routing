"""H96 calibration of public shadow routing against owned OpenRouter choices.

The primary sample is the independent, budget-bounded default arm.  The model
fits only a global inverse-price exponent and evaluates chronologically when
multiple capture runs are available.  Provider fixed effects are intentionally
deferred until the panel has adequate provider-level support.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp

from ..capture_route_calibration import STUDY_ID
from . import data

DEFAULT_OUT = Path("analysis/h96-route-calibration")
MIN_FIT_OBSERVATIONS = 20


def _metadata(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    rows: list[dict[str, Any]] = []
    for value in frame.get("metadata_json", pd.Series(index=frame.index, dtype=object)):
        try:
            item = json.loads(value or "{}")
        except (TypeError, json.JSONDecodeError):
            item = {}
        rows.append(item if isinstance(item, dict) else {})
    metadata = pd.DataFrame(rows, index=frame.index)
    return pd.concat([frame.reset_index(drop=True), metadata.reset_index(drop=True)], axis=1)


def _provider(value: Any) -> str:
    return str(value or "").strip().casefold()


def _candidate_menus(candidates: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if candidates.empty:
        return {}
    c = candidates.copy()
    c = c[c["compatible"].fillna(False)].copy()
    c["provider_key"] = c["provider_name"].map(_provider)
    c["expected_quote_usd"] = pd.to_numeric(c["expected_quote_usd"], errors="coerce")
    if "price_index_per_token" in c:
        c["price_index_per_token"] = pd.to_numeric(
            c["price_index_per_token"], errors="coerce"
        )
    else:
        c["price_index_per_token"] = np.nan
    if {"prompt_price_per_token", "completion_price_per_token"}.issubset(c.columns):
        fallback_index = (
            pd.to_numeric(c["prompt_price_per_token"], errors="coerce")
            + pd.to_numeric(c["completion_price_per_token"], errors="coerce")
        ) / 2.0
        c["price_index_per_token"] = c["price_index_per_token"].fillna(fallback_index)
    c = c[
        (c["provider_key"] != "")
        & (c["expected_quote_usd"] > 0)
        & (c["price_index_per_token"] > 0)
    ]
    c = c.sort_values(["block_id", "expected_quote_usd", "provider_key"])
    c = c.drop_duplicates(["block_id", "provider_key"], keep="first")
    return {
        str(block_id): group[
            [
                "provider_name",
                "provider_key",
                "expected_quote_usd",
                "price_index_per_token",
            ]
        ].to_dict("records")
        for block_id, group in c.groupby("block_id", sort=False)
    }


def prepare_observations(
    candidates: pd.DataFrame,
    assignments: pd.DataFrame,
    attempts: pd.DataFrame,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    menus = _candidate_menus(candidates)
    if assignments.empty or attempts.empty:
        return [], pd.DataFrame()
    a = assignments.copy()
    t = _metadata(attempts)
    needed = [
        "task_id",
        "selected_provider",
        "outcome",
        "cost_usd",
        "latency_ms",
        "input_tokens",
        "output_tokens",
    ]
    for column in needed:
        if column not in t:
            t[column] = None
    t = t[needed].drop_duplicates("task_id", keep="last")
    joined = a.merge(t, on="task_id", how="left", validate="one_to_one")
    joined["selected_provider_key"] = joined["selected_provider"].map(_provider)
    observations: list[dict[str, Any]] = []
    primary = joined[
        (joined["policy"] == "default_budgeted_iid")
        & (joined["outcome"] == "succeeded")
        & (joined["selected_provider_key"] != "")
    ]
    for row in primary.to_dict("records"):
        menu = menus.get(str(row["block_id"]), [])
        costs = np.array([float(item["expected_quote_usd"]) for item in menu], dtype=float)
        price_index_costs = np.array(
            [float(item["price_index_per_token"]) for item in menu], dtype=float
        )
        providers = [str(item["provider_key"]) for item in menu]
        selected = str(row["selected_provider_key"])
        observations.append(
            {
                "task_id": row["task_id"],
                "run_id": row["run_id"],
                "block_id": row["block_id"],
                "model_id": row["model_id"],
                "shape_id": row["shape_id"],
                "selected_provider": row["selected_provider"],
                "selected_key": selected,
                "providers": providers,
                "costs": costs,
                "price_index_costs": price_index_costs,
                "selected_index": providers.index(selected) if selected in providers else None,
            }
        )
    return observations, joined


def _probabilities(costs: np.ndarray, eta: float) -> np.ndarray:
    logits = -float(eta) * np.log(costs)
    return np.exp(logits - logsumexp(logits))


def _nll(eta: float, observations: list[dict[str, Any]]) -> float:
    total = 0.0
    for observation in observations:
        selected_index = observation["selected_index"]
        if selected_index is None:
            continue
        probabilities = _probabilities(observation["costs"], eta)
        total -= float(np.log(max(probabilities[selected_index], 1e-15)))
    return total


def fit_eta(observations: list[dict[str, Any]]) -> dict[str, Any]:
    covered = [item for item in observations if item["selected_index"] is not None]
    if len(covered) < MIN_FIT_OBSERVATIONS:
        return {
            "fit_ready": False,
            "n_fit": len(covered),
            "eta_hat": None,
            "eta_profile_ci_low": None,
            "eta_profile_ci_high": None,
        }
    result = minimize_scalar(
        lambda eta: _nll(float(eta), covered),
        bounds=(0.0, 8.0),
        method="bounded",
        options={"xatol": 1e-6},
    )
    eta_hat = float(result.x)
    minimum = float(result.fun)
    grid = np.linspace(0.0, 8.0, 1_601)
    accepted = grid[np.array([_nll(float(eta), covered) for eta in grid]) <= minimum + 1.9207]
    return {
        "fit_ready": bool(result.success),
        "n_fit": len(covered),
        "eta_hat": eta_hat,
        "eta_profile_ci_low": float(accepted.min()) if len(accepted) else None,
        "eta_profile_ci_high": float(accepted.max()) if len(accepted) else None,
    }


def _chronological_split(observations: list[dict[str, Any]]) -> tuple[list, list, str]:
    runs = sorted({str(item["run_id"]) for item in observations})
    if len(runs) < 4:
        return observations, observations, "in_sample_until_four_runs"
    split = max(1, int(np.floor(0.7 * len(runs))))
    train_runs = set(runs[:split])
    return (
        [item for item in observations if str(item["run_id"]) in train_runs],
        [item for item in observations if str(item["run_id"]) not in train_runs],
        "chronological_70_30_by_run",
    )


def score_observations(
    observations: list[dict[str, Any]],
    eta: float,
    *,
    split_name: str,
    cost_key: str = "costs",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for observation in observations:
        costs = observation[cost_key]
        selected_index = observation["selected_index"]
        probabilities = _probabilities(costs, eta)
        covered = selected_index is not None
        selected_probability = float(probabilities[selected_index]) if covered else None
        selected_quote = float(costs[selected_index]) if covered else None
        cheapest_index = int(np.argmin(costs)) if len(costs) else None
        brier = None
        if covered:
            target = np.zeros(len(probabilities))
            target[selected_index] = 1.0
            brier = float(np.square(probabilities - target).sum())
        rows.append(
            {
                "task_id": observation["task_id"],
                "run_id": observation["run_id"],
                "block_id": observation["block_id"],
                "model_id": observation["model_id"],
                "shape_id": observation["shape_id"],
                "selected_provider": observation["selected_provider"],
                "selected_in_public_menu": covered,
                "candidate_provider_count": len(observation["providers"]),
                "eta": eta,
                "cost_definition": cost_key,
                "selected_probability": selected_probability,
                "negative_log_likelihood": (
                    -np.log(max(selected_probability, 1e-15)) if covered else None
                ),
                "brier_score": brier,
                "predicted_provider": (
                    observation["providers"][int(np.argmax(probabilities))]
                    if len(probabilities)
                    else None
                ),
                "top_one_correct": bool(
                    covered and int(np.argmax(probabilities)) == selected_index
                ),
                "selected_quote_usd": selected_quote,
                "cheapest_quote_usd": (
                    float(costs[cheapest_index]) if cheapest_index is not None else None
                ),
                "cost_regret_usd": (
                    selected_quote - float(costs[cheapest_index])
                    if covered and cheapest_index is not None
                    else None
                ),
                "split": split_name,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame, {
            "observations": 0,
            "candidate_coverage_rate": None,
            "mean_log_loss": None,
            "mean_brier_score": None,
            "top_one_accuracy": None,
            "mean_cost_regret_usd": None,
        }
    covered = frame[frame["selected_in_public_menu"]]  # noqa: E712
    metrics = {
        "observations": len(frame),
        "candidate_coverage_rate": (
            float(frame["selected_in_public_menu"].mean()) if len(frame) else None
        ),
        "mean_log_loss": (
            float(covered["negative_log_likelihood"].mean()) if len(covered) else None
        ),
        "mean_brier_score": (
            float(covered["brier_score"].mean()) if len(covered) else None
        ),
        "top_one_accuracy": (
            float(covered["top_one_correct"].mean()) if len(covered) else None
        ),
        "mean_cost_regret_usd": (
            float(covered["cost_regret_usd"].mean()) if len(covered) else None
        ),
    }
    return frame, metrics


def policy_audit(joined: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    if joined.empty:
        return pd.DataFrame()
    menus = _candidate_menus(candidates)
    rows: list[dict[str, Any]] = []
    for row in joined.to_dict("records"):
        policy = str(row.get("policy") or "")
        if policy.startswith("pinned_"):
            match = _provider(row.get("requested_provider")) == _provider(
                row.get("selected_provider")
            )
            rows.append(
                {
                    "audit": "pinned_provider_match",
                    "task_id": row.get("task_id"),
                    "block_id": row.get("block_id"),
                    "policy": policy,
                    "success": bool(row.get("outcome") == "succeeded" and match),
                }
            )
        elif policy == "sort_price":
            menu = menus.get(str(row.get("block_id")), [])
            cheapest = (
                min(menu, key=lambda item: float(item["price_index_per_token"]))[
                    "provider_key"
                ]
                if menu
                else ""
            )
            rows.append(
                {
                    "audit": "sort_price_cheapest_match",
                    "task_id": row.get("task_id"),
                    "block_id": row.get("block_id"),
                    "policy": policy,
                    "success": bool(
                        row.get("outcome") == "succeeded"
                        and _provider(row.get("selected_provider")) == cheapest
                    ),
                }
            )
    sticky = joined[joined["policy"].isin(["default_sticky_seed", "default_sticky_repeat"])]
    for pair_id, group in sticky.groupby("sticky_pair_id", dropna=True):
        by_policy = {str(row["policy"]): row for row in group.to_dict("records")}
        if {"default_sticky_seed", "default_sticky_repeat"}.issubset(by_policy):
            seed = by_policy["default_sticky_seed"]
            repeat = by_policy["default_sticky_repeat"]
            rows.append(
                {
                    "audit": "sticky_provider_repeat",
                    "task_id": None,
                    "block_id": seed.get("block_id"),
                    "policy": "sticky_pair",
                    "success": bool(
                        seed.get("outcome") == "succeeded"
                        and repeat.get("outcome") == "succeeded"
                        and _provider(seed.get("selected_provider"))
                        == _provider(repeat.get("selected_provider"))
                    ),
                    "sticky_pair_id": pair_id,
                }
            )
    return pd.DataFrame(rows)


def analyze_frames(
    candidates: pd.DataFrame,
    assignments: pd.DataFrame,
    attempts: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    observations, joined = prepare_observations(candidates, assignments, attempts)
    train, test, split_rule = _chronological_split(observations)
    fit = fit_eta(train)
    eta = float(fit["eta_hat"]) if fit["fit_ready"] else 2.0
    scores, score_summary = score_observations(test, eta, split_name=split_rule)
    _, eta2_shape_summary = score_observations(test, 2.0, split_name=split_rule)
    _, eta2_price_index_summary = score_observations(
        test, 2.0, split_name=split_rule, cost_key="price_index_costs"
    )
    audit = policy_audit(joined, candidates)
    audit_summary = (
        audit.groupby("audit")["success"].agg(["count", "mean"]).to_dict("index")
        if not audit.empty
        else {}
    )
    summary = {
        "study_id": STUDY_ID,
        "assignment_rows": len(assignments),
        "attempt_rows": len(attempts),
        "independent_default_observations": len(observations),
        "split_rule": split_rule,
        "fit": fit,
        "evaluation_at_eta_hat_or_two": score_summary,
        "evaluation_at_eta_two_shape_adjusted_quote": eta2_shape_summary,
        "evaluation_at_eta_two_public_price_index": eta2_price_index_summary,
        "policy_audit": audit_summary,
        "claim_boundary": (
            "Choice calibration for owned, budget-bounded probes. Provider-name outcomes do "
            "not identify exact endpoint variants or market-wide routed flow."
        ),
    }
    return scores, audit, summary


def _load(table: str) -> pd.DataFrame:
    try:
        return data.q(
            f"select * from read_parquet('{data.table_glob(table)}', union_by_name=true)"
        ).df()
    except Exception:
        return pd.DataFrame()


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    candidates = _load("router_calibration_candidates")
    assignments = _load("router_calibration_assignments")
    attempts = _load("router_route_attempts")
    if not attempts.empty and "study_id" in attempts:
        attempts = attempts[attempts["study_id"] == STUDY_ID]
    if not assignments.empty and "study_id" in assignments:
        assignments = assignments[assignments["study_id"] == STUDY_ID]
    if not candidates.empty and "study_id" in candidates:
        candidates = candidates[candidates["study_id"] == STUDY_ID]
    scores, audit, summary = analyze_frames(candidates, assignments, attempts)
    out_dir.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(out_dir / "h96_choice_scores.parquet", index=False)
    audit.to_parquet(out_dir / "h96_policy_audit.parquet", index=False)
    (out_dir / "h96_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
