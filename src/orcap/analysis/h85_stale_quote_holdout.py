"""H85 wrapper for the future-only stale-quote capacity holdout."""

from pathlib import Path
from typing import Any

from .common import DEFAULT_OUT
from .h82_enforcement_substitution import load_rows
from .h84_stale_quote_hazard import analyze_future


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    return analyze_future(load_rows(), out_dir)
