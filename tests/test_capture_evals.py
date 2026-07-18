from orcap.capture_evals import _normalize, battery, daily_items, extract_answer


def test_battery_loads_and_versioned():
    b = battery()
    assert b["version"].startswith("v1-")
    ids = [p["id"] for p in b["prompts"]]
    assert len(ids) == len(set(ids)) == 12


def test_daily_items_deterministic_and_rotating():
    a = daily_items("2026-07-18")
    b = daily_items("2026-07-18")
    c = daily_items("2026-07-19")
    assert [r["item_id"] for r in a] == [r["item_id"] for r in b]
    assert [r["item_id"] for r in a] != [r["item_id"] for r in c]
    assert sum(r["source"] == "mmlu" for r in a) == 16
    assert sum(r["source"] == "gsm8k" for r in a) == 4


def test_extract_answer_letter():
    assert extract_answer("The answer is B.", "letter") == "B"
    assert extract_answer("b", "letter") == "B"
    assert extract_answer("I cannot decide", "letter") is None


def test_extract_answer_number():
    assert extract_answer("... so\n#### 1,250", "number") == "1250"
    assert extract_answer("the total is 42 dollars", "number") == "42"
    assert extract_answer("no digits here", "number") is None


def test_normalize():
    assert _normalize("  A  B\nc ") == "a b c"
