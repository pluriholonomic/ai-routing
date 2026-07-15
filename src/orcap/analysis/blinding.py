"""Cross-analysis isolation for power-gated prospective routing studies."""

from __future__ import annotations

import pandas as pd

OUTCOME_BLINDED_STUDY_IDS = frozenset(
    {
        "openrouter-routing-crossover-v2",
        "openrouter-fallback-selection-decomposition-v1",
    }
)


def exclude_outcome_blinded(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove rows whose outcomes may only be released by dedicated analyzers."""
    if frame.empty or "study_id" not in frame:
        return frame.copy(), 0
    masked = frame["study_id"].astype("string").isin(OUTCOME_BLINDED_STUDY_IDS)
    return frame.loc[~masked].copy(), int(masked.sum())
