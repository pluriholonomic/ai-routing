from datetime import UTC, datetime

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from orcap.capture_price_events import build_event_bundle, write_event_bundle
from orcap.price_experiments import validate_manifest


class FakeResponse:
    status_code = 200

    def __init__(self, model):
        self.model = model

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "data": {
                "endpoints": [
                    {
                        "provider_name": provider,
                        "tag": f"tag-{provider}",
                        "name": f"endpoint-{provider}",
                        "pricing": {"prompt": str(price), "completion": str(price)},
                        "context_length": 8_192,
                        "max_completion_tokens": 1_024,
                        "supported_parameters": [],
                    }
                    for provider, price in (("a", 1e-6), ("b", 2e-6), ("c", 3e-6))
                ]
            }
        }


class FakeClient:
    def get(self, url):
        return FakeResponse(url)


def _write_snapshots(root):
    rows = []
    for run_ts, prices in (
        ("20260718T235500Z", {"a": 2e-6, "b": 2.2e-6, "c": 3e-6}),
        ("20260719T000000Z", {"a": 1e-6, "b": 2.2e-6, "c": 3e-6}),
    ):
        for provider, price in prices.items():
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": "2026-07-19",
                    "model_id": "author/model",
                    "provider_name": provider,
                    "tag": f"tag-{provider}",
                    "price_prompt": price,
                    "price_completion": price,
                }
            )
    path = root / "curated/endpoints_snapshots/dt=2026-07-19/snapshots.parquet"
    path.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(rows), preserve_index=False), path)


def test_event_bundle_freezes_due_w0_assignments_and_round_trips(tmp_path):
    _write_snapshots(tmp_path)
    bundle = build_event_bundle(
        FakeClient(),
        data_root=tmp_path,
        run_id="20260719T000500Z",
        seed=71,
        now=datetime(2026, 7, 19, 0, 5, tzinfo=UTC),
    )
    assert bundle["summary"]["source_healthy"] is True
    assert bundle["summary"]["new_events"] >= 1
    assert bundle["summary"]["planned_tasks"] >= 6
    assert {row["wave_id"] for row in bundle["assignments"]} == {"w0"}
    validate_manifest(
        bundle["manifest"], bundle["candidates"], bundle["assignments"], bundle["summary"]
    )
    paths = write_event_bundle(
        bundle,
        bundle_path=tmp_path / "price-event-plan.json",
        curated_dir=tmp_path / "curated",
    )
    assert all(value for value in paths.values())
    assert not any("messages" in row for row in bundle["assignments"])


def test_stale_source_registers_no_paid_plan(tmp_path):
    _write_snapshots(tmp_path)
    bundle = build_event_bundle(
        FakeClient(),
        data_root=tmp_path,
        run_id="20260719T020000Z",
        seed=71,
        now=datetime(2026, 7, 19, 2, 0, tzinfo=UTC),
    )
    assert bundle["summary"]["source_healthy"] is False
    assert bundle["summary"]["planned_tasks"] == 0
