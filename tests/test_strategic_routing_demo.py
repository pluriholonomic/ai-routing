from __future__ import annotations

import pytest

from examples.strategic_routing_demo import run_demo


def test_demo_is_deterministic_and_reconciles_every_epoch():
    first = run_demo(seed=31)
    second = run_demo(seed=31)
    assert first == second
    assert first["agents"] == ["owned", "spot"]
    assert len(first["epochs"]) == 4
    assert all(abs(row["reconciliation_error"]) <= 1e-12 for row in first["epochs"])
    assert not any(row["done"] for row in first["epochs"][:-1])
    assert first["epochs"][-1]["done"]


def test_demo_rejects_invalid_horizon_through_environment_contract():
    with pytest.raises(ValueError):
        run_demo(horizon=0)
