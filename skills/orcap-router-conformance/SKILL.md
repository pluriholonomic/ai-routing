---
name: orcap-router-conformance
description: Use when building or running executable-router adapters that validate the fast market kernel against real routing code — LiteLLM (first baseline), llm-d Router + Inference Sim (main systems test), vLLM Router (non-price systems control) — or when interpreting conformance gates, Monte Carlo share intervals, or systems-fidelity thresholds. Covers WP5 and Section 11 of the execution plan.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [orcap, simulation, conformance, litellm, llm-d, vllm]
    related_skills: [orcap-market-env-kernel, orcap-strategic-experiments, orcap-repo-orientation]
---

# ORCAP Router Conformance

## Overview

The fast kernel is a surrogate. Conformance proves its allocation rule and
latency/failure distributions match executable routing code under identical
provider snapshots. Disagreements are reported as adapter limitations, never
averaged away.

Execution plan WP5 + Section 11
(docs/strategic-routing-simulation-execution-plan-2026-07-18.md); background
survey: docs/routing-sim-survey-2026-07-18.md and
docs/open-source-routing-strategic-simulation-2026-07-18.md.

## Adapter ladder (implement in this order)

1. **LiteLLM (first, Python-native, shortest loop)**
   - Represent each simulated provider as a local mock deployment.
   - Exercise `litellm/router_strategy/`: weighted, lowest-cost, least-busy,
     lowest-latency, usage/rate-limit (lowest_tpm_rpm_v2), plus a custom
     quote-score strategy for inverse-eta selection.
   - Push synthetic observations via `log_success_event` into the DualCache;
     call `_get_available_deployments()`; never hit network.
   - >= 10,000 selections per stochastic state; runs local/CI.

2. **llm-d Router + llm-d Inference Sim (main systems test; remote Linux +
   containers, Kind/Kubernetes)**
   - One Inference Sim deployment per provider type; calibrate service
     profiles and failure injection.
   - Publish quote, capacity-headroom, queue, latency metrics; add a quote
     scorer returning price^(-eta); compose with stock weighted-random picker.
   - Replay controlled request traces identical to fast-kernel scenarios;
     record selected endpoint, fallback, latency, throughput, queue state,
     failure under a synthetic study ID.

3. **vLLM Router (non-price systems control)**
   - random, round-robin, power-of-two, cache-aware policies only — an
     independent check that systems behavior, not price logic, drives
     differences.

4. **Vidur (offline held-out service grid)** — latency/throughput oracle for
   the queue-surrogate fidelity gate; not a routing surface.

Do not make llm-d infrastructure a critical-path dependency for the first
result (plan §17). A conformance failure on llm-d after LiteLLM passes narrows
claims to accounting/mechanism outcomes, not a stop.

## Conformance gate (all required to pass)

- candidate eligibility agrees exactly on supported fixtures;
- deterministic router choices agree exactly;
- each stochastic provider share lies inside its simultaneous 95% Monte Carlo
  interval AND absolute error <= 2 percentage points;
- fallback order and exclusion reasons agree;
- fast-kernel latency/failure distributions pass the systems-fidelity gate.

## Systems-fidelity gate (Section 11)

Fit the queue surrogate on one llm-d/Vidur grid, validate on a DISJOINT grid
over request lengths, service speed, concurrent load, queue limit, cache hit
rate, failure/timeout rate, fallback depth. Promotion thresholds:

- median latency relative error <= 10%
- p95 latency relative error <= 20%
- throughput relative error <= 10%
- failure/fallback absolute calibration error <= 3 percentage points
- provider-ranking Spearman >= 0.9

Miss any gate: rerun systems conclusions through the executable backend or
narrow to accounting/mechanism outcomes.

## Pitfalls

- OpenRouter's own router is closed-source; the ground truth is the documented
  inverse-square rule with a 30s outage filter the public API does not expose —
  the surrogate can never be conformance-tested against OpenRouter itself,
  only against the documented formula (`src/orcap/routing_simulation.py`).
- llm-d/Vidur run remotely; keep their results in a separate workflow
  (.github/workflows) from fast-kernel training outputs, with separate
  artifact namespaces.
- No GPU is required for the initial conformance suite; do not add one.
- Adapter code lives outside the kernel (`adapters/` per the target layout);
  the kernel must not import LiteLLM, llm-d, or any router SDK.
