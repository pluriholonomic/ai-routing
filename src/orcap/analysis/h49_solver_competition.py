"""H49 — sampled CoW solver-competition monitor.

The public CoW endpoint returns only the latest solver competition at the time
of collection. This module turns those bounded snapshots into a transparent
time series of candidate-solver counts, ranks, and within-auction objective
gaps. It is expressly not a market-wide trade, fill, surplus, or solver-share
estimator.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

MIN_AUCTIONS = 100
MIN_DAYS = 7
MIN_SOLVERS = 3
AUCTION_COLUMNS = [
    "auction_id",
    "run_ts",
    "dt",
    "candidate_order_count",
    "candidate_solver_count",
    "winner_solver_count",
    "settlement_transaction_count",
    "auction_span_blocks",
    "score_observed_count",
    "best_competition_score",
    "second_competition_score",
    "relative_best_second_score_gap",
]
SOLVER_COLUMNS = [
    "participant_id",
    "sampled_auctions",
    "sampled_wins",
    "sampled_win_rate_given_candidate",
    "sampled_auction_participation_share",
    "median_ranking",
]


def load_competitions() -> pd.DataFrame:
    """Load only explicitly labeled, stable-identity competition candidates."""
    glob = data.table_glob("market_participants")
    required = {
        "run_ts",
        "dt",
        "source",
        "metric",
        "auction_id",
        "participant_id",
        "ranking",
        "is_winner",
        "competition_score",
    }
    try:
        schema = data.q(
            f"describe select * from read_parquet('{glob}', union_by_name=true)"
        ).df()
        if not required.issubset(set(schema["column_name"])):
            return pd.DataFrame(columns=sorted(required))
        return data.q(
            f"""
            select cast(run_ts as varchar) as run_ts,
                   cast(dt as varchar) as dt,
                   cast(auction_id as varchar) as auction_id,
                   cast(participant_id as varchar) as participant_id,
                   ranking, is_winner, competition_score
            from read_parquet('{glob}', union_by_name=true)
            where source = 'cow'
              and metric = 'solver_competition_candidate'
              and auction_id is not null
              and participant_id is not null
            """
        ).df()
    except Exception as exc:
        log.info("H49 competition data unavailable: %s", exc)
        return pd.DataFrame(columns=sorted(required))


def load_auction_observations() -> pd.DataFrame:
    """Load count-only fields from public sampled solver-competition snapshots.

    ``auction.orders`` in the public response is a current batch's opaque order
    UID list. We intentionally retain only its count and the settlement count;
    neither is inferred to be full market-wide arrivals, fills, volume, or
    demand. This lets H49 describe the intensity of the *observed* snapshots
    without exposing identifiers that would invite a false order-flow claim.
    """
    glob = data.table_glob("market_events")
    required = {"run_ts", "dt", "source", "event_type", "record_json"}
    columns = [
        "auction_id",
        "run_ts",
        "dt",
        "candidate_order_count",
        "settlement_transaction_count",
        "auction_span_blocks",
    ]
    try:
        schema = data.q(
            f"describe select * from read_parquet('{glob}', union_by_name=true)"
        ).df()
        if not required.issubset(set(schema["column_name"])):
            return pd.DataFrame(columns=columns)
        rows = data.q(
            f"""
            select cast(run_ts as varchar) as run_ts,
                   cast(dt as varchar) as dt,
                   record_json
            from read_parquet('{glob}', union_by_name=true)
            where source = 'cow' and event_type = 'solver_competition_snapshot'
            """
        ).df()
    except Exception as exc:
        log.info("H49 auction observation data unavailable: %s", exc)
        return pd.DataFrame(columns=columns)
    parsed = []
    for row in rows.itertuples(index=False):
        try:
            payload = json.loads(row.record_json)
            start = int(payload["auction_start_block"])
            deadline = int(payload["auction_deadline_block"])
            parsed.append(
                {
                    "auction_id": str(payload["auction_id"]),
                    "run_ts": row.run_ts,
                    "dt": row.dt,
                    "candidate_order_count": int(payload["candidate_order_count"]),
                    "settlement_transaction_count": int(
                        payload["settlement_transaction_count"]
                    ),
                    "auction_span_blocks": deadline - start,
                }
            )
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return pd.DataFrame(parsed, columns=columns)


def _deduplicate(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows.copy()
    out = rows.copy()
    out["competition_score"] = pd.to_numeric(out["competition_score"], errors="coerce")
    out["ranking"] = pd.to_numeric(out["ranking"], errors="coerce")
    out["is_winner"] = out["is_winner"].fillna(False).astype(bool)
    # A collector can observe the same latest auction on repeated runs. Keep
    # its latest row per solver; it is one sampled auction, not repeated flow.
    return out.sort_values("run_ts").drop_duplicates(
        ["auction_id", "participant_id"], keep="last"
    )


def auction_panel(rows: pd.DataFrame, observations: pd.DataFrame | None = None) -> pd.DataFrame:
    """One observation per distinct sampled auction, with within-batch metrics."""
    rows = _deduplicate(rows)
    if rows.empty:
        return pd.DataFrame(columns=AUCTION_COLUMNS)
    results = []
    for auction_id, group in rows.groupby("auction_id", sort=True):
        scores = group["competition_score"].dropna().sort_values(ascending=False)
        best = float(scores.iloc[0]) if len(scores) else None
        second = float(scores.iloc[1]) if len(scores) > 1 else None
        relative_gap = (best - second) / best if best and second is not None else None
        latest = group.sort_values("run_ts").iloc[-1]
        results.append(
            {
                "auction_id": auction_id,
                "run_ts": latest["run_ts"],
                "dt": latest["dt"],
                "candidate_solver_count": int(group["participant_id"].nunique()),
                "winner_solver_count": int(group["is_winner"].sum()),
                "score_observed_count": int(scores.shape[0]),
                "best_competition_score": best,
                "second_competition_score": second,
                "relative_best_second_score_gap": relative_gap,
            }
        )
    panel = pd.DataFrame(results)
    if observations is not None and not observations.empty:
        latest_observations = observations.sort_values("run_ts").drop_duplicates(
            "auction_id", keep="last"
        )
        panel = panel.merge(
            latest_observations.loc[
                :,
                [
                    "auction_id",
                    "candidate_order_count",
                    "settlement_transaction_count",
                    "auction_span_blocks",
                ],
            ],
            on="auction_id",
            how="left",
        )
    for column in (
        "candidate_order_count",
        "settlement_transaction_count",
        "auction_span_blocks",
    ):
        if column not in panel:
            panel[column] = None
    return panel.loc[:, AUCTION_COLUMNS]


def solver_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Candidate and winner frequency within the *observed sampled* auctions."""
    rows = _deduplicate(rows)
    if rows.empty:
        return pd.DataFrame(columns=SOLVER_COLUMNS)
    total_auctions = rows["auction_id"].nunique()
    grouped = rows.groupby("participant_id", as_index=False).agg(
        sampled_auctions=("auction_id", "nunique"),
        sampled_wins=("is_winner", "sum"),
        median_ranking=("ranking", "median"),
    )
    grouped["sampled_win_rate_given_candidate"] = (
        grouped["sampled_wins"] / grouped["sampled_auctions"]
    )
    grouped["sampled_auction_participation_share"] = grouped["sampled_auctions"] / total_auctions
    return grouped.loc[:, SOLVER_COLUMNS].sort_values(
        ["sampled_auctions", "participant_id"], ascending=[False, True]
    )


def summarize(auctions: pd.DataFrame, solvers: pd.DataFrame) -> dict:
    if auctions.empty:
        return {
            "evidence_status": "not_identified",
            "n_sampled_auctions": 0,
            "claim_boundary": _claim_boundary(),
        }
    n_days = int(auctions["dt"].nunique())
    reasons = []
    if len(auctions) < MIN_AUCTIONS:
        reasons.append(f"only {len(auctions)}/{MIN_AUCTIONS} sampled auctions")
    if n_days < MIN_DAYS:
        reasons.append(f"only {n_days}/{MIN_DAYS} days")
    if len(solvers) < MIN_SOLVERS:
        reasons.append(f"only {len(solvers)}/{MIN_SOLVERS} candidate solvers")
    return {
        "evidence_status": "sampled_descriptive" if not reasons else "power_gated",
        "n_sampled_auctions": int(len(auctions)),
        "n_days": n_days,
        "n_candidate_solvers": int(len(solvers)),
        "median_candidate_solver_count": float(auctions["candidate_solver_count"].median()),
        "median_winner_solver_count": float(auctions["winner_solver_count"].median()),
        "median_sampled_candidate_order_count": _median(auctions["candidate_order_count"]),
        "median_sampled_settlement_transaction_count": _median(
            auctions["settlement_transaction_count"]
        ),
        "median_relative_best_second_score_gap": _median(
            auctions["relative_best_second_score_gap"]
        ),
        "power_gate": {
            "min_sampled_auctions": MIN_AUCTIONS,
            "min_days": MIN_DAYS,
            "min_candidate_solvers": MIN_SOLVERS,
        },
        "gate_reasons": reasons,
        "claim_boundary": _claim_boundary(),
    }


def _median(values: pd.Series) -> float | None:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return None
    value = values.median()
    return float(value) if pd.notna(value) else None


def _claim_boundary() -> str:
    return (
        "Each row is a bounded latest-auction snapshot at collector cadence. It is not a "
        "market-wide or randomly sampled auction census, trade/fill/surplus measure, solver "
        "market share, causal competition estimate, or a direct analogue of routed request flow."
    )


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    rows = load_competitions()
    auctions = auction_panel(rows, load_auction_observations())
    solvers = solver_panel(rows)
    save(auctions, out_dir, "h49_solver_competition_auctions")
    save(solvers, out_dir, "h49_solver_competition_solvers")
    result = summarize(auctions, solvers)
    save_json(result, out_dir, "h49_summary")
    return result
