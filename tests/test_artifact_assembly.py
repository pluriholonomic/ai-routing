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
