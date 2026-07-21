"""Public-quote routing simulation.

This module never submits an inference request.  It turns a saved endpoint
snapshot into a *counterfactual first-route probability surface* for a fixed
set of text workloads.  The calculation follows OpenRouter's documented
default price rule: among stable low-cost providers, the first-route weight is
proportional to inverse price squared.

Important boundary: the public API does not expose the router's live 30-second
outage filter, internal score, or actual selected provider.  These rows are
therefore labelled ``simulated_route_share`` and are useful only for testing
whether changing public quotes would change the documented price-based
allocation.  They are not realized fill data.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

PANEL_ID = "routing-simulation-v2-20260721"
SELECTION_POLICY = "inverse_square_quote_cost_among_publicly_unruled_providers"
ELIGIBILITY_BASIS = (
    "positive public text quote; request capability/context not ruled out by endpoint metadata; "
    "does not observe OpenRouter's live 30-second health filter or internal score"
)

# A fixed, high-volume, multi-provider text-model panel selected from the
# 2026-07-09 weekly OpenRouter rankings, extended on 2026-07-21 to cover every
# model with a frozen WF-16 active-undercutter pair.  The new panel id prevents
# transitions from being drawn across that prospective coverage expansion.
# An operator can replace it with ORCAP_ROUTE_PANEL_MODELS=a/model,b/model.
DEFAULT_PANEL_MODELS = (
    "z-ai/glm-5.2",
    "minimax/minimax-m3",
    "stepfun/step-3.7-flash",
    "anthropic/claude-sonnet-5",
    "anthropic/claude-opus-4.8",
    "google/gemini-3.1-flash-lite",
    "openai/gpt-5.5",
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
    "tencent/hy3-preview",
    "xiaomi/mimo-v2.5-pro",
    "xiaomi/mimo-v2.5",
    "anthropic/claude-opus-4.7",
    "anthropic/claude-sonnet-4.6",
    "google/gemini-3-flash-preview",
    "deepseek/deepseek-v3.2",
    "openai/gpt-oss-120b",
    "google/gemini-2.5-flash-lite",
    "google/gemini-2.5-flash",
    "openai/gpt-4o-mini",
    # Prospective WF-19 identification extension.  z-ai/glm-5.2 and
    # deepseek/deepseek-v4-flash already appear above.
    "minimax/minimax-m2.5",
    "minimax/minimax-m2.7",
    "moonshotai/kimi-k2.6",
    "moonshotai/kimi-k2.7-code",
    "qwen/qwen3-235b-a22b-2507",
    "qwen/qwen3.6-27b",
    "z-ai/glm-4.6",
    "z-ai/glm-5",
)


@dataclass(frozen=True)
class RoutingScenario:
    """A request shape whose provider-relevant fields are public.

    The actual prompt text is deliberately absent: it is not submitted and is
    normally not an endpoint-selection field.  Token budgets and requested API
    features are the public metadata that can change the eligible set.
    """

    name: str
    input_tokens: int
    output_tokens: int
    required_parameters: tuple[str, ...] = ()


SCENARIOS = (
    RoutingScenario("short_chat", 1_000, 256),
    RoutingScenario("long_context", 32_000, 1_024),
    RoutingScenario("tool_chat", 2_000, 512, ("tools",)),
    RoutingScenario("structured_chat", 2_000, 512, ("response_format",)),
)


def panel_models() -> tuple[str, ...]:
    """Return the fixed panel, optionally replaced for a controlled rerun."""
    configured = os.environ.get("ORCAP_ROUTE_PANEL_MODELS")
    if not configured:
        return DEFAULT_PANEL_MODELS
    models = tuple(item.strip() for item in configured.split(",") if item.strip())
    if not models:
        raise ValueError("ORCAP_ROUTE_PANEL_MODELS was set but contains no model ids")
    return models


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _at_least(value: Any, minimum: int) -> bool:
    """Reject only a known-too-small public limit.

    Several otherwise valid endpoint records omit a max-token field.  Treating
    that omission as a hard rejection would manufacture a routing exclusion;
    we retain it as "not ruled out" and disclose that in ``ELIGIBILITY_BASIS``.
    """
    observed = _float(value)
    return observed is None or observed >= minimum


def _supports_parameters(endpoint: dict[str, Any], required: tuple[str, ...]) -> bool:
    if not required:
        return True
    supported = set(endpoint.get("supported_parameters") or [])
    # Require explicit capability for profiles which send a non-default API
    # feature.  This is stricter than the baseline and avoids over-including
    # endpoints when a feature is not available.
    return set(required).issubset(supported)


def _quote_cost(endpoint: dict[str, Any], scenario: RoutingScenario) -> float | None:
    prompt = _float(endpoint.get("price_prompt"))
    completion = _float(endpoint.get("price_completion"))
    request = _float(endpoint.get("price_request"))
    if prompt is None or completion is None:
        return None
    request = 0.0 if request is None else request
    if prompt < 0 or completion < 0 or request < 0:
        return None
    return prompt * scenario.input_tokens + completion * scenario.output_tokens + request


def _candidate(endpoint: dict[str, Any], scenario: RoutingScenario) -> dict[str, Any] | None:
    if not endpoint.get("provider_name"):
        return None
    required_context = scenario.input_tokens + scenario.output_tokens
    if not _at_least(endpoint.get("context_length"), required_context):
        return None
    if not _at_least(endpoint.get("max_prompt_tokens"), scenario.input_tokens):
        return None
    if not _at_least(endpoint.get("max_completion_tokens"), scenario.output_tokens):
        return None
    if not _supports_parameters(endpoint, scenario.required_parameters):
        return None
    cost = _quote_cost(endpoint, scenario)
    if cost is None:
        return None
    copy = dict(endpoint)
    copy["expected_quote_usd"] = cost
    return copy


def _provider_best_quotes(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse variants to the cheapest publicly eligible quote per provider.

    The docs describe inter-provider routing.  Public endpoint data may have
    several SKU variants under the same provider, but does not disclose their
    within-provider allocator; using the cheapest compatible quote gives one
    reproducible provider-level price while recording the number of variants.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        grouped.setdefault(str(candidate["provider_name"]), []).append(candidate)
    selected: list[dict[str, Any]] = []
    for provider, rows in grouped.items():
        best = min(
            rows,
            key=lambda row: (
                row["expected_quote_usd"],
                str(row.get("endpoint_fingerprint") or ""),
                str(row.get("tag") or ""),
            ),
        )
        best = dict(best)
        best["n_compatible_endpoint_variants"] = len(rows)
        best["provider_name"] = provider
        selected.append(best)
    return sorted(selected, key=lambda row: (row["expected_quote_usd"], row["provider_name"]))


def simulate_snapshot(
    endpoint_rows: Iterable[dict[str, Any]],
    *,
    run_ts: str,
    dt: str,
    models: tuple[str, ...] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Simulate public quote-based shares for the fixed panel at one timestamp.

    Free/zero-cost groups are deliberately excluded rather than assigning an
    invented infinite inverse-price weight.  The run ledger records those
    exclusions so absence of rows is not mistaken for zero change.
    """
    selected_models = models or panel_models()
    model_set = set(selected_models)
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in endpoint_rows:
        model_id = row.get("model_id")
        if model_id in model_set:
            by_model.setdefault(str(model_id), []).append(dict(row))

    out: list[dict[str, Any]] = []
    groups_total = len(selected_models) * len(SCENARIOS)
    groups_emitted = 0
    groups_single_provider = 0
    groups_zero_cost = 0
    groups_no_candidates = 0
    for model_id in selected_models:
        endpoints = by_model.get(model_id, [])
        for scenario in SCENARIOS:
            candidates = [
                candidate
                for endpoint in endpoints
                if (candidate := _candidate(endpoint, scenario)) is not None
            ]
            if not candidates:
                groups_no_candidates += 1
                continue
            if any(candidate["expected_quote_usd"] <= 0 for candidate in candidates):
                groups_zero_cost += 1
                continue
            provider_quotes = _provider_best_quotes(candidates)
            if len(provider_quotes) < 2:
                groups_single_provider += 1
                continue
            raw_weights = [quote["expected_quote_usd"] ** -2 for quote in provider_quotes]
            total_weight = sum(raw_weights)
            if not math.isfinite(total_weight) or total_weight <= 0:
                groups_zero_cost += 1
                continue
            min_cost = provider_quotes[0]["expected_quote_usd"]
            pairs = zip(provider_quotes, raw_weights, strict=True)
            for rank, (quote, raw_weight) in enumerate(pairs, 1):
                out.append(
                    {
                        "run_ts": run_ts,
                        "dt": dt,
                        "panel_id": PANEL_ID,
                        "selection_policy": SELECTION_POLICY,
                        "eligibility_basis": ELIGIBILITY_BASIS,
                        "model_id": model_id,
                        "model_name": quote.get("model_name"),
                        "scenario": scenario.name,
                        "input_tokens": scenario.input_tokens,
                        "output_tokens": scenario.output_tokens,
                        "required_parameters": ",".join(scenario.required_parameters),
                        "provider_name": quote["provider_name"],
                        "tag": quote.get("tag"),
                        "endpoint_fingerprint": quote.get("endpoint_fingerprint"),
                        "n_compatible_endpoint_variants": quote["n_compatible_endpoint_variants"],
                        "n_eligible_endpoints": len(candidates),
                        "n_eligible_providers": len(provider_quotes),
                        "provider_quote_rank": rank,
                        "is_lowest_public_quote": bool(
                            math.isclose(quote["expected_quote_usd"], min_cost)
                        ),
                        "expected_quote_usd": quote["expected_quote_usd"],
                        "price_prompt": _float(quote.get("price_prompt")),
                        "price_completion": _float(quote.get("price_completion")),
                        "price_request": _float(quote.get("price_request")),
                        "inverse_square_weight": raw_weight,
                        "simulated_route_share": raw_weight / total_weight,
                        "public_status": quote.get("status"),
                        "uptime_last_5m": _float(quote.get("uptime_last_5m")),
                        "uptime_last_30m": _float(quote.get("uptime_last_30m")),
                        "latency_last_30m": _float(quote.get("latency_last_30m")),
                        "throughput_last_30m": _float(quote.get("throughput_last_30m")),
                    }
                )
            groups_emitted += 1

    summary = {
        "run_ts": run_ts,
        "dt": dt,
        "panel_id": PANEL_ID,
        "selection_policy": SELECTION_POLICY,
        "configured_models": len(selected_models),
        "models_found": len(by_model),
        "scenario_count": len(SCENARIOS),
        "groups_total": groups_total,
        "groups_emitted": groups_emitted,
        "groups_no_candidates": groups_no_candidates,
        "groups_single_provider": groups_single_provider,
        "groups_zero_cost": groups_zero_cost,
        "rows": len(out),
    }
    return out, summary
