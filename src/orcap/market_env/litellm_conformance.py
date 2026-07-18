"""Executable conformance checks against LiteLLM's real router selection code.

The adapter deliberately calls :class:`litellm.Router` deployment-selection
methods without issuing inference requests.  It validates only mechanisms that
LiteLLM exposes directly:

* weighted ``simple-shuffle`` after mapping our inverse-price score to the
  deployment ``weight`` field;
* ``cost-based-routing`` after mapping the scalar quote equally to input and
  output token prices;
* blocked-deployment filtering and sequential exclusion for fallback order.

It does not claim that LiteLLM or OpenRouter natively implements our
inverse-price score, nor that either router's hidden production state is
recovered by these fixtures.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import inspect
import itertools
import json
import random
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

from .routers import InversePriceRouter, LowestCostRouter, RouterMechanism
from .types import Availability, ProviderAction, ProviderSpec


@dataclass(frozen=True)
class ConformanceFixture:
    """One fixed provider snapshot supplied to both router implementations."""

    name: str
    specs: tuple[ProviderSpec, ...]
    actions: Mapping[str, ProviderAction]
    exponent: float = 2.0


def _spec(
    provider: str,
    *,
    physical_capacity: int = 100,
    reliability: float = 1.0,
) -> ProviderSpec:
    return ProviderSpec(
        provider=provider,
        marginal_cost=0.2,
        physical_capacity=physical_capacity,
        reliability=reliability,
    )


def frozen_fixtures() -> tuple[ConformanceFixture, ...]:
    """Return the prespecified stochastic conformance fixtures."""
    fixtures = (
        ConformanceFixture(
            name="balanced_three",
            specs=tuple(_spec(provider) for provider in ("a", "b", "c")),
            actions={provider: ProviderAction(quote=1.0) for provider in ("a", "b", "c")},
        ),
        ConformanceFixture(
            name="moderate_price_spread",
            specs=tuple(_spec(provider) for provider in ("a", "b", "c")),
            actions={
                "a": ProviderAction(quote=1.0),
                "b": ProviderAction(quote=1.4),
                "c": ProviderAction(quote=2.2),
            },
        ),
        ConformanceFixture(
            name="four_provider_spread",
            specs=tuple(_spec(provider) for provider in ("a", "b", "c", "d")),
            actions={
                "a": ProviderAction(quote=1.0),
                "b": ProviderAction(quote=1.2),
                "c": ProviderAction(quote=1.8),
                "d": ProviderAction(quote=2.6),
            },
        ),
        ConformanceFixture(
            name="withdrawn_and_zero_capacity",
            specs=(_spec("a"), _spec("b"), _spec("c"), _spec("d", physical_capacity=0)),
            actions={
                "a": ProviderAction(quote=1.0),
                "b": ProviderAction(quote=1.5),
                "c": ProviderAction(quote=0.8, availability=Availability.WITHDRAWN),
                "d": ProviderAction(quote=0.7),
            },
        ),
        ConformanceFixture(
            name="degraded_remains_eligible",
            specs=tuple(_spec(provider) for provider in ("a", "b", "c")),
            actions={
                "a": ProviderAction(quote=1.0),
                "b": ProviderAction(quote=1.3, availability=Availability.DEGRADED),
                "c": ProviderAction(quote=1.7, admitted_capacity_fraction=0.0),
            },
        ),
    )
    for fixture in fixtures:
        if set(fixture.actions) != {spec.provider for spec in fixture.specs}:
            raise AssertionError(f"invalid fixture provider set: {fixture.name}")
    return fixtures


def _spec_map(fixture: ConformanceFixture) -> dict[str, ProviderSpec]:
    return {spec.provider: spec for spec in fixture.specs}


def _exclusion_reason(
    spec: ProviderSpec,
    action: ProviderAction,
) -> str | None:
    if action.availability == Availability.WITHDRAWN:
        return "withdrawn"
    if action.admitted_capacity_fraction <= 0:
        return "zero_admitted_capacity"
    if spec.physical_capacity <= 0:
        return "zero_physical_capacity"
    return None


def _model_id(fixture: str, provider: str) -> str:
    return f"orcap-{fixture}-{provider}"


def _provider_from_model_id(model_id: str) -> str:
    return model_id.rsplit("-", 1)[-1]


def _model_list(
    fixture: ConformanceFixture,
    mechanism: RouterMechanism,
    *,
    strategy: str,
) -> list[dict[str, Any]]:
    specs = _spec_map(fixture)
    if strategy == "simple-shuffle":
        probabilities = mechanism.probabilities(specs, fixture.actions)
    else:
        probabilities = {}
    model_list: list[dict[str, Any]] = []
    for provider in sorted(specs):
        action = fixture.actions[provider]
        blocked = _exclusion_reason(specs[provider], action) is not None
        params: dict[str, Any] = {
            "model": "openai/gpt-4o-mini",
            "api_key": "synthetic-conformance-key",
            "input_cost_per_token": action.quote / 2,
            "output_cost_per_token": action.quote / 2,
            "cache_creation_input_token_cost": 0.0,
            "cache_read_input_token_cost": 0.0,
        }
        if strategy == "simple-shuffle":
            params["weight"] = probabilities.get(provider, 0.0)
        model_list.append(
            {
                "model_name": fixture.name,
                "litellm_params": params,
                "model_info": {
                    "id": _model_id(fixture.name, provider),
                    "blocked": blocked,
                },
            }
        )
    return model_list


def _litellm_router(fixture: ConformanceFixture, *, strategy: str) -> Any:
    try:
        from litellm import Router
    except ImportError as exc:  # pragma: no cover - exercised only without optional extra
        raise RuntimeError(
            "LiteLLM conformance requires `uv sync --extra router-conformance`"
        ) from exc
    mechanism: RouterMechanism
    if strategy == "simple-shuffle":
        mechanism = InversePriceRouter(fixture.exponent)
    elif strategy == "cost-based-routing":
        mechanism = LowestCostRouter()
    else:  # pragma: no cover - internal caller freezes the allowed set
        raise ValueError(f"unsupported LiteLLM conformance strategy: {strategy}")
    return Router(
        model_list=_model_list(fixture, mechanism, strategy=strategy),
        routing_strategy=strategy,
        disable_cooldowns=True,
        cache_responses=False,
    )


def _family_interval(count: int, trials: int, *, family_cells: int) -> tuple[float, float]:
    """Bonferroni-exact interval simultaneous over the complete stochastic family."""
    alpha = 0.05 / family_cells
    low, high = proportion_confint(count, trials, alpha=alpha, method="beta")
    return float(low), float(high)


def _expected_permutation_probabilities(weights: Mapping[str, float]) -> dict[str, float]:
    result: dict[str, float] = {}
    for permutation in itertools.permutations(sorted(weights)):
        remaining = dict(weights)
        probability = 1.0
        for provider in permutation:
            probability *= remaining[provider] / sum(remaining.values())
            del remaining[provider]
        result[">".join(permutation)] = probability
    return result


def _selection_counts(
    router: Any,
    fixture: ConformanceFixture,
    *,
    trials: int,
    seed: int,
) -> Counter[str]:
    random.seed(seed)
    counts: Counter[str] = Counter()
    for _ in range(trials):
        deployment = router.get_available_deployment(model=fixture.name, request_kwargs={})
        counts[_provider_from_model_id(deployment["model_info"]["id"])] += 1
    return counts


def _fallback_counts(
    router: Any,
    fixture: ConformanceFixture,
    *,
    trials: int,
    seed: int,
) -> Counter[str]:
    random.seed(seed)
    mechanism = InversePriceRouter(fixture.exponent)
    expected = mechanism.probabilities(_spec_map(fixture), fixture.actions)
    counts: Counter[str] = Counter()
    for _ in range(trials):
        excluded: list[str] = []
        order: list[str] = []
        for _position in range(len(expected)):
            deployment = router.get_available_deployment(
                model=fixture.name,
                request_kwargs={"_excluded_deployment_ids": tuple(excluded)},
            )
            model_id = deployment["model_info"]["id"]
            excluded.append(model_id)
            order.append(_provider_from_model_id(model_id))
        counts[">".join(order)] += 1
    return counts


async def _cost_choices(fixtures: Sequence[ConformanceFixture]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        router = _litellm_router(fixture, strategy="cost-based-routing")
        expected_probabilities = LowestCostRouter().probabilities(
            _spec_map(fixture), fixture.actions
        )
        expected = next(
            provider for provider, probability in expected_probabilities.items() if probability
        )
        deployment = await router.async_get_available_deployment(
            model=fixture.name,
            request_kwargs={},
            input="synthetic conformance request",
        )
        observed = _provider_from_model_id(deployment["model_info"]["id"])
        rows.append(
            {
                "diagnostic": "deterministic_lowest_cost",
                "fixture": fixture.name,
                "category": expected,
                "expected": 1.0,
                "observed": float(observed == expected),
                "ci_low": 1.0,
                "ci_high": 1.0,
                "absolute_error": float(observed != expected),
                "interval_contains_expected": observed == expected,
                "absolute_error_le_2pp": observed == expected,
                "passed": observed == expected,
                "trials": 1,
                "observed_choice": observed,
            }
        )
    return rows


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def run_conformance(
    *,
    trials_per_state: int = 10_000,
    fallback_trials: int = 10_000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Execute the frozen LiteLLM conformance suite and return rows plus summary."""
    if trials_per_state < 10_000 or fallback_trials < 10_000:
        raise ValueError("the frozen conformance gate requires at least 10,000 trials per state")
    fixtures = frozen_fixtures()
    fallback_fixture = next(
        fixture for fixture in fixtures if fixture.name == "moderate_price_spread"
    )
    stochastic_cells = sum(
        len(InversePriceRouter(fixture.exponent).probabilities(_spec_map(fixture), fixture.actions))
        for fixture in fixtures
    )
    fallback_probabilities = _expected_permutation_probabilities(
        InversePriceRouter(fallback_fixture.exponent).probabilities(
            _spec_map(fallback_fixture), fallback_fixture.actions
        )
    )
    family_cells = stochastic_cells + len(fallback_probabilities)
    rows: list[dict[str, Any]] = []

    for fixture_index, fixture in enumerate(fixtures):
        mechanism = InversePriceRouter(fixture.exponent)
        expected = mechanism.probabilities(_spec_map(fixture), fixture.actions)
        router = _litellm_router(fixture, strategy="simple-shuffle")
        counts = _selection_counts(
            router,
            fixture,
            trials=trials_per_state,
            seed=81_000 + fixture_index,
        )
        observed_candidates = {provider for provider, count in counts.items() if count > 0}
        eligibility_exact = observed_candidates == set(expected)
        for provider, probability in expected.items():
            count = counts[provider]
            observed = count / trials_per_state
            low, high = _family_interval(count, trials_per_state, family_cells=family_cells)
            error = abs(observed - probability)
            interval_pass = low <= probability <= high
            error_pass = error <= 0.02
            rows.append(
                {
                    "diagnostic": "first_route_share",
                    "fixture": fixture.name,
                    "category": provider,
                    "expected": probability,
                    "observed": observed,
                    "ci_low": low,
                    "ci_high": high,
                    "absolute_error": error,
                    "interval_contains_expected": interval_pass,
                    "absolute_error_le_2pp": error_pass,
                    "passed": interval_pass and error_pass and eligibility_exact,
                    "trials": trials_per_state,
                    "eligibility_exact": eligibility_exact,
                }
            )

    fallback_router = _litellm_router(fallback_fixture, strategy="simple-shuffle")
    fallback_counts = _fallback_counts(
        fallback_router,
        fallback_fixture,
        trials=fallback_trials,
        seed=82_000,
    )
    fallback_support_exact = set(fallback_counts) == set(fallback_probabilities)
    for order, probability in fallback_probabilities.items():
        count = fallback_counts[order]
        observed = count / fallback_trials
        low, high = _family_interval(count, fallback_trials, family_cells=family_cells)
        error = abs(observed - probability)
        interval_pass = low <= probability <= high
        error_pass = error <= 0.02
        rows.append(
            {
                "diagnostic": "fallback_permutation",
                "fixture": fallback_fixture.name,
                "category": order,
                "expected": probability,
                "observed": observed,
                "ci_low": low,
                "ci_high": high,
                "absolute_error": error,
                "interval_contains_expected": interval_pass,
                "absolute_error_le_2pp": error_pass,
                "passed": interval_pass and error_pass and fallback_support_exact,
                "trials": fallback_trials,
                "eligibility_exact": fallback_support_exact,
            }
        )

    rows.extend(asyncio.run(_cost_choices(fixtures)))
    frame = pd.DataFrame(rows)

    from litellm.router_strategy.lowest_cost import LowestCostLoggingHandler
    from litellm.router_strategy.simple_shuffle import simple_shuffle

    stochastic = frame[frame["diagnostic"] != "deterministic_lowest_cost"]
    exclusions = []
    for fixture in fixtures:
        for spec in fixture.specs:
            reason = _exclusion_reason(spec, fixture.actions[spec.provider])
            if reason is not None:
                exclusions.append(
                    {
                        "fixture": fixture.name,
                        "provider": spec.provider,
                        "adapter_reason": reason,
                        "litellm_representation": "model_info.blocked=true",
                    }
                )
    summary = {
        "experiment": "SM4 LiteLLM executable-router conformance",
        "source_commit": _git_commit(),
        "litellm_version": importlib.metadata.version("litellm"),
        "litellm_simple_shuffle_source_sha256": _sha256_text(inspect.getsource(simple_shuffle)),
        "litellm_cost_selector_source_sha256": _sha256_text(
            inspect.getsource(LowestCostLoggingHandler.async_get_available_deployments)
        ),
        "trials_per_stochastic_state": trials_per_state,
        "fallback_trials": fallback_trials,
        "stochastic_family_cells": family_cells,
        "interval_method": (
            "Clopper-Pearson intervals with Bonferroni alpha=0.05/family_cells; "
            "simultaneous over every first-route share and fallback permutation cell"
        ),
        "absolute_error_gate": 0.02,
        "n_stochastic_fixtures": len(fixtures),
        "n_stochastic_rows": int(len(stochastic)),
        "n_deterministic_rows": int(
            (frame["diagnostic"] == "deterministic_lowest_cost").sum()
        ),
        "all_rows_pass": bool(frame["passed"].all()),
        "all_interval_gates_pass": bool(stochastic["interval_contains_expected"].all()),
        "all_absolute_error_gates_pass": bool(stochastic["absolute_error_le_2pp"].all()),
        "max_absolute_error": float(stochastic["absolute_error"].max()),
        "excluded_provider_mappings": exclusions,
        "claim_boundary": (
            "This validates LiteLLM 1.92.0 deployment filtering, weighted selection, "
            "sequential exclusion, and scalar lowest-cost selection on synthetic fixtures. "
            "Inverse-price scores are explicitly mapped into LiteLLM weights; this is not "
            "evidence that LiteLLM or OpenRouter natively uses inverse-price routing, and it "
            "does not validate live production state, queueing, latency, or provider conduct."
        ),
        "adapter_limitations": [
            (
                "LiteLLM exposes blocked status but not our economic exclusion reason; "
                "the adapter preserves the reason separately."
            ),
            (
                "LiteLLM cost-based routing sums configured input and output unit prices; "
                "fixtures split the scalar quote equally across them."
            ),
            (
                "No model request is sent, so fallback execution and service-system fidelity "
                "remain outside this experiment."
            ),
        ],
    }
    return frame, summary


def _write_plot(frame: pd.DataFrame, output_dir: Path) -> None:
    stochastic = frame[frame["diagnostic"] != "deterministic_lowest_cost"].copy()
    stochastic["label"] = (
        stochastic["fixture"].str.replace("_", " ")
        + " | "
        + stochastic["category"].astype(str)
    )
    y = list(range(len(stochastic)))
    fig, axes = plt.subplots(1, 2, figsize=(12.5, max(6.5, 0.34 * len(stochastic))))
    axes[0].errorbar(
        stochastic["observed"],
        y,
        xerr=[
            stochastic["observed"] - stochastic["ci_low"],
            stochastic["ci_high"] - stochastic["observed"],
        ],
        fmt="o",
        color="#1f5a94",
        ecolor="#7fa6c9",
        capsize=2,
        label="LiteLLM observed",
    )
    axes[0].scatter(
        stochastic["expected"], y, marker="x", color="#b43c2f", s=45, label="surrogate exact"
    )
    axes[0].set_yticks(y, stochastic["label"], fontsize=8)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("Selection probability")
    axes[0].set_title("Exact target and globally simultaneous 95% interval")
    axes[0].legend(loc="lower right")
    axes[0].grid(axis="x", alpha=0.25)

    axes[1].barh(y, 100 * stochastic["absolute_error"], color="#4472a5")
    axes[1].axvline(2.0, color="#b43c2f", linestyle="--", label="2 pp gate")
    axes[1].set_yticks(y, [])
    axes[1].invert_yaxis()
    axes[1].set_xlabel("Absolute error (percentage points)")
    axes[1].set_title("Executable versus surrogate discrepancy")
    axes[1].legend(loc="lower right")
    axes[1].grid(axis="x", alpha=0.25)
    fig.suptitle("SM4: LiteLLM executable-router conformance", fontsize=14)
    fig.tight_layout()
    fig.savefig(output_dir / "sm4_litellm_conformance.pdf", bbox_inches="tight")
    fig.savefig(output_dir / "sm4_litellm_conformance.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_release(
    output_dir: Path,
    *,
    trials_per_state: int = 10_000,
    fallback_trials: int = 10_000,
) -> dict[str, Any]:
    """Run the conformance suite and write its immutable-style evidence bundle."""
    output_dir.mkdir(parents=True, exist_ok=True)
    frame, summary = run_conformance(
        trials_per_state=trials_per_state,
        fallback_trials=fallback_trials,
    )
    parquet_path = output_dir / "sm4_litellm_conformance.parquet"
    json_path = output_dir / "sm4_litellm_conformance_summary.json"
    frame.to_parquet(parquet_path, index=False)
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _write_plot(frame, output_dir)
    report_path = output_dir / "sm4_litellm_conformance_report.md"
    report_path.write_text(
        "# SM4 LiteLLM executable-router conformance\n\n"
        f"- LiteLLM release: `{summary['litellm_version']}`\n"
        f"- Source commit: `{summary['source_commit']}`\n"
        f"- Stochastic fixtures: {summary['n_stochastic_fixtures']} at "
        f"{summary['trials_per_stochastic_state']:,} selections each\n"
        f"- Sequential fallback trials: {summary['fallback_trials']:,}\n"
        f"- Maximum absolute share error: {100 * summary['max_absolute_error']:.3f} pp\n"
        f"- All registered conformance rows pass: **{summary['all_rows_pass']}**\n\n"
        "## Interpretation\n\n"
        + summary["claim_boundary"]
        + "\n\n## Limitations\n\n"
        + "\n".join(f"- {item}" for item in summary["adapter_limitations"])
        + "\n"
    )
    artifact_paths = [
        parquet_path,
        json_path,
        report_path,
        output_dir / "sm4_litellm_conformance.pdf",
        output_dir / "sm4_litellm_conformance.png",
    ]
    manifest = {
        "experiment": summary["experiment"],
        "source_commit": summary["source_commit"],
        "parameters": {
            "trials_per_state": trials_per_state,
            "fallback_trials": fallback_trials,
        },
        "fixtures": [
            {
                "name": fixture.name,
                "exponent": fixture.exponent,
                "specs": [asdict(spec) for spec in fixture.specs],
                "actions": {
                    provider: asdict(action) for provider, action in fixture.actions.items()
                },
            }
            for fixture in frozen_fixtures()
        ],
        "artifacts": {
            path.name: {"sha256": _hash_file(path), "bytes": path.stat().st_size}
            for path in artifact_paths
        },
    }
    manifest_path = output_dir / "sm4_litellm_conformance_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("analysis"))
    parser.add_argument("--trials-per-state", type=int, default=10_000)
    parser.add_argument("--fallback-trials", type=int, default=10_000)
    args = parser.parse_args(argv)
    summary = write_release(
        args.output_dir,
        trials_per_state=args.trials_per_state,
        fallback_trials=args.fallback_trials,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["all_rows_pass"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
