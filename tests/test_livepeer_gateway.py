import pytest

from orcap.capture_livepeer import _count_expression, _regions, _vector_counts, gateway_metric_rows


def _vector(values):
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"region": region}, "value": ["1", str(value)]}
                for region, value in values.items()
            ],
        },
    }


def test_livepeer_logql_expression_is_aggregate_by_region_and_bounded_window():
    expression = _count_expression('|= "Swapping Orchestrator"', 5)
    assert expression.startswith("sum by (region) (count_over_time")
    assert "[5m]" in expression
    assert "manifest" not in expression.lower()
    assert "session" not in expression.lower()


def test_livepeer_aggregate_rows_preserve_zeroes_without_collecting_stream_ids():
    rows = gateway_metric_rows(
        ["fra", "nyc"],
        {
            "swap_events": _vector({"fra": 3, "nyc": 4}),
            "reuse_events": _vector({"fra": 10, "nyc": 8}),
            "inflight_reuse_events": _vector({"fra": 7, "nyc": 50}),
        },
        "20260710T000000Z",
        "2026-07-10",
        5,
    )
    fra, nyc = rows
    assert fra["decision_events"] == 13
    assert fra["inflight_reuse_events"] == 7
    assert nyc["inflight_reuse_events"] == 8
    assert "session" not in fra["record_json"]
    assert "orchestrator identity" in fra["metric_definition"]


def test_livepeer_vector_rejects_non_success_response():
    with pytest.raises(ValueError, match="status=success"):
        _vector_counts({"status": "error"})


def test_livepeer_region_parser_accepts_only_successful_public_labels():
    assert _regions({"status": "success", "data": ["nyc", "fra", "nyc"]}) == ["fra", "nyc"]
    assert _regions({"status": "error", "data": ["fra"]}) == []
