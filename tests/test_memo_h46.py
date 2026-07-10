import pandas as pd

from orcap.memo import _h46_trajectory_html


def test_memo_renders_recent_h46_rolling_elasticity_trajectory(tmp_path):
    pd.DataFrame(
        [
            {
                "window_end": "2026-07-20",
                "share_price_elasticity": -1.2,
                "std_error": 0.1,
                "n_groups": 40,
            },
            {
                "window_end": "2026-07-21",
                "share_price_elasticity": -1.3,
                "std_error": 0.2,
                "n_groups": 45,
            },
        ]
    ).to_parquet(tmp_path / "h46_rolling_routing_elasticity.parquet", index=False)
    rendered = _h46_trajectory_html(tmp_path)
    assert "H46 rolling routing elasticity" in rendered
    assert "2026-07-20" in rendered
    assert "-1.30" in rendered
