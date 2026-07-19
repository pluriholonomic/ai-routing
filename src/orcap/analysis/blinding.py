"""Cross-analysis isolation for power-gated prospective routing studies."""

from __future__ import annotations

import pandas as pd

OUTCOME_BLINDED_STUDY_IDS = frozenset(
    {
        "openrouter-routing-crossover-v2",
        "openrouter-fallback-selection-decomposition-v1",
        "openrouter-delegation-replication-v1",
        "openrouter-capacity-policy-v1",
        "openrouter-enforcement-policy-v1",
        "huggingface-policy-frontier-v1",
    }
)


def exclude_outcome_blinded(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove rows whose outcomes may only be released by dedicated analyzers."""
    if frame.empty or "study_id" not in frame:
        return frame.copy(), 0
    masked = frame["study_id"].astype("string").isin(OUTCOME_BLINDED_STUDY_IDS)
    return frame.loc[~masked].copy(), int(masked.sum())


def sql_outcome_blind_filter(column: str = "study_id") -> str:
    """Return the DuckDB predicate used to isolate gated study outcomes.

    ``column`` is supplied only by analysis code, never by data or a caller.  A
    shared predicate keeps SQL-only coverage summaries under the same blinding
    contract as the pandas analyzers.
    """
    study_ids = ", ".join(
        f"'{study_id.replace(chr(39), chr(39) * 2)}'"
        for study_id in sorted(OUTCOME_BLINDED_STUDY_IDS)
    )
    return f"coalesce(cast({column} as varchar), '') not in ({study_ids})"
