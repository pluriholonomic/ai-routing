import numpy as np

from orcap.capture_bittensor import metagraph_snapshot, neuron_rows, weight_rows


class Metagraph:
    uids = np.array([0, 1, 2])
    hotkeys = ["validator", "miner-a", "miner-b"]
    coldkeys = ["cold-v", "cold-a", "cold-b"]
    active = np.array([1, 1, 0])
    validator_permit = np.array([1, 0, 0])
    stake = np.array([10.0, 2.0, 1.0])
    alpha_stake = np.array([8.0, 2.0, 1.0])
    tao_stake = np.array([2.0, 0.0, 0.0])
    consensus = np.array([0.0, 0.6, 0.4])
    incentive = np.array([0.0, 0.7, 0.3])
    dividends = np.array([1.0, 0.0, 0.0])
    emission = np.array([0.5, 0.35, 0.15])
    validator_trust = np.array([0.9, 0.0, 0.0])
    last_update = np.array([100, 99, 98])
    block = np.array(101)
    W = np.array([[0.0, 0.75, 0.25], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])


def test_bittensor_rows_keep_scoring_allocation_separate_from_request_routing():
    snapshot = metagraph_snapshot(
        Metagraph(), block_hash="0xabc", netuid=64, mechid=0, network="finney"
    )
    neurons = neuron_rows(snapshot, "20260713T000000Z", "2026-07-13")
    weights = weight_rows(snapshot, "20260713T000000Z", "2026-07-13")

    assert snapshot["matrix_complete"] is True
    assert len(neurons) == 3
    assert neurons[0]["validator_permit"] is True
    assert neurons[1]["incentive"] == 0.7
    assert "not a request route" in neurons[0]["metric_definition"]
    assert len(weights) == 2
    assert weights[0]["validator_uid"] == 0
    assert weights[0]["miner_uid"] == 1
    assert weights[0]["weight"] == 0.75
    assert weights[0]["matrix_complete_sparse_encoding"] is True


def test_bittensor_snapshot_fails_closed_on_incomplete_weight_matrix():
    metagraph = Metagraph()
    metagraph.W = np.ones((2, 2))

    try:
        metagraph_snapshot(
            metagraph, block_hash="0xabc", netuid=64, mechid=0, network="finney"
        )
    except ValueError as exc:
        assert "weights shape" in str(exc)
    else:
        raise AssertionError("expected incomplete matrix to fail")
