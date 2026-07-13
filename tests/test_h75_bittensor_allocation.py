import pandas as pd

from orcap.analysis.h75_bittensor_allocation import coverage_gate, snapshot_panel


def _frames(days=1):
    neurons = []
    weights = []
    for index, day in enumerate(pd.date_range("2026-01-01", periods=days, freq="D")):
        run_ts = day.strftime("%Y%m%dT000000Z")
        block = 100 + index
        for uid, validator, stake, incentive, emission in [
            (0, True, 10.0, 0.0, 0.5),
            (1, False, 2.0, 0.75, 0.35),
            (2, False, 1.0, 0.25, 0.15),
        ]:
            neurons.append(
                {
                    "run_ts": run_ts,
                    "dt": day.strftime("%Y-%m-%d"),
                    "source": "bittensor_chutes",
                    "netuid": 64,
                    "mechid": 0,
                    "block_number": block,
                    "block_hash": f"0x{block}",
                    "subnet_name": "Chutes",
                    "uid": uid,
                    "active": True,
                    "validator_permit": validator,
                    "stake": stake,
                    "incentive": incentive,
                    "emission": emission,
                }
            )
        for miner_uid, weight in [(1, 0.75), (2, 0.25)]:
            weights.append(
                {
                    "run_ts": run_ts,
                    "source": "bittensor_chutes",
                    "netuid": 64,
                    "mechid": 0,
                    "block_number": block,
                    "block_hash": f"0x{block}",
                    "validator_uid": 0,
                    "miner_uid": miner_uid,
                    "weight": weight,
                    "matrix_size": 3,
                    "matrix_complete_sparse_encoding": True,
                }
            )
    return pd.DataFrame(neurons), pd.DataFrame(weights)


def test_h75_recovers_transparent_weight_to_incentive_allocation():
    neurons, weights = _frames()
    panel = snapshot_panel(neurons, weights)

    assert len(panel) == 1
    assert panel.iloc[0]["neurons"] == 3
    assert panel.iloc[0]["validators"] == 1
    assert panel.iloc[0]["nonzero_weight_edges"] == 2
    assert panel.iloc[0]["matrix_complete"]
    assert panel.iloc[0]["stake_weighted_incoming_to_incentive_spearman"] == 1.0


def test_h75_power_gate_requires_repeated_complete_snapshots():
    neurons, weights = _frames(days=2)
    gate = coverage_gate(snapshot_panel(neurons, weights))

    assert gate["status"] == "power_gated"
    assert gate["complete_snapshots"] == 2
    assert "only 2/90 complete metagraph snapshots" in gate["gate_reasons"]
