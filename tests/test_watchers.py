import pandas as pd

from orcap.capture_fees import pct_tokens
from orcap.capture_labstatus import incident_rows
from orcap.capture_probes import _pinned_targets
import random


def test_pct_tokens_extracts_values_with_context():
    text = "OpenRouter charges a 5.5% fee when you buy credits. BYOK costs 5%."
    toks = pct_tokens(text)
    assert [t["value"] for t in toks] == [5.5, 5.0]
    assert "credits" in toks[0]["context"]


def test_incident_rows_flatten_components():
    body = {"incidents": [{"id": "abc", "name": "Elevated errors", "impact": "major",
                           "status": "resolved", "created_at": "2026-07-01T00:00:00Z",
                           "resolved_at": "2026-07-01T02:00:00Z",
                           "components": [{"name": "API"}, {"name": "Chat"}]}]}
    rows = incident_rows("openai", body, "20260714T000000Z", "2026-07-14")
    assert rows[0]["components"] == "API,Chat"
    assert rows[0]["impact"] == "major"


def test_pinned_targets_orders_cheapest_second_random():
    eps = [{"provider": "A", "price": 1.0}, {"provider": "B", "price": 2.0},
           {"provider": "C", "price": 3.0}, {"provider": "D", "price": 4.0}]
    picks = _pinned_targets(eps, random.Random(0))
    assert picks[0] == ("pinned_cheapest", eps[0])
    assert picks[1] == ("pinned_second", eps[1])
    assert picks[2][0] == "pinned_random" and picks[2][1] in eps[2:]
    assert _pinned_targets(eps[:1], random.Random(0)) == []
