import pytest

import orcap.hf_snapshot_retry as retry


def test_snapshot_download_retry_recovers_without_discarding_arguments(monkeypatch):
    calls = []
    sleeps = []

    def fake_download(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) < 3:
            raise OSError("transient CAS failure")
        return "/cache/snapshot"

    monkeypatch.setattr(retry, "_snapshot_download", fake_download)
    result = retry.snapshot_download_retry(
        "owner/repo",
        repo_type="dataset",
        allow_patterns=["curated/*"],
        sleep=sleeps.append,
    )

    assert result == "/cache/snapshot"
    assert len(calls) == 3
    assert all(call[0] == ("owner/repo",) for call in calls)
    assert all(call[1]["allow_patterns"] == ["curated/*"] for call in calls)
    assert sleeps == [1, 2]


def test_snapshot_download_retry_raises_after_bounded_attempts(monkeypatch):
    calls = 0

    def fake_download(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise OSError("still unavailable")

    monkeypatch.setattr(retry, "_snapshot_download", fake_download)
    with pytest.raises(OSError, match="still unavailable"):
        retry.snapshot_download_retry(
            "owner/repo",
            attempts=2,
            sleep=lambda _: None,
        )
    assert calls == 2


def test_snapshot_download_retry_rejects_nonpositive_attempts():
    with pytest.raises(ValueError, match="positive"):
        retry.snapshot_download_retry("owner/repo", attempts=0)
