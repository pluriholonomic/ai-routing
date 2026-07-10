import pytest

from orcap.capture_livepeer_history import gateway_history_rows, range_counts


def _matrix(values):
    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {"metric": {"region": region}, "values": samples}
                for region, samples in values.items()
            ],
        },
    }


def test_livepeer_range_parser_accepts_aggregate_matrix_points_only():
    counts = range_counts(_matrix({"fra": [["100", "2"]], "nyc": [[100, "4"]]}))

    assert counts == {(100, "fra"): 2, (100, "nyc"): 4}


def test_livepeer_history_rows_zero_fill_aggregate_metrics_without_identities():
    rows = gateway_history_rows(
        ["fra", "nyc"],
        {
            "swap_events": _matrix({"fra": [[100, "2"]], "nyc": [[100, "4"]]}),
            "reuse_events": _matrix({"fra": [[100, "8"]], "nyc": [[100, "6"]]}),
            "inflight_reuse_events": _matrix({"fra": [[100, "99"]]}),
        },
        "20260710T000000Z",
        "2026-07-10",
        5,
    )

    fra, nyc = rows
    assert fra["source_observed_at"] == "1970-01-01T00:01:40+00:00"
    assert fra["decision_events"] == 10
    assert fra["inflight_reuse_events"] == 8
    assert nyc["inflight_reuse_events"] == 0
    assert "manifest" not in fra["record_json"]


def test_livepeer_range_parser_rejects_non_matrix_and_duplicate_samples():
    with pytest.raises(ValueError, match="matrix"):
        range_counts({"status": "success", "data": {"resultType": "vector"}})
    with pytest.raises(ValueError, match="duplicate"):
        range_counts(_matrix({"fra": [[100, "1"], [100, "2"]]}))
