from __future__ import annotations

import tomllib
from pathlib import Path

from orcap.analysis.adaptive_adversarial_replay import COST_FRACTIONS, QUOTE_MULTIPLIERS
from orcap.analysis.adaptive_adversarial_simulation import (
    CAPACITY_REGIMES,
    DEVIATION_MULTIPLIERS,
)
from orcap.analysis.adaptive_adversarial_simulation import (
    COST_FRACTIONS as SIM_COST_FRACTIONS,
)


def test_frozen_protocol_matches_analysis_constants():
    path = Path("config/adaptive_adversarial_v1.toml")
    with path.open("rb") as handle:
        protocol = tomllib.load(handle)
    assert protocol["schema_version"] == 1
    assert tuple(protocol["historical_replay"]["quote_multipliers"]) == QUOTE_MULTIPLIERS
    assert tuple(protocol["historical_replay"]["cost_fractions"]) == COST_FRACTIONS
    assert tuple(protocol["simulation"]["cost_fractions"]) == SIM_COST_FRACTIONS
    assert tuple(protocol["simulation"]["deviation_multipliers"]) == DEVIATION_MULTIPLIERS
    assert dict(
        zip(
            protocol["simulation"]["capacity_regimes"],
            protocol["simulation"]["capacity_multipliers"],
            strict=True,
        )
    ) == CAPACITY_REGIMES


def test_preregistration_preserves_paid_study_boundary():
    text = Path(
        "experiments/adaptive-router-adversarial-v1/preregistration.md"
    ).read_text(encoding="utf-8")
    assert "screening" in text.casefold()
    assert "existing 120-block paid adaptive" in text
    assert "does not identify actual" in text


def test_v2_protocol_is_future_only_and_workflow_cannot_release_v1():
    path = Path("config/adaptive_adversarial_v2.toml")
    with path.open("rb") as handle:
        protocol = tomllib.load(handle)
    assert protocol["schema_version"] == 2
    assert protocol["status"] == "frozen_future_only"
    assert protocol["population"]["development_data_through"] < protocol["population"][
        "test_start_date"
    ]
    assert protocol["population"]["test_start_date"] == "2026-07-21"
    assert protocol["population"]["test_end_date"] == "2026-08-03"
    workflow = Path(
        ".github/workflows/adaptive-adversarial-confirmatory.yml"
    ).read_text(encoding="utf-8")
    assert "adaptive-router-adversarial-v2" in workflow
    assert "--start-date 2026-07-21" in workflow
    assert "--end-date 2026-08-03" in workflow
    assert "config/adaptive_adversarial_v1.toml" not in workflow
    assert "write immutable marker before eligible-row access" in workflow
