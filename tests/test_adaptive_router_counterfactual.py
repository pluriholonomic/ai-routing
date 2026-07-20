from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from orcap.analysis.adaptive_router_counterfactual import run_analysis


def _write_panel(root: Path) -> None:
    for day in range(1, 6):
        dt = f"2026-07-{day:02d}"
        rows = []
        for provider, prompt, completion, uptime in (
            ("A", 1.0e-6, 2.0e-6, 99.0),
            ("B", 1.2e-6, 2.1e-6, 99.8),
            ("C", 1.5e-6, 2.4e-6, 98.0),
        ):
            rows.append(
                {
                    "run_ts": f"202607{day:02d}T120000Z",
                    "dt": dt,
                    "model_id": "example/model",
                    "provider_name": provider,
                    "tag": provider.lower(),
                    "status": 0,
                    "price_prompt": prompt * (1 + day / 100),
                    "price_completion": completion * (1 + day / 100),
                    "uptime_last_30m": uptime,
                }
            )
        directory = root / "curated" / "endpoints_snapshots" / f"dt={dt}"
        directory.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows), directory / "part-0.parquet")


def test_temporal_counterfactual_writes_holdout_outputs_and_claim_boundary(tmp_path):
    _write_panel(tmp_path)
    out = tmp_path / "analysis"
    summary = run_analysis(
        data_root=tmp_path, out_dir=out, bootstrap_draws=20
    )
    assert summary["status"] == "complete"
    assert summary["welfare_identified"] is False
    assert summary["source_dates"] == 5
    assert (out / "adaptive-router-frontier.png").is_file()
    assert (out / "adaptive-router-daily-effects.pdf").is_file()
    stored = json.loads((out / "adaptive-router-summary.json").read_text())
    assert "provider behavior fixed" in stored["claim_boundary"]
