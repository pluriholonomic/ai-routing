import httpx
import pytest

import orcap.hf_snapshot_retry as retry


def test_file_exists_retry_recovers_from_read_timeout():
    calls = 0
    sleeps = []

    class FakeApi:
        def file_exists(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise httpx.ReadTimeout("Hub HEAD timed out")
            assert args == ("owner/repo", "path/file.parquet")
            assert kwargs == {"repo_type": "dataset"}
            return True

    assert retry.file_exists_retry(
        FakeApi(),
        "owner/repo",
        "path/file.parquet",
        repo_type="dataset",
        sleep=sleeps.append,
    )
    assert calls == 3
    assert sleeps == [1, 2]


def test_file_exists_retry_fails_closed_after_bounded_attempts():
    class FakeApi:
        def file_exists(self, *args, **kwargs):
            raise OSError("Hub unavailable")

    with pytest.raises(OSError, match="Hub unavailable"):
        retry.file_exists_retry(FakeApi(), "owner/repo", "path", attempts=2, sleep=lambda _: None)


def test_file_exists_retry_preserves_confirmed_absence():
    class FakeApi:
        def file_exists(self, *args, **kwargs):
            return False

    assert retry.file_exists_retry(FakeApi(), "owner/repo", "path") is False


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
