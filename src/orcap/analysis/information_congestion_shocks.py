"""Build the outcome-blind public shock registry for information-congestion v1."""

from __future__ import annotations

import argparse
import hashlib
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa

from ..capture_api import write_partition
from ..config import run_timestamp
from ..information_congestion import (
    DEFAULT_CONFIG,
    IC_COMMON_SHOCK_SCHEMA,
    _time_series,
    load_protocol,
)
from ..price_experiments import provider_key
from .information_congestion_readiness import read_table


def _event_id(parts: list[Any]) -> str:
    material = "|".join(str(value) for value in parts)
    return "ics-" + hashlib.sha256(material.encode()).hexdigest()[:24]


def _base_event(
    *,
    study_id: str,
    protocol_sha256: str,
    event_type: str,
    event_ts: pd.Timestamp,
    model_id: str,
    provider: str | None,
    affected: list[str],
    eligible_n: int,
    pre_ts: pd.Timestamp,
    post_ts: pd.Timestamp,
    previous_value: float | None = None,
    new_value: float | None = None,
    log_price_change: float | None = None,
    placebo: bool = False,
    contaminated: bool = False,
) -> dict[str, Any]:
    keys = sorted(set(affected))
    return {
        "study_id": study_id,
        "event_id": _event_id([event_type, model_id, provider, event_ts.isoformat(), keys]),
        "event_type": event_type,
        "event_ts": event_ts.isoformat(),
        "model_id": model_id,
        "provider_key": provider,
        "provider_count": len(keys),
        "affected_provider_keys": keys,
        "eligible_n": int(eligible_n),
        "pre_run_ts": pre_ts.strftime("%Y%m%dT%H%M%SZ"),
        "post_run_ts": post_ts.strftime("%Y%m%dT%H%M%SZ"),
        "elapsed_minutes": float((post_ts - pre_ts).total_seconds() / 60),
        "log_price_change": log_price_change,
        "previous_value": previous_value,
        "new_value": new_value,
        "placebo": placebo,
        "contaminated": contaminated,
        "protocol_sha256": protocol_sha256,
        "payload_retained": False,
    }


def endpoint_shocks(
    snapshots: pd.DataFrame,
    *,
    models: list[str],
    study_id: str,
    protocol_sha256: str,
    maximum_adjacency_minutes: float,
    author_aliases: set[str],
) -> list[dict[str, Any]]:
    """Detect exact-adjacent price, entry, exit, and coincident changes."""

    events: list[dict[str, Any]] = []
    for model_id in models:
        frame = _time_series(snapshots, model_id)
        if frame.empty:
            continue
        times = pd.Index(sorted(frame["ts"].unique()))
        ordinal = {time: index for index, time in enumerate(times)}
        frame["capture_ordinal"] = frame["ts"].map(ordinal)
        eligible = frame.groupby("ts")["provider_key"].nunique().to_dict()
        frame = frame.sort_values(["provider_key", "ts"])
        grouped = frame.groupby("provider_key", sort=False)
        frame["previous_ts"] = grouped["ts"].shift()
        frame["previous_quote"] = grouped["quote_usd"].shift()
        frame["previous_ordinal"] = grouped["capture_ordinal"].shift()
        frame["elapsed_minutes"] = (
            frame["ts"] - frame["previous_ts"]
        ).dt.total_seconds() / 60
        adjacent = (
            frame["capture_ordinal"].sub(frame["previous_ordinal"]).eq(1)
            & frame["elapsed_minutes"].gt(0)
            & frame["elapsed_minutes"].le(maximum_adjacency_minutes)
        )
        changed = ~np.isclose(
            frame["quote_usd"],
            frame["previous_quote"],
            rtol=1e-12,
            atol=1e-15,
            equal_nan=False,
        )
        price_events = frame.loc[adjacent & changed].copy()
        for row in price_events.itertuples(index=False):
            key = str(row.provider_key)
            old, new = float(row.previous_quote), float(row.quote_usd)
            event_type = (
                "author_price_change" if key in author_aliases else "provider_price_change"
            )
            events.append(
                _base_event(
                    study_id=study_id,
                    protocol_sha256=protocol_sha256,
                    event_type=event_type,
                    event_ts=row.ts,
                    model_id=model_id,
                    provider=key,
                    affected=[key],
                    eligible_n=int(eligible.get(row.ts, 0)),
                    pre_ts=row.previous_ts,
                    post_ts=row.ts,
                    previous_value=old,
                    new_value=new,
                    log_price_change=(math.log(new / old) if old > 0 and new > 0 else None),
                )
            )
        for event_ts, group in price_events.groupby("ts"):
            keys = sorted(set(group["provider_key"].astype(str)))
            if len(keys) < 2:
                continue
            previous_ts = group["previous_ts"].max()
            events.append(
                _base_event(
                    study_id=study_id,
                    protocol_sha256=protocol_sha256,
                    event_type="coincident_price_change",
                    event_ts=event_ts,
                    model_id=model_id,
                    provider=None,
                    affected=keys,
                    eligible_n=int(eligible.get(event_ts, 0)),
                    pre_ts=previous_ts,
                    post_ts=event_ts,
                )
            )

        by_time = {
            time: set(group["provider_key"].astype(str))
            for time, group in frame.groupby("ts")
        }
        for pre_ts, post_ts in zip(times[:-1], times[1:], strict=True):
            elapsed = float((post_ts - pre_ts).total_seconds() / 60)
            if elapsed <= 0 or elapsed > maximum_adjacency_minutes:
                continue
            before, after = by_time[pre_ts], by_time[post_ts]
            for event_type, keys in (
                ("provider_entry", sorted(after - before)),
                ("provider_exit", sorted(before - after)),
            ):
                for key in keys:
                    events.append(
                        _base_event(
                            study_id=study_id,
                            protocol_sha256=protocol_sha256,
                            event_type=event_type,
                            event_ts=post_ts,
                            model_id=model_id,
                            provider=key,
                            affected=[key],
                            eligible_n=len(after),
                            pre_ts=pre_ts,
                            post_ts=post_ts,
                        )
                    )
    return events


def congestion_shocks(
    congestion: pd.DataFrame,
    *,
    models: list[str],
    study_id: str,
    protocol_sha256: str,
    maximum_adjacency_minutes: float,
    rate_limit_spike_minimum: float,
) -> list[dict[str, Any]]:
    """Detect router-enforcement and capacity shocks from the public stats surface."""

    required = {"run_ts", "model_permaslug", "provider_name"}
    if congestion.empty or not required.issubset(congestion):
        return []
    frame = congestion.copy()
    frame["ts"] = pd.to_datetime(
        frame["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
    )
    frame["provider_key"] = frame["provider_name"].map(provider_key)
    prefixes = tuple(sorted(models, key=len, reverse=True))

    def canonical_model(value: Any) -> str | None:
        raw = str(value)
        return next(
            (
                model
                for model in prefixes
                if raw == model or raw.startswith(model + "-")
            ),
            None,
        )

    frame["model_id"] = frame["model_permaslug"].map(canonical_model)
    frame = frame[
        frame["ts"].notna()
        & frame["provider_key"].ne("")
        & frame["model_id"].notna()
    ].copy()
    if frame.empty:
        return []
    frame = frame.sort_values(["model_id", "provider_key", "ts"])
    group = ["model_id", "provider_key"]
    grouped = frame.groupby(group, sort=False)
    frame["previous_ts"] = grouped["ts"].shift()
    frame["elapsed_minutes"] = (
        frame["ts"] - frame["previous_ts"]
    ).dt.total_seconds() / 60
    adjacent = frame["elapsed_minutes"].gt(0) & frame["elapsed_minutes"].le(
        maximum_adjacency_minutes
    )
    eligible = frame.groupby(["model_id", "ts"])["provider_key"].nunique().to_dict()
    events: list[dict[str, Any]] = []
    specs = (
        ("is_deranked", "derank_transition", None),
        ("rate_limited_5m", "rate_limit_spike", float(rate_limit_spike_minimum)),
        ("capacity_ceiling_rpm", "capacity_change", None),
    )
    for column, event_type, minimum_increase in specs:
        if column not in frame:
            continue
        current = pd.to_numeric(frame[column], errors="coerce")
        previous = grouped[column].shift()
        previous = pd.to_numeric(previous, errors="coerce")
        if minimum_increase is None:
            changed = current.notna() & previous.notna() & ~np.isclose(
                current, previous, rtol=1e-12, atol=1e-12
            )
        else:
            changed = current.sub(previous).ge(minimum_increase)
        for index in frame.index[adjacent & changed.fillna(False)]:
            row = frame.loc[index]
            key = str(row["provider_key"])
            model_id = str(row["model_id"])
            events.append(
                _base_event(
                    study_id=study_id,
                    protocol_sha256=protocol_sha256,
                    event_type=event_type,
                    event_ts=row["ts"],
                    model_id=model_id,
                    provider=key,
                    affected=[key],
                    eligible_n=int(eligible.get((model_id, row["ts"]), 0)),
                    pre_ts=row["previous_ts"],
                    post_ts=row["ts"],
                    previous_value=float(previous.loc[index]),
                    new_value=float(current.loc[index]),
                )
            )
    if not events:
        return []
    raw = pd.DataFrame(events)
    collapsed: list[dict[str, Any]] = []
    group_columns = ["event_type", "model_id", "event_ts", "pre_run_ts", "post_run_ts"]
    for _, group in raw.groupby(group_columns, dropna=False, sort=True):
        template = group.iloc[0].to_dict()
        keys = sorted(
            {
                str(key)
                for values in group["affected_provider_keys"]
                for key in list(values)
            }
        )
        template["provider_key"] = None
        template["affected_provider_keys"] = keys
        template["provider_count"] = len(keys)
        template["previous_value"] = float(
            pd.to_numeric(group["previous_value"], errors="coerce").mean()
        )
        template["new_value"] = float(
            pd.to_numeric(group["new_value"], errors="coerce").mean()
        )
        template["event_id"] = _event_id(
            [
                template["event_type"],
                template["model_id"],
                template["event_ts"],
                keys,
            ]
        )
        collapsed.append(template)
    return collapsed


def mark_event_contamination(
    events: list[dict[str, Any]], *, isolation_window_minutes: float
) -> list[dict[str, Any]]:
    """Mark event clocks that overlap another same-family response window."""

    if not events:
        return events
    families = {
        "author_price_change": "quote",
        "provider_price_change": "quote",
        "coincident_price_change": "quote",
        "provider_entry": "composition",
        "provider_exit": "composition",
        "derank_transition": "enforcement",
        "rate_limit_spike": "enforcement",
        "capacity_change": "capacity",
    }
    frame = pd.DataFrame(events)
    frame["family"] = frame["event_type"].map(families).fillna(frame["event_type"])
    frame["clock"] = pd.to_datetime(frame["event_ts"], utc=True, errors="coerce")
    window = pd.to_timedelta(float(isolation_window_minutes), unit="m")
    contaminated_clocks: set[tuple[str, str, pd.Timestamp]] = set()
    for (model_id, family), group in frame.groupby(["model_id", "family"], sort=False):
        clocks = pd.Series(sorted(set(group["clock"].dropna())))
        if clocks.empty:
            continue
        previous_gap = clocks.diff()
        next_gap = clocks.shift(-1) - clocks
        for clock, previous, following in zip(
            clocks, previous_gap, next_gap, strict=True
        ):
            if (pd.notna(previous) and previous <= window) or (
                pd.notna(following) and following <= window
            ):
                contaminated_clocks.add((str(model_id), str(family), clock))
    output = []
    for row in events:
        family = families.get(str(row["event_type"]), str(row["event_type"]))
        clock = pd.Timestamp(row["event_ts"])
        key = (str(row["model_id"]), family, clock)
        output.append(row | {"contaminated": bool(key in contaminated_clocks)})
    return output


def placebo_clocks(
    events: list[dict[str, Any]],
    snapshots: pd.DataFrame,
    *,
    models: list[str],
    study_id: str,
    protocol_sha256: str,
    interval_hours: int,
) -> list[dict[str, Any]]:
    """Add deterministic clocks, labeled placebo so they never count as shocks."""

    output: list[dict[str, Any]] = []
    event_times = pd.to_datetime(
        pd.Series([row["event_ts"] for row in events]), utc=True, errors="coerce"
    )
    for model_id in models:
        frame = _time_series(snapshots, model_id)
        if frame.empty:
            continue
        by_time = frame.groupby("ts")["provider_key"].nunique()
        start = frame["ts"].min().ceil(f"{interval_hours}h")
        end = frame["ts"].max().floor(f"{interval_hours}h")
        for ts in pd.date_range(start, end, freq=f"{interval_hours}h"):
            nearest = by_time.index[np.argmin(np.abs(by_time.index - ts))]
            if abs((nearest - ts).total_seconds()) > 15 * 60:
                continue
            near_event = (
                not event_times.empty
                and ((event_times - ts).abs() <= pd.to_timedelta(15, unit="m")).any()
            )
            if near_event:
                continue
            output.append(
                _base_event(
                    study_id=study_id,
                    protocol_sha256=protocol_sha256,
                    event_type="placebo_clock",
                    event_ts=ts,
                    model_id=model_id,
                    provider=None,
                    affected=[],
                    eligible_n=int(by_time.loc[nearest]),
                    pre_ts=nearest,
                    post_ts=nearest,
                    placebo=True,
                )
            )
    return output


def build_registry(
    data_root: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
) -> tuple[list[dict[str, Any]], str]:
    protocol, digest = load_protocol(config_path)
    settings = protocol["shocks"]
    study_id = str(protocol["study"]["study_id"])
    models = [str(value) for value in protocol["study"]["models"]]
    endpoints = read_table(data_root, "endpoints_snapshots")
    congestion = read_table(data_root, "congestion_intraday")
    events = endpoint_shocks(
        endpoints,
        models=models,
        study_id=study_id,
        protocol_sha256=digest,
        maximum_adjacency_minutes=float(settings["maximum_adjacency_minutes"]),
        author_aliases={provider_key(value) for value in settings["author_provider_aliases"]},
    )
    events.extend(
        congestion_shocks(
            congestion,
            models=models,
            study_id=study_id,
            protocol_sha256=digest,
            maximum_adjacency_minutes=float(settings["maximum_adjacency_minutes"]),
            rate_limit_spike_minimum=float(settings["rate_limit_spike_minimum"]),
        )
    )
    events = mark_event_contamination(
        events,
        isolation_window_minutes=float(settings["isolation_window_minutes"]),
    )
    events.extend(
        placebo_clocks(
            events,
            endpoints,
            models=models,
            study_id=study_id,
            protocol_sha256=digest,
            interval_hours=int(settings["placebo_interval_hours"]),
        )
    )
    deduped = {str(row["event_id"]): row for row in events}
    existing = read_table(data_root, "ic_common_shocks")
    existing_ids = (
        set(existing["event_id"].dropna().astype(str))
        if not existing.empty and "event_id" in existing
        else set()
    )
    new_rows = [row for key, row in deduped.items() if key not in existing_ids]
    return sorted(new_rows, key=lambda row: (row["event_ts"], row["event_id"])), digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    rows, digest = build_registry(args.data_root, config_path=args.config)
    now = datetime.now(UTC)
    run_id = run_timestamp(now)
    dt = now.date().isoformat()
    output = args.output_root / "curated"
    path = None
    if rows:
        table = pa.Table.from_pylist(
            [row | {"run_ts": run_id, "dt": dt} for row in rows],
            schema=IC_COMMON_SHOCK_SCHEMA,
        )
        path = write_partition(table, "ic_common_shocks", run_id, dt, output)
    summary = {
        "format": "orcap-information-congestion-shocks-v1",
        "study_id": "openrouter-information-congestion-v1",
        "protocol_sha256": digest,
        "events": len(rows),
        "non_placebo_events": sum(not bool(row["placebo"]) for row in rows),
        "output": str(path) if path else None,
    }
    print(summary)


if __name__ == "__main__":
    main()
