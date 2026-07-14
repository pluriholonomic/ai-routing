"""Lab/provider status-page collector (statuspage.io JSON APIs).

Feeds CBH-18 (peer supply when first-party capacity binds): incident spells
define capacity-bind windows. incidents.json returns the trailing incident
history on first fetch, so the panel is partially backfilled from day one;
the actual depth per provider is recorded rather than assumed.

Tables: lab_incidents (one row per incident per run; dedupe by incident id at
analysis time), lab_status_snapshots (current indicator per provider).
"""

from __future__ import annotations

import json
import logging
import tomllib
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, dt_partition, run_timestamp

log = logging.getLogger(__name__)

REGISTRY = Path(__file__).resolve().parents[2] / "config" / "lab_status.toml"
UA = {"User-Agent": "orcap lab-status watcher (research)"}


def _json(resp: httpx.Response) -> Any | None:
    """Some registered hosts serve HTML at the statuspage path; skip them."""
    try:
        body = resp.json()
    except (json.JSONDecodeError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def incident_rows(provider: str, body: Any, run_ts: str, dt: str) -> list[dict[str, Any]]:
    rows = []
    for inc in (body or {}).get("incidents") or []:
        comps = ",".join(c.get("name", "") for c in inc.get("components") or [])
        rows.append(
            {
                "run_ts": run_ts,
                "dt": dt,
                "provider": provider,
                "incident_id": inc.get("id"),
                "name": inc.get("name"),
                "impact": inc.get("impact"),
                "status": inc.get("status"),
                "created_at": inc.get("created_at"),
                "updated_at": inc.get("updated_at"),
                "resolved_at": inc.get("resolved_at"),
                "components": comps,
                "shortlink": inc.get("shortlink"),
            }
        )
    return rows


def capture(registry: Path = REGISTRY, curated_dir: Path = CURATED_DIR) -> dict[str, Any]:
    with registry.open("rb") as f:
        pages = tomllib.load(f)["pages"]
    run_ts, dt = run_timestamp(), dt_partition()
    incidents: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    per_provider: dict[str, int] = {}
    with httpx.Client(timeout=30, follow_redirects=True, headers=UA) as client:
        for p in pages:
            prov = p["provider"]
            try:
                s = client.get(f"{p['base_url']}/api/v2/summary.json")
                if s.status_code == 200 and _json(s) is not None:
                    st = _json(s).get("status") or {}
                    snapshots.append(
                        {
                            "run_ts": run_ts,
                            "dt": dt,
                            "provider": prov,
                            "indicator": st.get("indicator"),
                            "description": st.get("description"),
                        }
                    )
                r = client.get(f"{p['base_url']}/api/v2/incidents.json")
                if r.status_code == 200 and _json(r) is not None:
                    rows = incident_rows(prov, _json(r), run_ts, dt)
                    incidents.extend(rows)
                    per_provider[prov] = len(rows)
                else:
                    per_provider[prov] = -1
            except httpx.HTTPError as exc:
                log.warning("status page %s failed: %s", prov, exc)
                per_provider[prov] = -1
    if incidents:
        write_partition(
            pa.Table.from_pylist(incidents), "lab_incidents", run_ts, dt, curated_dir
        )
    if snapshots:
        write_partition(
            pa.Table.from_pylist(snapshots), "lab_status_snapshots", run_ts, dt, curated_dir
        )
    log.info("lab status: incident history depth per provider: %s", per_provider)
    return {"providers": per_provider, "n_incident_rows": len(incidents)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(json.dumps(capture()))


if __name__ == "__main__":
    main()
