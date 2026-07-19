import pandas as pd

from orcap.analysis import price_tests_online


class FrameResult:
    def __init__(self, frame):
        self.frame = frame

    def df(self):
        return self.frame.copy()


def test_synchronization_monitor_counts_pairs_and_preserves_claim_boundary(
    monkeypatch, tmp_path
):
    frame = pd.DataFrame(
        [
            {
                "changed_at_run_ts": "20260719T000000Z",
                "model_id": "m1",
                "provider_name": provider,
                "old_price": 2.0,
                "new_price": 1.0,
            }
            for provider in ("a", "b", "c")
        ]
    )
    monkeypatch.setattr(price_tests_online.data, "q", lambda _sql: FrameResult(frame))
    result = price_tests_online._synchronization_monitor(tmp_path)
    assert result["same_direction_pairs"] == 3
    assert result["multi_provider_cells"] == 1
    assert "do not identify" in result["claim_boundary"]
    assert (tmp_path / "synchronization-cells.parquet").is_file()


def test_synchronization_monitor_power_gates_empty_input(monkeypatch, tmp_path):
    monkeypatch.setattr(
        price_tests_online.data, "q", lambda _sql: FrameResult(pd.DataFrame())
    )
    result = price_tests_online._synchronization_monitor(tmp_path)
    assert result["evidence_status"] == "power_gated"
    assert result["n_price_changes"] == 0
