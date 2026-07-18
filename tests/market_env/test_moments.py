import numpy as np
import pandas as pd

from orcap.market_env.moments import calvano_delta, compute_moments, moment_distance


def synth_traj() -> pd.DataFrame:
    rows = []
    for e in range(10):
        for prov, cls, price, rep in [
            ("AuthorCo", "author", 1.0, False),
            ("CopyCo", "adopter", 1.0, False),
            ("CheapCo", "below_static", 0.667, False),
            ("JitterCo", "below_active", 0.6 + 0.01 * (e % 2), e > 0),
            ("PremiumCo", "above", 1.4, False),
        ]:
            rows.append(dict(
                epoch=e, model_id="m/x", provider_name=prov, price=price,
                is_author=prov == "AuthorCo", anchor_class=cls, anchor_price=1.0,
                repriced=rep and e > 0,
                flow_share={"AuthorCo": .3, "CopyCo": .2, "CheapCo": .25,
                            "JitterCo": .15, "PremiumCo": .1}[prov],
                profit=1.0,
            ))
    return pd.DataFrame(rows)


def test_compute_moments_hand_checked():
    m = compute_moments(synth_traj())
    assert abs(m["dispersion_max_min_ratio"] - 1.4 / 0.6) < 0.02
    assert m["adopter_atom_share"] == 1.0
    assert abs(m["premium_ladder_below_static"] - np.log(0.667)) < 1e-6
    assert abs(m["premium_ladder_above"] - np.log(1.4)) < 1e-6
    assert m["cadence_adopter"] == 0.0
    assert m["cadence_below_active"] > 0.5


def test_moment_distance_perfect_match_is_zero():
    m = compute_moments(synth_traj())
    targets = {k: (v, 1.0) for k, v in m.items() if v is not None}
    d = moment_distance(m, targets)
    assert d["distance"] == 0.0


def test_moment_distance_scores_deviation():
    m = compute_moments(synth_traj())
    targets = {"dispersion_max_min_ratio": (m["dispersion_max_min_ratio"] * 2, 1.0)}
    d = moment_distance(m, targets)
    assert d["distance"] > 0.2


def test_calvano_delta():
    assert calvano_delta(1.0, 1.0, 2.0) == 0.0
    assert calvano_delta(2.0, 1.0, 2.0) == 1.0
    assert calvano_delta(1.0, 1.0, 1.0) is None
