import pandas as pd

import orcap.capture_capacity_policy_probes as h87


def _endpoints():
    return {
        "data": {
            "endpoints": [
                {
                    "provider_name": "A",
                    "pricing": {"completion": "1.0e-6", "prompt": "1.0e-7"},
                },
                {
                    "provider_name": "B",
                    "pricing": {"completion": "1.1e-6", "prompt": "1.0e-7"},
                },
                {
                    "provider_name": "C",
                    "pricing": {"completion": "2.0e-6", "prompt": "1.0e-7"},
                },
            ]
        }
    }


def _stats():
    return {
        "data": [
            {
                "provider_display_name": "A",
                "fortuna": {"capacity_ceiling_rpm": 100, "recent_peak_rpm": 10},
                "is_deranked": False,
            },
            {
                "provider_display_name": "B",
                "fortuna": {"capacity_ceiling_rpm": 20, "recent_peak_rpm": 18},
                "is_deranked": False,
            },
            {
                "provider_display_name": "C",
                "fortuna": {"capacity_ceiling_rpm": 50, "recent_peak_rpm": 25},
                "is_deranked": False,
            },
        ]
    }


class _Response:
    def __init__(self, body, status=200):
        self._body = body
        self.status_code = status

    def json(self):
        return self._body


class _Client:
    def get(self, url):
        return _Response(_stats() if "stats/endpoint" in url else _endpoints())


def test_capacity_pair_is_price_calipered_and_orders_public_risk():
    states = h87.public_provider_states(_endpoints(), _stats())
    pair, reason = h87.select_capacity_pair(states)
    assert reason == "eligible"
    assert pair["safe_provider"] == "A"
    assert pair["risky_provider"] == "B"
    assert pair["price_ratio"] == 1.1
    assert pair["capacity_risk_gap"] > 0
    # C is operationally complete but outside the 25% price caliper from A/B.
    assert set(states["provider_name"]) == {"A", "B", "C"}


def test_collector_writes_outcome_free_candidates_and_one_redacted_attempt(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("ORCAP_H87_RANDOMIZATION_SEED", "123")

    def fake_send(_client, model_id, provider=None, **_kwargs):
        completion = {"id": "generation-1", "provider": provider, "usage": {"cost": 1e-6}}
        generation = {
            "data": {
                "provider_name": provider or "A",
                "latency": 12,
                "native_tokens_prompt": 5,
                "native_tokens_completion": 1,
                "total_cost": 1e-6,
            }
        }
        return completion, generation, None, 200

    monkeypatch.setattr(h87, "_send_probe", fake_send)
    result = h87.run_capacity_policy_probes(
        [{"model_id": "model/test", "canonical_slug": "model/test-20260701"}],
        client=_Client(),
        curated_dir=tmp_path,
    )
    assert result["candidate_models"] == 1
    assert result["eligible_pairs"] == 1
    assert result["assignments_sent"] == 1

    candidate_file = next(
        (tmp_path / "h87_capacity_policy_candidates").glob("*/*.parquet")
    )
    attempt_file = next((tmp_path / "router_route_attempts").glob("*/*.parquet"))
    candidates = pd.read_parquet(candidate_file)
    attempts = pd.read_parquet(attempt_file)
    assert len(candidates) == 1
    assert candidates.loc[0, "request_sent"]
    assert "outcome" not in candidates.columns
    assert candidates.loc[0, "candidate_state_hash"]
    assert len(attempts) == 1
    assert attempts.loc[0, "study_id"] == h87.STUDY_ID
    assert attempts.loc[0, "payload_retained"] is False or not attempts.loc[0, "payload_retained"]

