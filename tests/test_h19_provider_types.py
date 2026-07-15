import numpy as np
import pandas as pd

from orcap.analysis.h19_provider_types import CLUSTER_FEATURES, cluster


def test_provider_clustering_tolerates_all_missing_live_feature():
    rng = np.random.default_rng(7)
    rows = 12
    frame = pd.DataFrame(
        rng.normal(size=(rows, len(CLUSTER_FEATURES))), columns=CLUSTER_FEATURES
    )
    frame["provider"] = [f"provider-{i}" for i in range(rows)]
    frame["tool_err"] = np.nan

    typed, summary = cluster(frame)

    assert len(typed) == rows
    assert typed["cluster"].notna().all()
    assert summary["n_providers"] == rows
