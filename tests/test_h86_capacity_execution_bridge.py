import json

import pandas as pd
import pytest

from orcap.analysis.h86_capacity_execution_bridge import (
    analyze,
    attach_public_state,
    legacy_pinned_attempts,
    public_provider_states,
    risk_pairs,
)


def _public_row(ts: pd.Timestamp, provider: str, endpoint: str, ceiling: float, peak: float):
    return {
        "run_ts": ts.strftime("%Y%m%dT%H%M%SZ"),
        "dt": ts.strftime("%Y-%m-%d"),
        "model_permaslug": "model/test",
        "endpoint_uuid": endpoint,
        "provider_name": provider,
        "price_completion": {"A": 1.0, "B": 1.1, "C": 1.05}[provider],
        "success_5m": 20,
        "rate_limited_5m": 0,
        "derankable_error_30m": 0,
        "request_count_30m": 20,
        "capacity_ceiling_rpm": ceiling,
        "recent_peak_rpm": peak,
        "is_deranked": False,
        "source": "congestion_intraday",
    }


def _attempt(
    observed: pd.Timestamp,
    policy: str,
    provider: str | None,
    outcome: str,
    event: str,
    rank: int | None,
    *,
    study_id: str = "openrouter-default-probes-v1",
):
    metadata = {"status_code": 200 if outcome == "succeeded" else 429}
    if rank is not None:
        metadata.update(
            {
                "quoted_rank": rank,
                "quoted_price_completion": {"A": 1.0, "B": 1.1, "C": 1.05}[provider],
                "n_quoted": 3,
            }
        )
    return {
        "event_id": event,
        "observed_at": observed.isoformat(),
        "router": "openrouter",
        "source": "openrouter_generation",
        "study_id": study_id,
        "request_ref": event,
        "model_id": "model/test",
        "requested_provider": provider,
        "selected_provider": provider if outcome == "succeeded" else None,
        "attempt_index": 0,
        "outcome": outcome,
        "retry_reason": None if outcome == "succeeded" else "http_429",
        "fallback_triggered": False,
        "policy": policy,
        "cost_usd": 0.000001 if outcome == "succeeded" else None,
        "latency_ms": 100 if outcome == "succeeded" else None,
        "metadata_json": json.dumps(metadata),
        "run_ts": observed.strftime("%Y%m%dT%H%M%SZ"),
    }


def _fixture():
    public = []
    attempts = []
    start = pd.Timestamp("2026-07-13T00:00:00Z")
    for block in range(6):
        snapshot = start + pd.Timedelta(hours=int(block))
        public.extend(
            [
                _public_row(snapshot, "A", f"a-{block}", 100, 10),
                _public_row(snapshot, "B", f"b-{block}", 20, 18),
                _public_row(snapshot, "C", f"c-{block}", 50, 25),
            ]
        )
        observed = snapshot + pd.Timedelta(minutes=5.0)
        attempts.extend(
            [
                _attempt(
                    observed,
                    "openrouter_default",
                    None,
                    "succeeded",
                    f"default-{block}",
                    None,
                ),
                _attempt(
                    observed + pd.Timedelta(seconds=1.0),
                    "pinned_cheapest",
                    "A",
                    "succeeded",
                    f"a-{block}",
                    0,
                ),
                _attempt(
                    observed + pd.Timedelta(seconds=2.0),
                    "pinned_second",
                    "B",
                    "failed",
                    f"b-{block}",
                    1,
                ),
                _attempt(
                    observed + pd.Timedelta(seconds=3.0),
                    "pinned_random",
                    "C",
                    "succeeded" if block % 2 else "failed",
                    f"c-{block}",
                    2,
                ),
            ]
        )
    attempts.append(
        _attempt(
            start + pd.Timedelta(days=1.0),
            "pinned_cheapest",
            "A",
            "failed",
            "prospective-must-stay-blinded",
            0,
            study_id="openrouter-routing-crossover-v2",
        )
    )
    return pd.DataFrame(attempts), pd.DataFrame(public)


def test_provider_state_and_asof_join_are_backward_and_exact():
    attempts, public = _fixture()
    pinned = legacy_pinned_attempts(attempts)
    states = public_provider_states(public)
    joined = attach_public_state(pinned, states)

    assert len(pinned) == 18
    assert set(pinned["study_id"]) == {"openrouter-default-probes-v1"}
    assert joined["public_join_status"].eq("matched_exact_backward").all()
    assert joined["public_state_age_minutes"].between(5, 5.1).all()
    risks = joined.groupby("requested_provider")["public_capacity_risk"].mean()
    assert risks["B"] > risks["C"] > risks["A"]


def test_provider_state_tolerates_missing_public_capacity_fields():
    _, public = _fixture()
    public.loc[0, "recent_peak_rpm"] = pd.NA
    public.loc[1, "capacity_ceiling_rpm"] = pd.NA
    states = public_provider_states(public)
    assert len(states) == 18
    assert "capacity_risk" in states


def test_risk_pairs_and_full_analysis_recover_synthetic_direction(tmp_path):
    attempts, public = _fixture()
    joined = attach_public_state(
        legacy_pinned_attempts(attempts), public_provider_states(public)
    )
    pairs = risk_pairs(joined)
    assert len(pairs) == 6
    assert set(pairs["high_provider"]) == {"B"}
    assert set(pairs["low_provider"]) == {"A"}
    assert pairs["failure_difference"].eq(1).all()

    summary = analyze(attempts, public, tmp_path)
    assert summary["primary_failure_contrast"]["mean"] == pytest.approx(1.0)
    assert summary["paired_sign_test"]["one_sided_p"] == pytest.approx(0.015625)
    assert summary["support"]["capacity_risk_complete_attempts"] == 18
    assert summary["evidence_status"] == "retrospective_capacity_execution_bridge"
    assert (tmp_path / "h86_capacity_execution_bridge.pdf").exists()


def test_empty_capacity_support_is_reported_without_outcomes(tmp_path):
    attempts, public = _fixture()
    public["capacity_ceiling_rpm"] = pd.NA
    summary = analyze(attempts, public, tmp_path)
    assert summary["support"]["risk_pairs"] == 0
    assert summary["primary_failure_contrast"]["mean"] is None
    assert summary["primary_failure_contrast"]["n"] == 0
    assert not (tmp_path / "h86_capacity_execution_bridge.pdf").exists()
