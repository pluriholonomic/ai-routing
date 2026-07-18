from orcap.market_env.experiments_sim import _market_seed, _paired_bootstrap_ci


def test_market_seed_is_stable_and_market_specific():
    assert _market_seed(7, "model-a") == 12998580639844196237
    assert _market_seed(7, "model-a") != _market_seed(7, "model-b")
    assert _market_seed(7, "model-a") != _market_seed(8, "model-a")


def test_paired_bootstrap_interval_is_deterministic_and_directional():
    values = [0.1, 0.2, 0.3, 0.4]
    first = _paired_bootstrap_ci(values, draws=1_000)
    second = _paired_bootstrap_ci(values, draws=1_000)
    assert first == second
    assert first is not None and first[0] > 0
