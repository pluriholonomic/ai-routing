"""Shared population rules for paid-market analyses.

OpenRouter exposes subsidized ``:free`` variants alongside paid model IDs.
Those variants are economically useful for demand-creation analyses, but they
do not belong in inference-provider pricing, competition, or pass-through
estimates.  Keep the exclusion explicit and narrow: a colon by itself does not
make a model free because paid routing variants can also use colon suffixes.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

FREE_MODEL_IDS = frozenset({"openrouter/free"})
_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def is_free_model_id(value: Any) -> bool:
    """Return whether a public model identifier denotes a free-only route."""

    if value is None or pd.isna(value):
        return False
    model_id = str(value).strip().casefold()
    return model_id in FREE_MODEL_IDS or model_id.endswith(":free")


def paid_model_mask(values: pd.Series) -> pd.Series:
    """Boolean mask for identified model IDs outside the free-only surface."""

    normalized = values.astype("string").str.strip().str.casefold()
    return (
        normalized.notna()
        & normalized.ne("")
        & ~normalized.isin(FREE_MODEL_IDS)
        & ~normalized.str.endswith(":free", na=False)
    )


def paid_activity_mask(
    frame: pd.DataFrame,
    *,
    model_column: str = "model_permaslug",
    variant_column: str = "variant",
) -> pd.Series:
    """Exclude rows labelled free either by variant or by model identifier."""

    if model_column not in frame:
        raise KeyError(model_column)
    mask = paid_model_mask(frame[model_column])
    if variant_column in frame:
        variant = frame[variant_column].astype("string").str.strip().str.casefold()
        mask &= variant.ne("free").fillna(True)
    return mask


def paid_model_sql(column: str) -> str:
    """DuckDB predicate matching :func:`paid_model_mask` for a safe identifier."""

    if not _SQL_IDENTIFIER.fullmatch(column):
        raise ValueError(f"unsafe SQL identifier: {column!r}")
    normalized = f"lower(trim(cast({column} as varchar)))"
    return (
        f"({column} is not null and trim(cast({column} as varchar)) <> '' "
        f"and {normalized} <> 'openrouter/free' "
        f"and {normalized} not like '%:free')"
    )


def paid_activity_sql(model_column: str, variant_column: str = "variant") -> str:
    """DuckDB predicate for paid activity rows, including paid variants."""

    if not _SQL_IDENTIFIER.fullmatch(variant_column):
        raise ValueError(f"unsafe SQL identifier: {variant_column!r}")
    return (
        f"({paid_model_sql(model_column)} and "
        f"coalesce(lower(trim(cast({variant_column} as varchar))), '') <> 'free')"
    )
