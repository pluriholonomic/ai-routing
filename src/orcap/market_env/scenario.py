"""Validated scenario object for deterministic and learned simulations."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .types import ProviderSpec, Workload


@dataclass(frozen=True)
class MarketScenario:
    """One immutable simulation design.

    Demand is currently an integer per epoch.  Stochastic arrival processes
    generate these integers outside the kernel so common random numbers can be
    reused exactly across router treatments.
    """

    scenario_id: str
    workload: Workload
    providers: tuple[ProviderSpec, ...]
    horizon_epochs: int
    demand_per_epoch: int

    def __post_init__(self) -> None:
        if not self.scenario_id:
            raise ValueError("scenario_id must be non-empty")
        if len(self.providers) < 1:
            raise ValueError("scenario must contain at least one provider")
        names = [provider.provider for provider in self.providers]
        if len(set(names)) != len(names):
            raise ValueError("provider names must be unique")
        for name, value in [
            ("horizon_epochs", self.horizon_epochs),
            ("demand_per_epoch", self.demand_per_epoch),
        ]:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


def load_scenario(path: str | Path) -> MarketScenario:
    """Load a versioned TOML scenario with strict dataclass validation."""
    source = Path(path)
    with source.open("rb") as handle:
        raw = tomllib.load(handle)
    expected = {
        "schema_version",
        "scenario_id",
        "horizon_epochs",
        "demand_per_epoch",
        "workload",
        "providers",
    }
    unknown = set(raw) - expected
    if unknown:
        raise ValueError(f"unknown scenario fields: {sorted(unknown)}")
    if raw.get("schema_version") != 1:
        raise ValueError("schema_version must equal 1")
    workload_raw = dict(raw.get("workload") or {})
    providers_raw = raw.get("providers") or []
    if not isinstance(providers_raw, list):
        raise ValueError("providers must be an array of tables")
    return MarketScenario(
        scenario_id=str(raw.get("scenario_id") or ""),
        horizon_epochs=raw.get("horizon_epochs"),
        demand_per_epoch=raw.get("demand_per_epoch"),
        workload=Workload(**workload_raw),
        providers=tuple(ProviderSpec(**dict(provider)) for provider in providers_raw),
    )
