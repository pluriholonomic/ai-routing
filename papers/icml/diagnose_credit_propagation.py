"""Replay frozen E-SIM6 learners and diagnose late credit propagation.

This is a descriptive audit of the already-frozen experiment.  It does not
change seeds, budgets, gates, or outcomes.  Each replay must reproduce the
stored Q-table before its visitation diagnostics are accepted.
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from orcap.market_env.state_aliasing import (
    HIGH,
    LOW,
    BinaryCutPenaltyMDP,
    BinaryQAgent,
)

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "output/market_env/esim6/93265b9b03/results.json"
OUT = Path(__file__).with_name("credit-propagation-diagnostic.json")
CHECKPOINTS = (100_000, 200_000)


def _profile() -> BinaryCutPenaltyMDP:
    return BinaryCutPenaltyMDP(
        low_price=0.6562682848061103,
        high_price=1.6,
        marginal_cost=0.2,
        rival_prices=(1.0, 1.0, float(np.exp(-0.4)), float(np.exp(0.34))),
        exponent=2.0,
        theta=0.17,
        memory=7,
        gamma=0.95,
    )


def _trailing_low_depth(state: int, memory: int) -> int:
    depth = 0
    for offset in range(memory):
        if (state >> offset) & 1 == HIGH:
            break
        depth += 1
    return depth


def _trace_seed(args: tuple[int, list[list[float]]]) -> dict:
    seed, frozen_q_table = args
    mdp = _profile()
    agent = BinaryQAgent(
        memory=mdp.memory,
        observation="history",
        alpha=0.15,
        gamma=mdp.gamma,
        beta=2e-5,
        seed=seed,
    )
    rewards = mdp.reward_table()
    successors = np.asarray(
        [
            [mdp.transition(state, action) for action in (LOW, HIGH)]
            for state in range(mdp.n_states)
        ],
        dtype=np.int16,
    )
    visits = {checkpoint: np.zeros(mdp.memory + 1, dtype=np.int64) for checkpoint in CHECKPOINTS}
    all_low_hits: list[int] = []
    state = mdp.initial_state
    for step in range(300_000):
        depth = _trailing_low_depth(state, mdp.memory)
        for checkpoint in CHECKPOINTS:
            if step >= checkpoint:
                visits[checkpoint][depth] += 1
        action = agent.act(state)
        next_state = int(successors[state, action])
        agent.update(state, action, float(rewards[state, action]), next_state)
        state = next_state
        if state == 0:
            all_low_hits.append(step + 1)

    frozen = np.asarray(frozen_q_table, dtype=float)
    max_q_error = float(np.max(np.abs(agent.q - frozen)))
    if max_q_error > 1e-12:
        raise RuntimeError(f"seed {seed} did not reproduce frozen Q-table: {max_q_error}")
    policy = agent.q.argmax(axis=1)
    return {
        "seed": seed,
        "first_all_low_transition": min(all_low_hits),
        "all_low_transitions": len(all_low_hits),
        "all_low_transitions_after_100k": sum(step > 100_000 for step in all_low_hits),
        "all_low_transitions_after_200k": sum(step > 200_000 for step in all_low_hits),
        "visits_by_trailing_low_depth_after_100k": visits[100_000].tolist(),
        "visits_by_trailing_low_depth_after_200k": visits[200_000].tolist(),
        "deepest_depth_after_100k": int(np.flatnonzero(visits[100_000])[-1]),
        "final_initial_action": int(policy[mdp.initial_state]),
        "final_initial_action_label": "low" if policy[mdp.initial_state] == LOW else "high",
        "max_frozen_q_table_error": max_q_error,
    }


def main() -> None:
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    calibrated = next(arm for arm in frozen["sweep"] if arm["memory"] == 7)
    jobs = [
        (int(row["seed"]), row["primitive_q"]["q_table"])
        for row in calibrated["rows"]
    ]
    with ProcessPoolExecutor(max_workers=4) as executor:
        rows = list(executor.map(_trace_seed, jobs))
    rows.sort(key=lambda row: row["seed"])
    failed = [row for row in rows if row["final_initial_action_label"] == "high"]
    summary = {
        "study": "esim6-late-credit-descriptive-audit",
        "source_run": "93265b9b03",
        "memory": 7,
        "train_transitions": 300000,
        "readiness_checkpoints": list(CHECKPOINTS),
        "seeds": len(rows),
        "frozen_q_tables_reproduced": all(row["max_frozen_q_table_error"] <= 1e-12 for row in rows),
        "first_all_low_transition_range": [
            min(row["first_all_low_transition"] for row in rows),
            max(row["first_all_low_transition"] for row in rows),
        ],
        "failed_initial_policies": len(failed),
        "failed_with_any_depth_5_visit_after_100k": sum(
            row["deepest_depth_after_100k"] >= 5 for row in failed
        ),
        "failed_with_any_all_low_transition_after_100k": sum(
            row["all_low_transitions_after_100k"] > 0 for row in failed
        ),
        "rows": rows,
        "claim_boundary": (
            "Post-hoc visitation audit of a frozen controlled simulation. "
            "It distinguishes early state discovery from late Bellman-credit "
            "support but is not a preregistered effect test or live-market result."
        ),
    }
    OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
