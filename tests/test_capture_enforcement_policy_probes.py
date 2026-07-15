import pandas as pd

import orcap.capture_enforcement_policy_probes as h88


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
                "status_heuristics_5m": {"success": 99, "rateLimited": 1},
                "is_deranked": False,
            },
            {
                "provider_display_name": "B",
                "status_heuristics_5m": {"success": 10, "rateLimited": 90},
                "is_deranked": False,
            },
            {
                "provider_display_name": "C",
                "status_heuristics_5m": {"success": 50, "rateLimited": 50},
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


def test_enforcement_pair_is_price_calipered_and_orders_public_stress():
    states = h88.public_enforcement_states(_endpoints(), _stats())
    pair, reason = h88.select_enforcement_pair(states)
    assert reason == "eligible"
    assert pair["safe_provider"] == "A"
    assert pair["risky_provider"] == "B"
    assert pair["price_ratio"] == 1.1
    assert pair["enforcement_stress_gap"] > 0
    assert set(states["provider_name"]) == {"A", "B", "C"}


def test_enforcement_states_require_ten_same_window_attempts():
    stats = _stats()
    stats["data"][0]["status_heuristics_5m"] = {"success": 8, "rateLimited": 1}
    states = h88.public_enforcement_states(_endpoints(), stats)
    assert set(states["provider_name"]) == {"B", "C"}


def test_collector_writes_outcome_free_candidates_and_one_redacted_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCAP_H88_RANDOMIZATION_SEED", "123")

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

    monkeypatch.setattr(h88, "_send_probe", fake_send)
    result = h88.run_enforcement_policy_probes(
        [{"model_id": "model/test", "canonical_slug": "model/test-20260701"}],
        client=_Client(),
        curated_dir=tmp_path,
    )
    assert result["candidate_models"] == 1
    assert result["eligible_pairs"] == 1
    assert result["assignments_sent"] == 1

    candidate_file = next((tmp_path / "h88_enforcement_policy_candidates").glob("*/*.parquet"))
    attempt_file = next((tmp_path / "router_route_attempts").glob("*/*.parquet"))
    candidates = pd.read_parquet(candidate_file)
    attempts = pd.read_parquet(attempt_file)
    assert len(candidates) == 1
    assert candidates.loc[0, "request_sent"]
    assert "outcome" not in candidates.columns
    assert candidates.loc[0, "candidate_state_hash"]
    assert len(attempts) == 1
    assert attempts.loc[0, "study_id"] == h88.STUDY_ID
    assert attempts.loc[0, "payload_retained"] is False or not attempts.loc[0, "payload_retained"]
