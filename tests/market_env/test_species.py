import numpy as np

from orcap.market_env.strategies_species import (
    ActiveUndercutterStrategy,
    AdopterStrategy,
    TargetHazardStrategy,
    species_strategy,
)
from orcap.market_env.types import ProviderSpec

SPEC = ProviderSpec(provider="Me", marginal_cost=0.2, physical_capacity=100)
SPECIES = {
    "adopter": {"changes_per_day": 0.03, "margin_log_median": 0.0},
    "below_static": {"changes_per_day": 0.0, "margin_log_median": -0.4},
    "below_active": {"changes_per_day": 1.1, "margin_log_median": -0.44},
    "above": {"changes_per_day": 0.02, "margin_log_median": 0.34},
}


def test_adopter_tracks_anchor_same_epoch():
    s = AdopterStrategy("AuthorCo", idio_hazard=0.0)
    assert s.act(SPEC, {"AuthorCo": 1.0, "Me": 0.9}).quote == 1.0
    assert s.act(SPEC, {"AuthorCo": 0.8, "Me": 1.0}).quote == 0.8


def test_static_undercutter_rigid_between_hazard_draws():
    s = TargetHazardStrategy("AuthorCo", margin_log=-0.4, hazard=0.0, seed=1)
    p1 = s.act(SPEC, {"AuthorCo": 1.0, "Rival": 0.5}).quote
    assert abs(p1 - np.exp(-0.4)) < 1e-9
    # rival cut does NOT trigger a move (rigidity)
    p2 = s.act(SPEC, {"AuthorCo": 1.0, "Rival": 0.3}).quote
    assert p2 == p1
    # anchor move DOES re-target
    p3 = s.act(SPEC, {"AuthorCo": 0.5, "Rival": 0.3}).quote
    assert abs(p3 - 0.5 * np.exp(-0.4)) < 1e-9


def test_same_seed_reproduces_trajectory():
    def run(seed):
        s = AdopterStrategy("AuthorCo", idio_hazard=0.5, seed=seed)
        return [s.act(SPEC, {"AuthorCo": 1.0}).quote for _ in range(50)]

    assert run(7) == run(7)
    assert run(7) != run(8)


def test_active_undercutter_one_tick_below_with_floor():
    s = ActiveUndercutterStrategy(margin_floor=0.1, tick_frac=0.01)
    q = s.act(SPEC, {"AuthorCo": 1.0, "Rival": 0.5, "Me": 0.9}).quote
    assert abs(q - 0.5 * 0.99) < 1e-9
    # floor binds when rivals go below cost*(1.1)
    q2 = s.act(SPEC, {"Rival": 0.1, "Me": 0.9}).quote
    assert abs(q2 - 0.2 * 1.1) < 1e-9


def test_factory_builds_all_species():
    for cls in SPECIES:
        s = species_strategy(cls, SPECIES, "AuthorCo", seed=3)
        a = s.act(SPEC, {"AuthorCo": 1.0, "Rival": 0.7, "Me": 0.9})
        assert a.quote > 0
