import json

import pandas as pd

from orcap.analysis.h58_nosana_node_registry import (
    complete_registry_snapshot_manifests,
    coverage_gate,
    registry_panel,
)


def _detail(*, complete=True, fetched=2, written=2):
    return json.dumps(
        {
            "query_succeeded": True,
            "registry_complete": complete,
            "account_records_fetched": fetched,
            "rows_written": {"nosana_node_registry": written},
        }
    )


def test_h58_requires_a_source_run_with_matching_raw_and_parsed_counts():
    source_runs = pd.DataFrame(
        [
            {
                "run_ts": "good",
                "dt": "2026-07-10",
                "source": "nosana",
                "status": "success",
                "detail_json": _detail(),
            },
            {
                "run_ts": "bad",
                "dt": "2026-07-10",
                "source": "nosana",
                "status": "success",
                "detail_json": _detail(complete=False),
            },
        ]
    )
    manifests = complete_registry_snapshot_manifests(source_runs)
    assert manifests == {("good", "2026-07-10"): 2}
    nodes = pd.DataFrame(
        [
            {
                "run_ts": "good",
                "dt": "2026-07-10",
                "snapshot_slot": 7,
                "participant_id": "a",
                "audited": True,
                "architecture_type": 1,
                "country_code": 840,
                "declared_cpu_cores": 8,
                "declared_gpu_value": 4,
                "declared_memory_gb": 32,
                "declared_iops": 500,
                "declared_storage_gb": 200,
            },
            {
                "run_ts": "good",
                "dt": "2026-07-10",
                "snapshot_slot": 7,
                "participant_id": "b",
                "audited": False,
                "architecture_type": 2,
                "country_code": 840,
                "declared_cpu_cores": 16,
                "declared_gpu_value": 4,
                "declared_memory_gb": 64,
                "declared_iops": 1_000,
                "declared_storage_gb": 500,
            },
            {
                "run_ts": "bad",
                "dt": "2026-07-10",
                "snapshot_slot": 8,
                "participant_id": "ignored",
            },
        ]
    )
    panel = registry_panel(nodes, manifests)
    values = panel.set_index("metric")["value"].to_dict()
    assert values["registered_node_count"] == 2
    assert values["audited_node_share"] == 0.5
    assert values["sum_declared_cpu_cores"] == 24.0
    assert values["distinct_declared_gpu_values"] == 1
    assert coverage_gate(panel)["status"] == "power_gated"

    source_runs["dt"] = pd.to_datetime(source_runs["dt"])
    nodes["dt"] = pd.to_datetime(nodes["dt"])
    reloaded_panel = registry_panel(nodes, complete_registry_snapshot_manifests(source_runs))
    assert not reloaded_panel.empty


def test_h58_rejects_a_snapshot_when_node_ids_are_not_unique():
    nodes = pd.DataFrame(
        [
            {"run_ts": "run", "dt": "2026-07-10", "participant_id": "duplicate"},
            {"run_ts": "run", "dt": "2026-07-10", "participant_id": "duplicate"},
        ]
    )
    assert registry_panel(nodes, {("run", "2026-07-10"): 2}).empty
