#!/usr/bin/env python3
"""Audit endpoint snapshot duplication and independently rebuild pricing events."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from orcap.analysis import data
from orcap.compact import TRACKED_PRICE_FIELDS, fold_pricing_changes


def _records(relation) -> list[dict[str, Any]]:
    return [dict(zip(relation.columns, row, strict=True)) for row in relation.fetchall()]


def _event_key(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)


def audit(revision: str) -> dict[str, Any]:
    os.environ["ORCAP_HF_REVISION"] = revision
    data.reset_connection()
    con = data.connect()
    con.execute("SET enable_progress_bar=false")
    endpoints = data.table_glob("endpoints_snapshots")
    changes = data.table_glob("pricing_changes", layer="derived")

    daily = _records(
        con.sql(
            f"""
            select cast(dt as varchar) as dt,
                   count(*) as physical_rows,
                   count(distinct (
                       run_ts, model_id, provider_name, tag,
                       endpoint_fingerprint, record_json
                   )) as distinct_source_records,
                   count(distinct (
                       run_ts, model_id, provider_name, tag, endpoint_fingerprint
                   )) as listing_keys,
                   count(distinct run_ts) as capture_runs
            from read_parquet('{endpoints}')
            group by dt
            order by dt
            """
        )
    )
    totals = {
        field: sum(int(row[field]) for row in daily)
        for field in (
            "physical_rows",
            "distinct_source_records",
            "listing_keys",
            "capture_runs",
        )
    }
    totals["exact_duplicate_rows"] = (
        totals["physical_rows"] - totals["distinct_source_records"]
    )
    totals["same_listing_raw_variants"] = (
        totals["distinct_source_records"] - totals["listing_keys"]
    )

    conflicts = _records(
        con.sql(
            f"""
            with base as (
                select dt, run_ts, model_id, provider_name, tag,
                       endpoint_fingerprint, record_json,
                       hash(
                           price_prompt, price_completion, price_request,
                           price_image, price_input_cache_read,
                           price_input_cache_write, price_discount
                       ) as price_hash,
                       hash(
                           status, uptime_last_5m, uptime_last_30m,
                           uptime_last_1d, latency_last_30m,
                           throughput_last_30m
                       ) as availability_hash,
                       hash(
                           quantization, context_length, max_completion_tokens,
                           max_prompt_tokens, supports_implicit_caching,
                           supported_parameters
                       ) as capability_hash
                from read_parquet('{endpoints}')
            ), grouped as (
                select cast(dt as varchar) as dt, run_ts, model_id,
                       provider_name, tag, endpoint_fingerprint,
                       count(*) as physical_rows,
                       count(distinct record_json) as raw_variants,
                       count(distinct price_hash) as price_variants,
                       count(distinct availability_hash) as availability_variants,
                       count(distinct capability_hash) as capability_variants
                from base
                group by all
            )
            select dt,
                   count(*) filter (where raw_variants > 1) as raw_conflict_groups,
                   count(*) filter (where price_variants > 1) as price_conflict_groups,
                   count(*) filter (where availability_variants > 1)
                       as availability_conflict_groups,
                   count(*) filter (where capability_variants > 1)
                       as capability_conflict_groups
            from grouped
            group by dt
            order by dt
            """
        )
    )
    conflict_totals = {
        field: sum(int(row[field]) for row in conflicts)
        for field in (
            "raw_conflict_groups",
            "price_conflict_groups",
            "availability_conflict_groups",
            "capability_conflict_groups",
        )
    }

    derived_dates = [
        str(row[0])
        for row in con.sql(
            f"select distinct dt from read_parquet('{changes}') order by dt"
        ).fetchall()
    ]
    state: dict[str, dict[str, Any]] = {}
    rebuilt: list[dict[str, Any]] = []
    pricing_columns = ", ".join(TRACKED_PRICE_FIELDS)
    for dt in derived_dates:
        table = con.execute(
            f"""
            select distinct run_ts, model_id, provider_name, tag,
                            endpoint_fingerprint, {pricing_columns}
            from read_parquet(?)
            where dt = ?
            order by run_ts, model_id, provider_name, tag, endpoint_fingerprint
            """,
            [endpoints, dt],
        ).to_arrow_table()
        events, state = fold_pricing_changes(table, state)
        rebuilt.extend({"dt": dt, **event} for event in events)

    observed_relation = con.sql(
        f"""
        select dt, changed_at_run_ts, model_id, provider_name, tag,
               endpoint_fingerprint, field, old_value, new_value
        from read_parquet('{changes}')
        where dt in ({','.join(repr(dt) for dt in derived_dates)})
        """
    )
    observed = _records(observed_relation)
    rebuilt_map = {_event_key(row): row for row in rebuilt}
    observed_map = {_event_key(row): row for row in observed}
    rebuilt_set = set(rebuilt_map)
    observed_set = set(observed_map)
    missing_keys = rebuilt_set - observed_set
    unexpected_keys = observed_set - rebuilt_set

    def _difference_counts(keys: set[str], field: str) -> dict[str, int]:
        rows = rebuilt_map if keys is missing_keys else observed_map
        counts: dict[str, int] = {}
        for key in keys:
            value = str(rows[key][field])
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    event_comparison = {
        "derived_dates": derived_dates,
        "rebuilt_events": len(rebuilt),
        "rebuilt_unique_events": len(rebuilt_set),
        "observed_events": len(observed),
        "observed_unique_events": len(observed_set),
        "missing_from_observed": len(missing_keys),
        "unexpected_in_observed": len(unexpected_keys),
        "missing_by_date": _difference_counts(missing_keys, "dt"),
        "missing_by_field": _difference_counts(missing_keys, "field"),
        "unexpected_by_date": _difference_counts(unexpected_keys, "dt"),
        "unexpected_by_field": _difference_counts(unexpected_keys, "field"),
        "missing_sample": [rebuilt_map[key] for key in sorted(missing_keys)[:10]],
        "unexpected_sample": [observed_map[key] for key in sorted(unexpected_keys)[:10]],
        "exact_set_match": rebuilt_set == observed_set,
    }

    return {
        "schema_version": 1,
        "input_revision": revision,
        "deduplication_unit": [
            "run_ts",
            "model_id",
            "provider_name",
            "tag",
            "endpoint_fingerprint",
            "record_json",
        ],
        "listing_unit": [
            "run_ts",
            "model_id",
            "provider_name",
            "tag",
            "endpoint_fingerprint",
        ],
        "daily": daily,
        "totals": totals,
        "daily_conflicts": conflicts,
        "conflict_totals": conflict_totals,
        "pricing_event_rebuild": event_comparison,
        "verdict": {
            "exact_overlap_present": totals["exact_duplicate_rows"] > 0,
            "price_conflicts_present": conflict_totals["price_conflict_groups"] > 0,
            "capability_conflicts_present": conflict_totals["capability_conflict_groups"] > 0,
            "availability_variants_present": (
                conflict_totals["availability_conflict_groups"] > 0
            ),
            "safe_to_deduplicate_exact_source_records": (
                conflict_totals["price_conflict_groups"] == 0
                and conflict_totals["capability_conflict_groups"] == 0
            ),
            "derived_pricing_events_reproducible": event_comparison["exact_set_match"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.revision)
    payload = json.dumps(result, indent=2, sort_keys=True, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
