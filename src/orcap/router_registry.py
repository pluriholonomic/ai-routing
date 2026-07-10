"""Versioned registry of public and account-configured routing adapters."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "config" / "router_registry.toml"


@dataclass(frozen=True)
class RouterSpec:
    name: str
    kind: str
    policy_class: str
    catalog_table: str
    realized_attempt_source: str
    supports_public_shadow: bool
    requires_credentials_for_realized_routes: bool


def registry() -> tuple[str, dict[str, RouterSpec]]:
    with REGISTRY_PATH.open("rb") as f:
        raw = tomllib.load(f)
    specs = {
        name: RouterSpec(
            name=name,
            kind=str(value["kind"]),
            policy_class=str(value["policy_class"]),
            catalog_table=str(value["catalog_table"]),
            realized_attempt_source=str(value["realized_attempt_source"]),
            supports_public_shadow=bool(value["supports_public_shadow"]),
            requires_credentials_for_realized_routes=bool(
                value["requires_credentials_for_realized_routes"]
            ),
        )
        for name, value in raw["routers"].items()
    }
    return str(raw["registry_version"]), specs


def router_spec(name: str) -> RouterSpec:
    _, specs = registry()
    if name not in specs:
        raise KeyError(f"unknown router {name!r}; add it to {REGISTRY_PATH}")
    return specs[name]
