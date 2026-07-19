import numpy as np

from orcap.analysis.h96_route_calibration import fit_eta as fit_h96_eta
from orcap.analysis.router_exponent import (
    block_bootstrap_interval,
    fit_exponent,
    probabilities,
    score,
    support_status,
)


def synthetic_choices(eta: float, n: int = 1200, seed: int = 7):
    rng = np.random.default_rng(seed)
    rows = []
    for index in range(n):
        spread = 1.05 + 0.7 * ((index % 17) / 16)
        costs = np.array([1.0, spread, spread**2])
        selected = int(rng.choice(len(costs), p=probabilities(costs, eta)))
        rows.append(
            {
                "block_id": f"b-{index // 3}",
                "model_id": f"m-{index % 7}",
                "selected_provider": f"p-{selected}",
                "costs": costs,
                "selected_index": selected,
            }
        )
    return rows


def test_probability_vector_and_input_validation():
    p = probabilities(np.array([1.0, 2.0, 4.0]), 2.0)
    assert np.isclose(p.sum(), 1.0)
    assert np.all(np.diff(p) < 0)
    for costs in (np.array([]), np.array([0.0, 1.0]), np.array([np.nan, 1.0])):
        try:
            probabilities(costs, 1.0)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid costs should fail")


def test_known_exponent_is_recovered_and_scored():
    rows = synthetic_choices(2.25)
    fitted = fit_exponent(rows)
    assert fitted["fit_ready"]
    assert abs(fitted["eta_hat"] - 2.25) < 0.30
    assert fitted["eta_profile_ci_low"] <= 2.25 <= fitted["eta_profile_ci_high"]
    metrics = score(rows, fitted["eta_hat"])
    assert metrics["n"] == len(rows)
    assert 0 <= metrics["top_one_accuracy"] <= 1
    assert metrics["mean_log_loss"] >= 0


def test_support_gates_and_numpy_cost_arrays_do_not_raise():
    rows = synthetic_choices(1.5, n=450)
    status = support_status(
        rows,
        minimum_choices=200,
        minimum_models=5,
        minimum_providers=3,
        minimum_blocks=100,
    )
    assert status["status"] == "ready"
    assert not status["failures"]
    assert support_status(rows[:10])["status"] == "insufficient_support"


def test_block_bootstrap_is_reproducible_and_contains_plausible_value():
    rows = synthetic_choices(1.8, n=500)
    first = block_bootstrap_interval(rows, draws=40, seed=33)
    second = block_bootstrap_interval(rows, draws=40, seed=33)
    assert first == second
    assert first[0] is not None and first[0] < 1.8 < first[1]


def test_common_point_estimate_is_backward_compatible_with_h96():
    rows = synthetic_choices(2.1, n=180)
    common = fit_exponent(rows)
    legacy = fit_h96_eta(rows)
    assert abs(common["eta_hat"] - legacy["eta_hat"]) < 1e-5
    assert abs(common["eta_profile_ci_low"] - legacy["eta_profile_ci_low"]) <= 0.01
    assert abs(common["eta_profile_ci_high"] - legacy["eta_profile_ci_high"]) <= 0.01
