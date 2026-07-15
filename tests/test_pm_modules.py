import numpy as np
import pandas as pd

from orcap.analysis.pm6_event_reclassification import classify


def _ch(rows):
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["is_cut"] = df["n"] < df["o"]
    return df.sort_values("ts")


END = pd.Timestamp("2026-02-01", tz="UTC")


def test_classify_punish_and_revert_requires_initiator_persistence():
    ch = _ch([
        {"ts": "2026-01-01", "model_id": "m", "provider_name": "i", "o": 2.0, "n": 1.5},
        {"ts": "2026-01-02", "model_id": "m", "provider_name": "r", "o": 2.0, "n": 1.6},
        {"ts": "2026-01-04", "model_id": "m", "provider_name": "r", "o": 1.6, "n": 2.0},
    ])
    assert classify(ch.iloc[0], ch, END) == "punish_and_revert"


def test_classify_cut_withdrawn_when_initiator_reverts_first():
    ch = _ch([
        {"ts": "2026-01-01", "model_id": "m", "provider_name": "i", "o": 2.0, "n": 1.5},
        {"ts": "2026-01-02", "model_id": "m", "provider_name": "r", "o": 2.0, "n": 1.6},
        {"ts": "2026-01-03", "model_id": "m", "provider_name": "i", "o": 1.5, "n": 2.0},
        {"ts": "2026-01-04", "model_id": "m", "provider_name": "r", "o": 1.6, "n": 2.0},
    ])
    assert classify(ch.iloc[0], ch, END) == "cut_withdrawn"


def test_classify_failed_and_followed_leadership():
    lonely = _ch([
        {"ts": "2026-01-01", "model_id": "m", "provider_name": "i", "o": 1.5, "n": 2.0},
        {"ts": "2026-01-02", "model_id": "m", "provider_name": "i", "o": 2.0, "n": 1.5},
    ])
    assert classify(lonely.iloc[0], lonely, END) == "failed_leadership"
    followed = _ch([
        {"ts": "2026-01-01", "model_id": "m", "provider_name": "i", "o": 1.5, "n": 2.0},
        {"ts": "2026-01-02", "model_id": "m", "provider_name": "r", "o": 1.5, "n": 2.0},
    ])
    assert classify(followed.iloc[0], followed, END) == "followed_leadership"


def test_classify_reoptimize_cut_matched_and_held():
    ch = _ch([
        {"ts": "2026-01-01", "model_id": "m", "provider_name": "i", "o": 2.0, "n": 1.5},
        {"ts": "2026-01-02", "model_id": "m", "provider_name": "r", "o": 2.0, "n": 1.5},
    ])
    assert classify(ch.iloc[0], ch, END) == "reoptimize"
