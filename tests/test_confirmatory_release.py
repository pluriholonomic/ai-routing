from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pandas as pd
import pytest

import orcap.confirmatory_release as release


class _Relation:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def df(self) -> pd.DataFrame:
        return self.frame.copy()


class _Commit:
    def __init__(self, oid: str):
        self.oid = oid


class _Api:
    def __init__(self, *, manifest=False, marker=False, calls=None):
        self.manifest = manifest
        self.marker = marker
        self.calls = calls if calls is not None else []

    def file_exists(self, repo_id, filename, *, repo_type):
        self.calls.append(("exists", filename))
        if filename.endswith("release_manifest.json"):
            return self.manifest
        if filename.endswith("first_outcome_access.json"):
            return self.marker
        return False

    def upload_file(self, **kwargs):
        marker = Path(kwargs["path_or_fileobj"])
        assert json.loads(marker.read_text())["outcome_fields_before_marker"] == "not_queried"
        self.calls.append(("marker", kwargs["path_in_repo"]))
        return _Commit("marker-commit")

    def upload_folder(self, **kwargs):
        folder = Path(kwargs["folder_path"])
        assert (folder / "release_manifest.json").exists()
        self.calls.append(("bundle", kwargs["path_in_repo"]))
        return _Commit("release-commit")


@contextlib.contextmanager
def _pinned():
    yield {
        "source": "huggingface",
        "repo_id": "test/dataset",
        "revision": "immutable-input-revision",
        "path": "hf://datasets/test/dataset@immutable-input-revision",
        "resolution": "test",
    }


def _ready_spec(monkeypatch, calls):
    original = release.STUDIES["h81"]

    def runner(*, out_dir):
        calls.append(("runner", str(out_dir)))
        (out_dir / "result.json").write_text('{"estimate": 0.0}\n')
        return {"outcomes_released": True, "estimate": 0.0}

    spec = release.StudySpec(
        key=original.key,
        study_id=original.study_id,
        release_path=original.release_path,
        preregistration=original.preregistration,
        analyzer_path=original.analyzer_path,
        gate=lambda: {"release_ready": True, "outcomes_queried": False},
        runner=runner,
    )
    monkeypatch.setitem(release.STUDIES, "h81", spec)
    monkeypatch.setattr(release.data, "pinned_analysis_source", _pinned)
    monkeypatch.setattr(release, "_code_commit", lambda: "code-commit")


def test_assignment_gate_queries_never_select_h81_outcomes(monkeypatch):
    sqls = []

    def query(sql):
        sqls.append(sql)
        return _Relation(release._empty_assignment_frame())

    monkeypatch.setattr(release.data, "q", query)
    status = release.h81_gate_status()

    assert status["release_ready"] is False
    assert status["outcomes_queried"] is False
    assert len(sqls) == 1
    assert "select *" not in sqls[0].lower()
    for forbidden in ["outcome", "cost_usd", "latency_ms", "selected_provider"]:
        assert forbidden not in sqls[0].lower()


def test_h95_route_attempt_preflight_uses_assignment_columns_only(monkeypatch):
    sqls = []

    def query(sql):
        sqls.append(sql)
        return _Relation(pd.DataFrame())

    monkeypatch.setattr(release.data, "q", query)
    status = release.h95_gate_status()

    route_sql = next(sql for sql in sqls if "router_route_attempts" in sql)
    assert status["release_ready"] is False
    assert status["outcomes_queried"] is False
    assert "select *" not in route_sql.lower()
    assert "outcome" not in route_sql.lower()


def test_remote_marker_precedes_first_outcome_runner(monkeypatch, tmp_path):
    calls = []
    _ready_spec(monkeypatch, calls)
    api = _Api(calls=calls)

    result = release.release_study(
        "h81", output_root=tmp_path, publish=True, api=api
    )

    labels = [call[0] for call in calls]
    assert labels.index("marker") < labels.index("runner") < labels.index("bundle")
    assert result["status"] == "released"
    assert result["first_access_marker_commit"] == "marker-commit"
    assert result["release_commit"] == "release-commit"
    manifest = json.loads((tmp_path / "h81" / "release_manifest.json").read_text())
    assert manifest["dataset"]["revision"] == "immutable-input-revision"
    assert manifest["environment_lock_sha256"]
    assert any(item["path"] == "result.json" for item in manifest["files"])


def test_existing_manifest_skips_outcome_runner(monkeypatch, tmp_path):
    calls = []
    _ready_spec(monkeypatch, calls)
    api = _Api(manifest=True, calls=calls)

    result = release.release_study(
        "h81", output_root=tmp_path, publish=True, api=api
    )

    assert result["status"] == "already_released"
    assert not any(call[0] == "runner" for call in calls)


def test_open_gate_without_publish_still_cannot_call_outcome_runner(
    monkeypatch, tmp_path
):
    calls = []
    _ready_spec(monkeypatch, calls)

    result = release.release_study("h81", output_root=tmp_path, publish=False)

    assert result["status"] == "ready_requires_published_first_access"
    assert result["outcome_access"] == "not_queried_without_remote_first_access_marker"
    assert not any(call[0] == "runner" for call in calls)


def test_orphan_marker_refuses_second_outcome_access(monkeypatch, tmp_path):
    calls = []
    _ready_spec(monkeypatch, calls)
    api = _Api(marker=True, calls=calls)

    with pytest.raises(RuntimeError, match="refusing a second outcome access"):
        release.release_study("h81", output_root=tmp_path, publish=True, api=api)

    assert not any(call[0] == "runner" for call in calls)


def test_closed_gate_never_calls_remote_api_or_runner(monkeypatch, tmp_path):
    calls = []
    original = release.STUDIES["h81"]
    spec = release.StudySpec(
        key=original.key,
        study_id=original.study_id,
        release_path=original.release_path,
        preregistration=original.preregistration,
        analyzer_path=original.analyzer_path,
        gate=lambda: {"release_ready": False, "outcomes_queried": False},
        runner=lambda **kwargs: calls.append(("runner", kwargs)),
    )
    monkeypatch.setitem(release.STUDIES, "h81", spec)
    monkeypatch.setattr(release.data, "pinned_analysis_source", _pinned)
    monkeypatch.setattr(release, "_code_commit", lambda: "code-commit")
    api = _Api(calls=calls)

    result = release.release_study(
        "h81", output_root=tmp_path, publish=True, api=api
    )

    assert result["status"] == "accruing"
    assert calls == []
    gate = json.loads((tmp_path / "h81" / "assignment_only_gate.json").read_text())
    assert gate["dataset"]["revision"] == "immutable-input-revision"


def test_remote_workflow_is_clean_idempotent_and_compaction_triggered():
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "confirmatory-release.yml"
    ).read_text()

    assert 'workflows: ["compact"]' in workflow
    assert "cancel-in-progress: false" in workflow
    assert "scripts/run_confirmatory_releases.py" in workflow
    assert "--publish" in workflow
    assert "if: always()" in workflow
