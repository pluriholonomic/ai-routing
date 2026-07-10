import numpy as np
import pandas as pd
import pytest

from orcap.cow_history import (
    MAX_WINDOW_DAYS,
    bq_rows_to_rpc_logs,
    cow_log_query,
    normalize,
    query_fingerprint,
    validate_window,
)

TRADE_TOPIC = "0xa07a543ab8a018198e99ca0184c93fe9050a79400a0a723441f84de1d972cc17"
SETTLEMENT_TOPIC = "0x40338ce1a7c49204f0099533b1e9a7ee0a3d261f84974ab7af36105b8c4e9db4"
OWNER = "0000000000000000000000001111111111111111111111111111111111111111"
SOLVER = "0000000000000000000000002222222222222222222222222222222222222222"
USDC = "000000000000000000000000a0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH = "000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"


def _word(value: int) -> str:
    return f"{value:064x}"


def _trade_data() -> str:
    # word 5 points to a 56-byte order UID; exact contents are only decoder input.
    return "0x" + "".join(
        [
            _word(int(USDC, 16)),
            _word(int(WETH, 16)),
            _word(2_000_000),
            _word(10**18),
            _word(0),
            _word(192),
            _word(56),
            "ab" * 56 + "00" * 8,
        ]
    )


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "block_timestamp": "2026-07-01T00:00:01Z",
                "block_number": 100,
                "block_hash": "0xabc",
                "transaction_hash": "0xtx",
                "log_index": 2,
                "data": _trade_data(),
                "topics": [TRADE_TOPIC, "0x" + OWNER],
            },
            {
                "block_timestamp": "2026-07-01T00:00:01Z",
                "block_number": 100,
                "block_hash": "0xabc",
                "transaction_hash": "0xtx",
                "log_index": 3,
                "data": "0x",
                "topics": [SETTLEMENT_TOPIC, "0x" + SOLVER],
            },
        ]
    )


def test_validate_window_is_explicit_end_exclusive_and_bounded():
    start, end = validate_window("2026-07-01", "2026-07-02")
    assert start.isoformat() == "2026-07-01"
    assert end.isoformat() == "2026-07-02"
    with pytest.raises(ValueError, match="after start"):
        validate_window("2026-07-01", "2026-07-01")
    with pytest.raises(ValueError, match="maximum"):
        validate_window("2026-07-01", f"2026-07-{MAX_WINDOW_DAYS + 2:02d}")


def test_query_is_partition_bounded_and_fingerprinted():
    query = cow_log_query()
    assert "block_timestamp >= TIMESTAMP(@start)" in query
    assert "topics[SAFE_OFFSET(0)] IN UNNEST(@event_topics)" in query
    assert len(query_fingerprint()) == 64


def test_bigquery_rows_reuse_canonical_trade_decoder_and_relabel_provenance():
    frame = _frame()
    frame["topics"] = frame["topics"].map(np.array)
    logs, times = bq_rows_to_rpc_logs(frame)
    assert logs[0]["logIndex"] == "0x2"
    assert times == {100: "2026-07-01T00:00:01Z"}
    executions, events = normalize(frame, captured_at="20260710T000000Z")
    assert len(executions) == 1
    assert len(events) == 2
    row = executions.iloc[0]
    assert row["dt"] == "2026-07-01"
    assert row["side"] == "usdc_to_weth"
    assert row["solver_id"] == "0x2222222222222222222222222222222222222222"
    assert "public-bigquery" in row["quality_tier"]
