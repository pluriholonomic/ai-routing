"""H75 — transparent Bittensor score/weight/reward allocation comparator."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

from . import data
from .common import DEFAULT_OUT, save, save_json

SOURCE = "bittensor_chutes"
MIN_SNAPSHOTS = 90
MIN_DAYS = 21
SNAPSHOT_KEYS = ["run_ts", "netuid", "mechid", "block_number", "block_hash"]
SUMMARY_COLUMNS = [
    *SNAPSHOT_KEYS,
    "dt",
    "subnet_name",
    "neurons",
    "active_neurons",
    "validators",
    "incentivized_miners",
    "nonzero_weight_edges",
    "stake_hhi",
    "incentive_hhi",
    "emission_hhi",
    "effective_incentive_recipients",
    "stake_weighted_incoming_to_incentive_spearman",
    "matrix_complete",
]


def _load(table: str) -> pd.DataFrame:
    try:
        glob = data.table_glob(table)
        return data.q(
            f"select * from read_parquet('{glob}', union_by_name=true) where source = '{SOURCE}'"
        ).df()
    except Exception:
        return pd.DataFrame()


def _hhi(values: pd.Series) -> float | None:
    values = pd.to_numeric(values, errors="coerce").fillna(0).clip(lower=0)
    total = float(values.sum())
    if total <= 0:
        return None
    shares = values / total
    return float((shares**2).sum())


def snapshot_panel(neurons: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    required_neurons = {
        *SNAPSHOT_KEYS,
        "dt",
        "subnet_name",
        "uid",
        "active",
        "validator_permit",
        "stake",
        "incentive",
        "emission",
    }
    required_weights = {
        *SNAPSHOT_KEYS,
        "validator_uid",
        "miner_uid",
        "weight",
        "matrix_size",
        "matrix_complete_sparse_encoding",
    }
    if (
        neurons.empty
        or weights.empty
        or not required_neurons.issubset(neurons.columns)
        or not required_weights.issubset(weights.columns)
    ):
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    output = []
    grouped_weights = {key: group for key, group in weights.groupby(SNAPSHOT_KEYS, sort=False)}
    for key, group in neurons.groupby(SNAPSHOT_KEYS, sort=True):
        edge_group = grouped_weights.get(key)
        if edge_group is None or edge_group.empty:
            continue
        group = group.drop_duplicates("uid", keep="last").copy()
        edge_group = edge_group.copy()
        size_values = pd.to_numeric(edge_group["matrix_size"], errors="coerce").dropna().unique()
        matrix_complete = (
            len(size_values) == 1
            and int(size_values[0]) == len(group)
            and edge_group["matrix_complete_sparse_encoding"].astype(bool).all()
        )

        validator_stake = group.loc[group["validator_permit"].astype(bool), ["uid", "stake"]].copy()
        validator_stake["stake"] = pd.to_numeric(
            validator_stake["stake"], errors="coerce"
        ).fillna(0)
        total_validator_stake = float(validator_stake["stake"].clip(lower=0).sum())
        validator_stake["validator_stake_share"] = (
            validator_stake["stake"].clip(lower=0) / total_validator_stake
            if total_validator_stake > 0
            else 0.0
        )
        incoming = edge_group.merge(
            validator_stake[["uid", "validator_stake_share"]],
            left_on="validator_uid",
            right_on="uid",
            how="left",
        )
        incoming["weighted_incoming"] = (
            pd.to_numeric(incoming["weight"], errors="coerce").fillna(0)
            * incoming["validator_stake_share"].fillna(0)
        )
        incoming = incoming.groupby("miner_uid", as_index=False)["weighted_incoming"].sum()
        comparison = group[["uid", "incentive"]].merge(
            incoming, left_on="uid", right_on="miner_uid", how="left"
        )
        comparison["weighted_incoming"] = comparison["weighted_incoming"].fillna(0)
        comparison["incentive"] = pd.to_numeric(comparison["incentive"], errors="coerce").fillna(0)
        correlation = None
        if comparison["weighted_incoming"].nunique() > 1 and comparison["incentive"].nunique() > 1:
            correlation = float(
                spearmanr(
                    comparison["weighted_incoming"], comparison["incentive"], nan_policy="omit"
                ).statistic
            )
        incentive_hhi = _hhi(group["incentive"])
        output.append(
            {
                "run_ts": key[0],
                "netuid": key[1],
                "mechid": key[2],
                "block_number": key[3],
                "block_hash": key[4],
                "dt": group["dt"].iloc[0],
                "subnet_name": group["subnet_name"].iloc[0],
                "neurons": int(group["uid"].nunique()),
                "active_neurons": int(group["active"].astype(bool).sum()),
                "validators": int(group["validator_permit"].astype(bool).sum()),
                "incentivized_miners": int(
                    pd.to_numeric(group["incentive"], errors="coerce").fillna(0).gt(0).sum()
                ),
                "nonzero_weight_edges": int(len(edge_group)),
                "stake_hhi": _hhi(group["stake"]),
                "incentive_hhi": incentive_hhi,
                "emission_hhi": _hhi(group["emission"]),
                "effective_incentive_recipients": (
                    1.0 / incentive_hhi if incentive_hhi and incentive_hhi > 0 else None
                ),
                "stake_weighted_incoming_to_incentive_spearman": correlation,
                "matrix_complete": bool(matrix_complete),
            }
        )
    return pd.DataFrame(output, columns=SUMMARY_COLUMNS)


def coverage_gate(panel: pd.DataFrame) -> dict:
    if panel.empty:
        return {
            "status": "not_identified",
            "snapshots": 0,
            "source_days": 0,
            "minimum_snapshots": MIN_SNAPSHOTS,
            "minimum_days": MIN_DAYS,
        }
    complete = panel.loc[panel["matrix_complete"].eq(True)]
    source_days = pd.to_datetime(complete["dt"], utc=True, errors="coerce").dt.date.nunique()
    reasons = []
    if len(complete) < MIN_SNAPSHOTS:
        reasons.append(f"only {len(complete)}/{MIN_SNAPSHOTS} complete metagraph snapshots")
    if source_days < MIN_DAYS:
        reasons.append(f"only {source_days}/{MIN_DAYS} source days")
    return {
        "status": "transparent_allocation_panel_ready" if not reasons else "power_gated",
        "snapshots": int(len(panel)),
        "complete_snapshots": int(len(complete)),
        "source_days": int(source_days),
        "minimum_snapshots": MIN_SNAPSHOTS,
        "minimum_days": MIN_DAYS,
        "gate_reasons": reasons,
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    neurons = _load("bittensor_neurons")
    weights = _load("bittensor_weights")
    panel = snapshot_panel(neurons, weights)
    result = {
        "neuron_rows": int(len(neurons)),
        "nonzero_weight_rows": int(len(weights)),
        "coverage_gate": coverage_gate(panel),
        "claim_boundary": (
            "H75 observes public Bittensor validator weights and score/reward state for the "
            "Chutes subnet. It is a transparent scoring-allocation comparator, not Chutes "
            "request routing, tokens served, workload delivery, prices, costs, or evidence "
            "about OpenRouter's private policy."
        ),
    }
    save(panel, out_dir, "h75_bittensor_allocation")
    save_json(result, out_dir, "h75_summary")
    return result
