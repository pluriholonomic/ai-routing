import numpy as np

from orcap.market_env.routers_steering import CutPenaltyRouter
from orcap.market_env.state_aliasing import (
    COMMIT_LOW,
    HIGH,
    LOW,
    BinaryCutPenaltyMDP,
    evaluate_deterministic_policy,
    option_outcome,
    solve_exact,
    solve_exact_with_option,
    train_option_q,
)
from orcap.market_env.strategies_qlearn import expected_profits


def example_mdp() -> BinaryCutPenaltyMDP:
    return BinaryCutPenaltyMDP(
        low_price=0.6562682848061103,
        high_price=1.6,
        marginal_cost=0.2,
        rival_prices=(1.0, 1.0, np.exp(-0.4), np.exp(0.34)),
        theta=0.17,
        memory=7,
        gamma=0.95,
    )


def test_binary_reward_matches_stateful_router():
    mdp = example_mdp()
    prices = {
        "Me": mdp.low_price,
        "Anchor": 1.0,
        "Adopter": 1.0,
        "StaticCut": float(np.exp(-0.4)),
        "Premium": float(np.exp(0.34)),
    }
    router = CutPenaltyRouter(2.0, theta=mdp.theta, memory=mdp.memory)
    past = dict(prices)
    past["Me"] = mdp.high_price
    for _ in range(mdp.memory):
        router.advance(past)
    expected = expected_profits(
        prices, dict.fromkeys(prices, mdp.marginal_cost), router, mdp.demand
    )["Me"]
    assert np.isclose(mdp.reward(mdp.initial_state, LOW), expected, atol=1e-14)


def test_binary_history_transition_and_penalty_duration():
    mdp = example_mdp()
    state = mdp.initial_state
    for _ in range(mdp.memory):
        assert mdp.is_penalized(state, LOW)
        state = mdp.transition(state, LOW)
    assert state == 0
    assert not mdp.is_penalized(state, LOW)
    assert mdp.transition(0, HIGH) == HIGH


def test_permanent_low_formula_matches_policy_evaluation():
    mdp = example_mdp()
    always_low = np.full(mdp.n_states, LOW, dtype=np.int8)
    values = evaluate_deterministic_policy(mdp, always_low)
    assert np.isclose(
        values[mdp.initial_state], mdp.permanent_low_value(), atol=1e-10
    )


def test_exact_solution_passes_bellman_and_prefers_profitable_cut():
    mdp = example_mdp()
    exact = solve_exact(mdp)
    assert exact.bellman_residual <= 1e-10
    assert exact.policy[mdp.initial_state] == LOW
    assert mdp.permanent_low_value() > mdp.permanent_high_value()


def test_commit_option_is_exactly_a_feasible_primitive_path():
    mdp = example_mdp()
    outcome = option_outcome(mdp, mdp.initial_state, COMMIT_LOW)
    state = mdp.initial_state
    discounted = 0.0
    for offset in range(mdp.memory + 1):
        discounted += mdp.gamma**offset * mdp.reward(state, LOW)
        state = mdp.transition(state, LOW)
    assert outcome.duration == mdp.memory + 1
    assert outcome.successor == state == 0
    assert np.isclose(outcome.discounted_reward, discounted, atol=1e-14)


def test_option_does_not_change_exact_feasible_value():
    mdp = example_mdp()
    primitive = solve_exact(mdp)
    option = solve_exact_with_option(mdp)
    assert option.bellman_residual <= 1e-10
    assert np.allclose(option.values, primitive.values, atol=1e-10)


def test_option_training_respects_exact_transition_budget():
    mdp = example_mdp()
    result = train_option_q(
        mdp, seed=3, train_transitions=101, evaluation_transitions=103
    )
    assert result["train_transitions"] == 101
    assert result["evaluation_transitions"] == 103
    assert result["exact_option_value_gap"] <= 1e-10
