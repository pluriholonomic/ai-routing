import numpy as np
import pandas as pd

from orcap.analysis.h19_provider_types import CLUSTER_FEATURES
from orcap.analysis.h19_text import _provider_homepage_frame, combined_cluster


def test_provider_homepage_frame_handles_unavailable_directory() -> None:
    frame = _provider_homepage_frame(None)

    assert frame.empty
    assert frame.columns.tolist() == [
        "slug",
        "provider",
        "homepage",
        "pricing_strategy",
        "byok_enabled",
    ]


def test_provider_homepage_frame_extracts_favicon_target() -> None:
    frame = _provider_homepage_frame(
        {
            "data": [
                {
                    "slug": "example",
                    "displayName": "Example",
                    "icon": {"url": "https://favicon.test/?url=https%3A%2F%2Fexample.com"},
                    "pricingStrategy": "cost_based",
                    "byokEnabled": True,
                }
            ]
        }
    )

    assert frame.to_dict("records") == [
        {
            "slug": "example",
            "provider": "Example",
            "homepage": "https://example.com",
            "pricing_strategy": "cost_based",
            "byok_enabled": True,
        }
    ]


def test_combined_cluster_tolerates_all_missing_behavior_feature() -> None:
    rng = np.random.default_rng(11)
    rows = 12
    behavior = pd.DataFrame(
        rng.normal(size=(rows, len(CLUSTER_FEATURES))), columns=CLUSTER_FEATURES
    )
    behavior["provider"] = [f"provider-{i}" for i in range(rows)]
    behavior["tool_err"] = np.nan
    text = pd.DataFrame(
        {
            "provider": behavior["provider"],
            "kw_capacity": rng.integers(0, 2, size=rows),
            "txt_0": rng.normal(size=rows),
            "txt_1": rng.normal(size=rows),
        }
    )

    typed, summary = combined_cluster(behavior, text)

    assert len(typed) == rows
    assert typed["cluster_combined"].notna().all()
    assert summary["n_providers"] == rows
