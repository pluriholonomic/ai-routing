import pandas as pd

from orcap.analysis import wf2_jrw_steering as wf2
from orcap.analysis import wf7_pinned_asymmetry as wf7
from orcap.analysis.blinding import exclude_outcome_blinded


class _FrameResult:
    def __init__(self, frame):
        self.frame = frame

    def df(self):
        return self.frame.copy()


def _attempt(policy, study_id, event):
    return {
        "event_id": event,
        "observed_at": "20260715T000000Z",
        "model_id": "model/a",
        "policy": policy,
        "requested_provider": "Provider",
        "selected_provider": "Provider",
        "outcome": "succeeded",
        "retry_reason": None,
        "study_id": study_id,
    }


def test_shared_filter_excludes_both_power_gated_studies():
    frame = pd.DataFrame(
        [
            _attempt("legacy", "openrouter-default-probes-v1", "legacy"),
            _attempt("pinned_cheapest", "openrouter-routing-crossover-v2", "h80"),
            _attempt(
                "delegated_default",
                "openrouter-fallback-selection-decomposition-v1",
                "h81",
            ),
        ]
    )

    filtered, excluded = exclude_outcome_blinded(frame)

    assert excluded == 2
    assert filtered["event_id"].tolist() == ["legacy"]


def test_wf2_gate_ignores_prospective_default_outcomes(monkeypatch, tmp_path):
    rows = [_attempt("openrouter_default", "openrouter-default-probes-v1", "legacy")]
    rows.extend(
        _attempt("openrouter_default", "openrouter-routing-crossover-v2", f"h80-{i}")
        for i in range(100)
    )
    monkeypatch.setattr(wf2.data, "q", lambda _sql: _FrameResult(pd.DataFrame(rows)))

    summary = wf2.run(tmp_path)

    assert summary["evidence_status"] == "power_gated"
    assert summary["gate"] == "only 1/100 default probes"


def test_wf7_gate_ignores_prospective_pinned_outcomes(monkeypatch, tmp_path):
    rows = [_attempt("pinned_cheapest", "openrouter-default-probes-v1", "legacy")]
    rows.extend(
        _attempt("pinned_cheapest", "openrouter-routing-crossover-v2", f"h80-{i}")
        for i in range(200)
    )
    monkeypatch.setattr(wf7.data, "q", lambda _sql: _FrameResult(pd.DataFrame(rows)))

    summary = wf7.run(tmp_path)

    assert summary["evidence_status"] == "power_gated"
    assert summary["gate"] == "only 1/150 pinned probes"
