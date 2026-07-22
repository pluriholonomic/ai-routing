from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("script", "args"),
    [
        ("scripts/assemble_artifacts.sh", ["26"]),
        ("scripts/assemble_price_artifacts.sh", ["26", "paid"]),
    ],
)
def test_plan_data_is_unwrapped_into_canonical_root(tmp_path, script, args):
    root = Path(__file__).parents[1]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "date").write_text("#!/bin/sh\necho 2026-07-19T00:00:00Z\n")
    (bin_dir / "gh").write_text(
        """#!/bin/sh
if [ "$1" = "run" ] && [ "$2" = "list" ]; then
  echo 101
  exit 0
fi
if [ "$1" = "run" ] && [ "$2" = "download" ]; then
  shift 2
  dest=""
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--dir" ]; then
      dest="$2"
      shift 2
    else
      shift
    fi
  done
  mkdir -p "$dest/artifact/plan-data/curated/example/dt=2026-07-19"
  printf row > "$dest/artifact/plan-data/curated/example/dt=2026-07-19/row.parquet"
  printf '{}' > "$dest/artifact/price-plan.json"
  exit 0
fi
exit 2
"""
    )
    for executable in bin_dir.iterdir():
        executable.chmod(0o755)
    destination = tmp_path / "assembled"
    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}
    completed = subprocess.run(
        ["bash", str(root / script), args[0], str(destination), *args[1:]],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (
        destination / "curated/example/dt=2026-07-19/row.parquet"
    ).read_text() == "row"
    assert not (destination / "plan-data").exists()
    assert not (destination / "price-plan.json").exists()


def test_artifact_assemblers_retry_github_api_calls():
    root = Path(__file__).parents[1]
    retry = (root / "scripts/gh_retry.sh").read_text(encoding="utf-8")
    assert "GH_RETRY_MAX_ATTEMPTS" in retry
    assert "sleep" in retry
    for name in ("assemble_artifacts.sh", "assemble_price_artifacts.sh"):
        text = (root / "scripts" / name).read_text(encoding="utf-8")
        assert 'source "$SCRIPT_DIR/gh_retry.sh"' in text
        assert "gh_retry run list" in text
        assert "gh_retry run download" in text


def test_gh_retry_recovers_from_transient_failure(tmp_path):
    root = Path(__file__).parents[1]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    counter = tmp_path / "counter"
    fake = bin_dir / "gh"
    fake.write_text(
        """#!/bin/sh
if [ ! -f "$GH_RETRY_COUNTER" ]; then
  printf 1 > "$GH_RETRY_COUNTER"
  echo transient >&2
  exit 1
fi
echo recovered
"""
    )
    fake.chmod(0o755)
    env = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GH_RETRY_COUNTER": str(counter),
        "GH_RETRY_MAX_ATTEMPTS": "2",
        "GH_RETRY_INITIAL_SECONDS": "0",
        "GH_RETRY_MAX_SECONDS": "0",
    }
    completed = subprocess.run(
        [
            "bash",
            "-c",
            'source scripts/gh_retry.sh; gh_retry run list --workflow capture.yml',
        ],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "recovered"
    assert "attempt 1/2 failed" in completed.stderr
