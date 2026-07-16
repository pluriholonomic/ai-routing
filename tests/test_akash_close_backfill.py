import pandas as pd

from orcap import backfill_akash_close_events as backfill


class _Relation:
    def __init__(self, frame):
        self.frame = frame

    def df(self):
        return self.frame.copy()


def test_missing_close_blocks_is_deterministic_bounded_and_skips_existing(monkeypatch):
    leases = pd.DataFrame(
        [
            {"execution_id": "lease-a", "event_block_height": 10},
            {"execution_id": "lease-b", "event_block_height": 10},
            {"execution_id": "lease-c", "event_block_height": 11},
        ]
    )
    existing = pd.DataFrame([{"execution_id": "lease-a"}])

    monkeypatch.setattr(backfill.data, "table_glob", lambda name: name)

    def query(sql):
        return _Relation(existing if "distinct execution_id" in sql else leases)

    monkeypatch.setattr(backfill.data, "q", query)

    assert backfill.missing_close_blocks(1) == {10: {"lease-b"}}
    assert backfill.missing_close_blocks(2) == {
        10: {"lease-b"},
        11: {"lease-c"},
    }
