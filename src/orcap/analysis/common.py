"""Shared helpers for hypothesis modules."""

import json
from pathlib import Path

import pandas as pd

DEFAULT_OUT = Path("analysis")


def save(df: pd.DataFrame, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{name}.parquet"
    df.to_parquet(p, index=False)
    return p


def save_json(obj: dict, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{name}.json"
    p.write_text(json.dumps(obj, indent=2, default=str))
    return p
