"""H47 — matched public GPU quote basis: Akash aggregate vs Vast offers.

This is a narrowly matched, posted-quote comparison. It does not establish a
clearing price, GPU-hours sold, or quality-adjusted cost: Akash reports an
aggregate model quote while Vast exposes individual offers.  The mapping is
versioned and intentionally excludes ambiguous datacenter-GPU equivalences.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

REPO_ROOT = Path(__file__).resolve().parents[3]
MAP_PATH = REPO_ROOT / "config" / "gpu_venue_map.toml"
MAX_MATCH_MINUTES = 90
MIN_SPAN_DAYS = 7
MIN_MATCHED_COHORTS = 2
MIN_MATCHED_PAIRS = 50
PANEL_COLUMNS = [
    "cohort",
    "akash_quote_id",
    "vast_gpu_class",
    "akash_run_ts",
    "vast_run_ts",
    "elapsed_minutes",
    "akash_quote_usd_hr",
    "akash_available_units",
    "vast_median_usd_hr",
    "vast_rented_share",
    "vast_offer_count",
    "vast_over_akash_basis_pct",
]


def venue_map() -> tuple[str, pd.DataFrame]:
    with MAP_PATH.open("rb") as f:
        raw = tomllib.load(f)
    rows = [
        {
            "cohort": name,
            "akash_quote_id": spec["akash_quote_id"],
            "vast_gpu_class": spec["vast_gpu_class"],
        }
        for name, spec in raw["cohorts"].items()
    ]
    return str(raw["mapping_version"]), pd.DataFrame(rows)


def vast_snapshot_panel(offers: pd.DataFrame) -> pd.DataFrame:
    if offers.empty:
        return pd.DataFrame(
            columns=[
                "run_ts",
                "gpu_class",
                "vast_median_usd_hr",
                "vast_rented_share",
                "vast_offer_count",
            ]
        )
    rows = offers.copy()
    rows["dph_total"] = pd.to_numeric(rows.get("dph_total"), errors="coerce")
    rows = rows[(rows["offer_type"] == "on-demand") & (rows["dph_total"] > 0)].copy()
    if rows.empty:
        return pd.DataFrame(
            columns=[
                "run_ts",
                "gpu_class",
                "vast_median_usd_hr",
                "vast_rented_share",
                "vast_offer_count",
            ]
        )
    rented = rows.get("rented")
    if rented is None:
        rows["rented_bool"] = np.nan
    else:
        rows["rented_bool"] = rented.map(
            lambda value: str(value).lower() in {"true", "1", "yes"} if pd.notna(value) else np.nan
        )
    return (
        rows.groupby(["run_ts", "gpu_class"], as_index=False)
        .agg(
            vast_median_usd_hr=("dph_total", "median"),
            vast_rented_share=("rented_bool", "mean"),
            vast_offer_count=("dph_total", "size"),
        )
        .sort_values(["gpu_class", "run_ts"])
    )


def match_venue_quotes(
    akash: pd.DataFrame, vast: pd.DataFrame, mapping: pd.DataFrame
) -> pd.DataFrame:
    """Nearest-time match one explicit GPU cohort at a time."""
    if akash.empty or vast.empty or mapping.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    quotes = akash.copy()
    quotes["price_usd"] = pd.to_numeric(quotes["price_usd"], errors="coerce")
    quotes["available_units"] = pd.to_numeric(quotes.get("available_units"), errors="coerce")
    quotes["ts"] = pd.to_datetime(quotes["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    offers = vast_snapshot_panel(vast)
    offers["ts"] = pd.to_datetime(offers["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    rows = []
    for item in mapping.itertuples(index=False):
        left = quotes[(quotes["quote_id"] == item.akash_quote_id) & (quotes["price_usd"] > 0)]
        right = offers[offers["gpu_class"] == item.vast_gpu_class]
        for quote in left.itertuples(index=False):
            candidates = right.loc[
                (right["ts"] - quote.ts).abs() <= pd.Timedelta(MAX_MATCH_MINUTES, unit="min")
            ]
            if candidates.empty:
                continue
            match = (
                candidates.assign(_gap=(candidates["ts"] - quote.ts).abs())
                .sort_values(["_gap", "ts"], ascending=[True, False])
                .iloc[0]
            )
            basis = (float(match["vast_median_usd_hr"]) / float(quote.price_usd) - 1) * 100
            rows.append(
                {
                    "cohort": item.cohort,
                    "akash_quote_id": item.akash_quote_id,
                    "vast_gpu_class": item.vast_gpu_class,
                    "akash_run_ts": quote.run_ts,
                    "vast_run_ts": match["run_ts"],
                    "elapsed_minutes": float(match["_gap"].total_seconds() / 60),
                    "akash_quote_usd_hr": float(quote.price_usd),
                    "akash_available_units": quote.available_units,
                    "vast_median_usd_hr": float(match["vast_median_usd_hr"]),
                    "vast_rented_share": match["vast_rented_share"],
                    "vast_offer_count": int(match["vast_offer_count"]),
                    "vast_over_akash_basis_pct": basis,
                }
            )
    return pd.DataFrame(rows, columns=PANEL_COLUMNS)


def coverage_diagnostic(akash: pd.DataFrame, vast: pd.DataFrame, mapping: pd.DataFrame) -> dict:
    """Expose exact-cohort and timestamp gaps before declaring zero matches.

    A zero matched panel can arise because no venue lists an exact cohort, no
    valid quote exists, or because independently captured snapshots have not
    yet been published on a common clock. These states have different repairs
    and must not be collapsed into a zero-basis observation.
    """
    quotes = akash.copy()
    quotes["price_usd"] = pd.to_numeric(quotes.get("price_usd"), errors="coerce")
    quotes = quotes.loc[quotes["price_usd"] > 0].copy()
    if not quotes.empty:
        quotes["ts"] = pd.to_datetime(
            quotes["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
        )
        quotes = quotes.dropna(subset=["ts"])
    offers = vast_snapshot_panel(vast)
    if not offers.empty:
        offers["ts"] = pd.to_datetime(
            offers["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True, errors="coerce"
        )
        offers = offers.dropna(subset=["ts"])
    rows = []
    for item in mapping.itertuples(index=False):
        left = (
            quotes.loc[quotes["quote_id"].eq(item.akash_quote_id)]
            if "quote_id" in quotes
            else quotes.iloc[0:0]
        )
        right = (
            offers.loc[offers["gpu_class"].eq(item.vast_gpu_class)]
            if "gpu_class" in offers
            else offers.iloc[0:0]
        )
        nearest = []
        within_window = 0
        if not left.empty and not right.empty:
            for timestamp in left["ts"]:
                gap = (right["ts"] - timestamp).abs().min()
                minutes = float(gap.total_seconds() / 60)
                nearest.append(minutes)
                within_window += int(minutes <= MAX_MATCH_MINUTES)
        rows.append(
            {
                "cohort": item.cohort,
                "akash_quote_id": item.akash_quote_id,
                "vast_gpu_class": item.vast_gpu_class,
                "akash_quote_snapshots": int(len(left)),
                "vast_on_demand_snapshots": int(len(right)),
                "nearest_elapsed_minutes": min(nearest) if nearest else None,
                "akash_snapshots_within_match_window": within_window,
            }
        )
    return {
        "valid_akash_quote_rows": int(len(quotes)),
        "vast_on_demand_snapshot_rows": int(len(offers)),
        "mapping_cohorts": int(len(mapping)),
        "cohorts": rows,
        "claim_boundary": (
            "Coverage diagnostic only. It identifies explicit quote/cohort/timestamp overlap; "
            "it is not a price basis, fill, utilization, or execution measure."
        ),
    }


def summarize(panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {
            "gate": {
                "min_span_days": MIN_SPAN_DAYS,
                "min_matched_cohorts": MIN_MATCHED_COHORTS,
                "min_matched_pairs": MIN_MATCHED_PAIRS,
                "passed": False,
            },
            "verdict": "gated_no_matched_quote_pairs",
        }
    ts = pd.to_datetime(panel["akash_run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    span_days = (ts.max() - ts.min()).total_seconds() / 86400 if len(ts) > 1 else 0.0
    n_cohorts = int(panel["cohort"].nunique())
    gate = {
        "min_span_days": MIN_SPAN_DAYS,
        "min_matched_cohorts": MIN_MATCHED_COHORTS,
        "min_matched_pairs": MIN_MATCHED_PAIRS,
        "span_days": round(span_days, 2),
        "matched_cohorts": n_cohorts,
        "matched_pairs": int(len(panel)),
    }
    gate["passed"] = bool(
        span_days >= MIN_SPAN_DAYS
        and n_cohorts >= MIN_MATCHED_COHORTS
        and len(panel) >= MIN_MATCHED_PAIRS
    )
    return {
        "gate": gate,
        "verdict": (
            "descriptive_matched_posted_quote_basis"
            if gate["passed"]
            else "insufficient_quote_history"
        ),
        "median_vast_over_akash_basis_pct": float(panel["vast_over_akash_basis_pct"].median()),
        "by_cohort": {
            cohort: {
                "n": int(len(group)),
                "median_basis_pct": float(group["vast_over_akash_basis_pct"].median()),
            }
            for cohort, group in panel.groupby("cohort")
        },
        "claim_boundary": (
            "Exact-specification public posted quotes only. This is not a fill-price, "
            "quality-adjusted cost, or provider-profit comparison."
        ),
    }


def _load_akash_quotes() -> tuple[pd.DataFrame, bool]:
    """Return quotes and whether the source query completed.

    A source-read failure is intentionally distinct from a successful empty
    table: otherwise a transient dataset/network error looks like evidence of
    no matched quotes.
    """
    try:
        return (
            data.q(
                f"""
            select run_ts, quote_id, price_usd, available_units
            from read_parquet('{data.table_glob("market_quotes")}', union_by_name=true)
            where source = 'akash' and quote_unit = 'usd_per_gpu_hour'
            """
            ).df(),
            True,
        )
    except Exception:
        return pd.DataFrame(), False


def _load_vast_offers() -> tuple[pd.DataFrame, bool]:
    try:
        return (
            data.q(
                f"""
            select run_ts, gpu_class, offer_type, dph_total, rented
            from read_parquet('{data.table_glob("gpu_offers_snapshots")}')
            """
            ).df(),
            True,
        )
    except Exception:
        return pd.DataFrame(), False


def source_read_status(rows: pd.DataFrame, query_succeeded: bool) -> dict:
    """Serialize source health without exposing transient exception details."""
    return {
        "status": "query_succeeded" if query_succeeded else "query_failed",
        "rows": int(len(rows)),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    version, mapping = venue_map()
    akash, akash_query_succeeded = _load_akash_quotes()
    vast, vast_query_succeeded = _load_vast_offers()
    panel = match_venue_quotes(akash, vast, mapping)
    save(panel, out_dir, "h47_gpu_venue_basis")
    result = {
        "mapping_version": version,
        "source_reads": {
            "akash_market_quotes": source_read_status(akash, akash_query_succeeded),
            "vast_gpu_offers": source_read_status(vast, vast_query_succeeded),
        },
        "coverage_diagnostic": coverage_diagnostic(akash, vast, mapping),
        **summarize(panel),
    }
    save_json(result, out_dir, "h47_summary")
    return result
