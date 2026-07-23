import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

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


def test_isolated_runner_uses_one_fresh_process_per_module(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, check):
        assert check is False
        calls.append(command)
        name = command[command.index("--module") + 1]
        result_file = Path(command[command.index("--result-file") + 1])
        result_file.write_text(
            json.dumps(
                {
                    "analysis_source": {"revision": "frozen"},
                    "result": {
                        "evidence_status": f"{name}_complete",
                        "claim_boundary": f"{name} boundary",
                    },
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(price_tests_online.subprocess, "run", fake_run)
    results = price_tests_online._run_modules_isolated(tmp_path)
    assert list(results) == list(price_tests_online._runners())
    assert len(calls) == len(price_tests_online._runners())
    assert all("--module" in call and "--result-file" in call for call in calls)


def test_isolated_runner_fails_closed_on_terminated_module(monkeypatch, tmp_path):
    monkeypatch.setattr(
        price_tests_online.subprocess,
        "run",
        lambda command, check: subprocess.CompletedProcess(command, 143),
    )
    with pytest.raises(RuntimeError, match=r"module h2 exited 143"):
        price_tests_online._run_modules_isolated(tmp_path)


def test_price_workflow_isolates_analysis_modules():
    workflow = (
        Path(__file__).parents[1] / ".github/workflows/price-tests-online.yml"
    ).read_text(encoding="utf-8")
    assert "--isolate-modules" in workflow
