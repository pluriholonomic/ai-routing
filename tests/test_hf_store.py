from pathlib import Path

import orcap.hf_store as hf_store


def test_get_api_uses_cached_identity_check(monkeypatch):
    calls = []

    class FakeApi:
        def __init__(self, *, token):
            calls.append(("init", token))

        def whoami(self, *, cache):
            calls.append(("whoami", cache))
            return {"name": "collector"}

    monkeypatch.setenv("HF_TOKEN", "secret-test-token")
    monkeypatch.setattr(hf_store, "HfApi", FakeApi)

    api = hf_store.get_api()

    assert isinstance(api, FakeApi)
    assert calls == [("init", "secret-test-token"), ("whoami", True)]


def test_push_retries_are_wrapped_around_repo_and_upload(monkeypatch, tmp_path: Path):
    calls = []

    class FakeApi:
        def upload_folder(self, **kwargs):
            calls.append(("upload", kwargs))

    api = FakeApi()
    monkeypatch.setattr(hf_store, "get_api", lambda: api)
    monkeypatch.setattr(
        hf_store,
        "ensure_repo",
        lambda supplied, repo_id, private=True: calls.append(
            ("ensure", supplied, repo_id, private)
        ),
    )

    hf_store.push(tmp_path, repo_id="owner/data", message="test upload")

    assert calls[0] == ("ensure", api, "owner/data", True)
    assert calls[1] == (
        "upload",
        {
            "repo_id": "owner/data",
            "repo_type": "dataset",
            "folder_path": str(tmp_path),
            "commit_message": "test upload",
        },
    )
