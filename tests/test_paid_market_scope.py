from __future__ import annotations

import pandas as pd

from orcap.analysis.paid_market_scope import activity_scope_panel


def test_activity_scope_panel_separates_free_without_discarding_paid_variants():
    activity = pd.DataFrame(
        [
            {
                "day": "2026-07-01",
                "model_permaslug": "vendor/model",
                "variant": "standard",
                "tokens": 70,
                "requests": 7,
            },
            {
                "day": "2026-07-01",
                "model_permaslug": "vendor/model",
                "variant": "nitro",
                "tokens": 20,
                "requests": 2,
            },
            {
                "day": "2026-07-01",
                "model_permaslug": "vendor/model",
                "variant": "free",
                "tokens": 10,
                "requests": 1,
            },
            {
                "day": "2026-07-02",
                "model_permaslug": "vendor/other:free",
                "variant": "standard",
                "tokens": 5,
                "requests": 1,
            },
            {
                "day": "2026-07-02",
                "model_permaslug": None,
                "variant": None,
                "tokens": 2,
                "requests": 1,
            },
        ]
    )

    panel = activity_scope_panel(activity).set_index("day")
    assert panel.loc["2026-07-01", "paid_tokens"] == 90
    assert panel.loc["2026-07-01", "free_tokens"] == 10
    assert panel.loc["2026-07-01", "free_token_share"] == 0.1
    assert panel.loc["2026-07-02", "paid_tokens"] == 0
    assert panel.loc["2026-07-02", "free_tokens"] == 5
    assert panel.loc["2026-07-02", "unclassified_tokens"] == 2
