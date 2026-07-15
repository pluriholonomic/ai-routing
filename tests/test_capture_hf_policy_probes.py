import pandas as pd

import orcap.capture_hf_policy_probes as h89


def _models():
    return {
        "data": [
            {
                "id": "model/test",
                "providers": [
                    {
                        "provider": "cheap",
                        "status": "live",
                        "pricing": {"input": 0.02, "output": 0.04},
                        "throughput": 10,
                    },
                    {
                        "provider": "fast",
                        "status": "live",
                        "pricing": {"input": 0.024, "output": 0.045},
                        "throughput": 100,
                    },
                    {
                        "provider": "too-expensive",
                        "status": "live",
                        "pricing": {"input": 1.0, "output": 1.0},
                        "throughput": 200,
                    },
                ],
            }
        ]
    }


class _Response:
    def __init__(self, body, status=200, headers=None):
        self._body = body
        self.status_code = status
        self.headers = {"content-type": "application/json", **(headers or {})}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(self.status_code)


class _Client:
    def get(self, _url, headers=None):
        return _Response(_models())

    def post(self, _url, headers=None, json=None):
        suffix = json["model"].rsplit(":", 1)[-1]
        provider = "fast" if suffix == "fastest" else "cheap" if suffix == "cheapest" else suffix
        return _Response(
            {
                "id": "hf-generation-1",
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 1,
                    "estimated_cost": 1e-6,
                },
            },
            headers={"x-inference-provider": provider, "x-request-id": "request-1"},
        )


def test_public_policy_state_uses_documented_cheapest_and_cost_caliper():
    state, reason = h89.public_policy_state(_models(), "model/test")
    assert reason == "eligible"
    assert state["public_cheapest_provider"] == "cheap"
    assert state["public_fastest_provider"] == "too-expensive"
    assert state["public_cost_caliper_provider"] == "fast"
    assert state["public_provider_count"] == 3


def test_h89_collector_writes_outcome_free_candidates_and_redacted_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setenv("ORCAP_H89_RANDOMIZATION_SEED", "123")
    result = h89.run_hf_policy_probes(
        ["model/test"], client=_Client(), curated_dir=tmp_path
    )
    assert result["candidate_models"] == 1
    assert result["eligible_models"] == 1
    assert result["assignments_sent"] == 1
    candidate_file = next((tmp_path / "h89_hf_policy_candidates").glob("*/*.parquet"))
    attempt_file = next((tmp_path / "router_route_attempts").glob("*/*.parquet"))
    candidates = pd.read_parquet(candidate_file)
    attempts = pd.read_parquet(attempt_file)
    assert "outcome" not in candidates.columns
    assert candidates.loc[0, "candidate_state_hash"]
    assert candidates.loc[0, "request_sent"]
    assert attempts.loc[0, "study_id"] == h89.STUDY_ID
    assert attempts.loc[0, "selected_provider"]
    assert not bool(attempts.loc[0, "payload_retained"])
