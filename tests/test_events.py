from orcap.capture_api import diff_models


def test_diff_detects_change_and_skips_variants():
    prev = {
        ("m/a", "P", "t", "f1"): 1.0,
        ("m/b", "P", "t", "f1"): 2.0,
        ("m/a:free", "P", "t", "f1"): 0.0,
    }
    cur = {
        ("m/a", "P", "t", "f1"): 1.5,  # changed
        ("m/b", "P", "t", "f1"): 2.0,  # unchanged
        ("m/a:free", "P", "t", "f1"): 9.9,  # variant — ignored
        ("m/c", "P", "t", "f1"): 3.0,  # new endpoint — not a price change
    }
    assert diff_models(prev, cur) == {"m/a"}
    assert diff_models({}, cur) == set()
