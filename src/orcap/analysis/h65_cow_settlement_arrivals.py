"""H65 — finalized CoW settlement-arrival comparator.

The unit is one on-chain ``Settlement`` event per transaction, binned into
non-overlapping 15-minute UTC intervals.  This intentionally excludes the
number of ``Trade`` events in a batch: batch size is a contract-mechanical
outcome and would spuriously look like self-excitation.  A count INGARCH is a
discrete-time Hawkes analogue, not a fitted continuous-time Hawkes process.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

from .common import DEFAULT_OUT, save, save_json

BIN_FREQUENCY = "15min"
MIN_DAYS = 7
MIN_SETTLEMENTS = 100


def settlement_bins(events: pd.DataFrame, *, frequency: str = BIN_FREQUENCY) -> pd.DataFrame:
    """Create complete UTC-day bins from exact finalized settlement timestamps."""
    required = {"event_type", "transaction_hash", "event_time"}
    if not required.issubset(events):
        return pd.DataFrame(columns=["bin_start", "settlement_count"])
    rows = events[events["event_type"] == "settlement"].copy()
    rows["event_time"] = pd.to_datetime(rows["event_time"], utc=True, errors="coerce")
    rows = rows.dropna(subset=["event_time", "transaction_hash"])
    rows = rows.drop_duplicates("transaction_hash")
    if rows.empty:
        return pd.DataFrame(columns=["bin_start", "settlement_count"])
    start = rows["event_time"].min().normalize()
    end = rows["event_time"].max().normalize() + pd.offsets.Day()
    bins = pd.date_range(start, end, freq=frequency, inclusive="left", tz="UTC")
    counts = rows.groupby(rows["event_time"].dt.floor(frequency)).size()
    return pd.DataFrame(
        {"bin_start": bins, "settlement_count": [int(counts.get(item, 0)) for item in bins]}
    )


def _loglik(y: np.ndarray, lam: np.ndarray) -> float:
    lam = np.maximum(lam, 1e-12)
    return float(np.sum(y * np.log(lam) - lam - gammaln(y + 1)))


def _ingarch_fit(train: np.ndarray) -> tuple[float, float, float] | None:
    """Poisson INGARCH(1,1), the binned exponential-Hawkes comparison."""
    if len(train) < 20 or train.mean() <= 0:
        return None
    mean = float(train.mean())

    def nll(theta: np.ndarray) -> float:
        omega, alpha, beta = theta
        if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 0.995:
            return 1e15
        lam = mean
        result = 0.0
        previous = float(train[0])
        for value in train[1:]:
            lam = omega + alpha * previous + beta * lam
            result += value * math.log(max(lam, 1e-12)) - lam - gammaln(value + 1)
            previous = float(value)
        return -result

    best = None
    for alpha, beta in ((0.1, 0.2), (0.3, 0.3), (0.05, 0.7)):
        candidate = minimize(
            nll,
            x0=np.array([max(1e-4, mean * (1 - alpha - beta)), alpha, beta]),
            method="Nelder-Mead",
            options={"maxiter": 2_000, "xatol": 1e-7, "fatol": 1e-7},
        )
        if np.isfinite(candidate.fun) and (best is None or candidate.fun < best.fun):
            best = candidate
    if best is None:
        return None
    omega, alpha, beta = (float(value) for value in best.x)
    if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 0.995:
        return None
    return omega, alpha, beta


def compare_count_models(bins: pd.DataFrame, *, split_fraction: float = 0.7) -> dict:
    """Chronological held-out constant/diurnal Poisson vs count-INGARCH.

    The hour-of-day Poisson has a Gamma(0.5, 0.5) prior for each UTC hour.
    It is deliberately included before treating any count-autoregressive gain
    as temporal clustering rather than a deterministic intraday pattern.
    """
    y = bins["settlement_count"].to_numpy(dtype=float)
    hours = pd.to_datetime(bins["bin_start"], utc=True).dt.hour.to_numpy(dtype=int)
    if not 0.5 <= split_fraction <= 0.8:
        raise ValueError("split_fraction must be between 0.5 and 0.8")
    split = int(len(y) * split_fraction)
    if split < 20 or len(y) - split < 10 or y[:split].mean() <= 0:
        return {"model_status": "insufficient_nonzero_training_bins"}
    train, test = y[:split], y[split:]
    poisson_rate = float(train.mean())
    poisson_ll = _loglik(test, np.full(len(test), poisson_rate))
    training_hours, test_hours = hours[:split], hours[split:]
    diurnal_rates = np.array(
        [
            (float(train[training_hours == hour].sum()) + 0.5)
            / (int((training_hours == hour).sum()) + 0.5)
            for hour in range(24)
        ]
    )
    diurnal_ll = _loglik(test, diurnal_rates[test_hours])
    result = {
        "model_status": "ok",
        "split": {
            "training_fraction": split_fraction,
            "training_bins": int(len(train)),
            "test_bins": int(len(test)),
        },
        "constant_poisson_rate_per_15min": poisson_rate,
        "constant_poisson_test_log_likelihood": poisson_ll,
        "diurnal_poisson_prior": "Gamma(0.5, 0.5) independently by UTC hour",
        "diurnal_poisson_test_log_likelihood": diurnal_ll,
        "diurnal_minus_constant_poisson_test_log_likelihood": diurnal_ll - poisson_ll,
    }
    fit = _ingarch_fit(train)
    if fit is None:
        return result | {"ingarch_status": "fit_failed"}
    omega, alpha, beta = fit
    lam = poisson_rate
    previous = float(train[0])
    for value in train[1:]:
        lam = omega + alpha * previous + beta * lam
        previous = float(value)
    predicted = []
    for value in test:
        lam = omega + alpha * previous + beta * lam
        predicted.append(lam)
        previous = float(value)  # one-step-ahead forecast conditions on observed history
    ingarch_ll = _loglik(test, np.array(predicted))
    return result | {
        "ingarch_status": "ok",
        "ingarch_omega": omega,
        "ingarch_alpha": alpha,
        "ingarch_beta": beta,
        "ingarch_persistence": alpha + beta,
        "ingarch_test_log_likelihood": ingarch_ll,
        "ingarch_minus_poisson_test_log_likelihood": ingarch_ll - poisson_ll,
        "ingarch_minus_diurnal_poisson_test_log_likelihood": ingarch_ll - diurnal_ll,
    }


def sensitivity(events: pd.DataFrame) -> pd.DataFrame:
    """Within-panel robustness grid; it is not independent replication."""
    rows = []
    for frequency in ("5min", "15min", "30min", "1h"):
        bins = settlement_bins(events, frequency=frequency)
        for split_fraction in (0.6, 0.7, 0.8):
            result = compare_count_models(bins, split_fraction=split_fraction)
            rows.append(
                {
                    "bin_frequency": frequency,
                    "split_fraction": split_fraction,
                    "n_bins": int(len(bins)),
                    "n_settlements": int(bins["settlement_count"].sum()) if not bins.empty else 0,
                    "model_status": result.get("model_status"),
                    "ingarch_status": result.get("ingarch_status"),
                    "ingarch_minus_diurnal_poisson_test_log_likelihood": result.get(
                        "ingarch_minus_diurnal_poisson_test_log_likelihood"
                    ),
                    "ingarch_persistence": result.get("ingarch_persistence"),
                }
            )
    return pd.DataFrame(rows)


def summarize(bins: pd.DataFrame, *, robustness: pd.DataFrame | None = None) -> dict:
    if bins.empty:
        return {
            "evidence_status": "not_identified",
            "n_settlements": 0,
            "claim_boundary": _claim_boundary(),
        }
    n_days = int(bins["bin_start"].dt.date.nunique())
    n_settlements = int(bins["settlement_count"].sum())
    mean = float(bins["settlement_count"].mean())
    variance = float(bins["settlement_count"].var(ddof=0))
    reasons = []
    if n_days < MIN_DAYS:
        reasons.append(f"only {n_days}/{MIN_DAYS} complete UTC days")
    if n_settlements < MIN_SETTLEMENTS:
        reasons.append(f"only {n_settlements}/{MIN_SETTLEMENTS} finalized settlements")
    result = {
        "evidence_status": "descriptive_arrival_comparator" if not reasons else "power_gated",
        "n_settlements": n_settlements,
        "n_complete_utc_days": n_days,
        "n_15min_bins": int(len(bins)),
        "mean_settlements_per_15min": mean,
        "variance_settlements_per_15min": variance,
        "fano_factor": variance / mean if mean > 0 else None,
        "count_model_comparison": compare_count_models(bins),
        "power_gate": {"min_complete_days": MIN_DAYS, "min_settlements": MIN_SETTLEMENTS},
        "gate_reasons": reasons,
        "claim_boundary": _claim_boundary(),
    }
    if robustness is not None and not robustness.empty:
        usable = robustness.dropna(subset=["ingarch_minus_diurnal_poisson_test_log_likelihood"])
        result["within_panel_sensitivity"] = {
            "n_specifications": int(len(robustness)),
            "n_usable_specifications": int(len(usable)),
            "n_ingarch_beats_diurnal": int(
                (usable["ingarch_minus_diurnal_poisson_test_log_likelihood"] > 0).sum()
            ),
            "min_ingarch_minus_diurnal_test_log_likelihood": _float_or_none(
                usable["ingarch_minus_diurnal_poisson_test_log_likelihood"].min()
                if not usable.empty
                else None
            ),
            "max_ingarch_minus_diurnal_test_log_likelihood": _float_or_none(
                usable["ingarch_minus_diurnal_poisson_test_log_likelihood"].max()
                if not usable.empty
                else None
            ),
            "boundary": (
                "This varies bins and split points within the same seven-day panel; it is a "
                "robustness diagnostic, not an independent replication or model-selection "
                "procedure."
            ),
        }
    return result


def _float_or_none(value: object) -> float | None:
    return float(value) if value is not None and pd.notna(value) else None


def _claim_boundary() -> str:
    return (
        "The unit is one finalized GPv2 Settlement event per transaction, not individual Trade "
        "events, order arrivals, user demand, routed requests, volumes, surplus, quality, or "
        "welfare. The INGARCH is a 15-minute discrete-time Hawkes analogue evaluated "
        "out-of-sample against constant-rate and UTC-hour Poisson baselines; it is not a "
        "continuous-time Hawkes estimate and cannot establish strategic self-excitation."
    )


def run(events_path: Path, out_dir: Path = DEFAULT_OUT) -> dict:
    events = pd.read_parquet(events_path)
    bins = settlement_bins(events)
    save(bins, out_dir, "h65_cow_settlement_15min")
    robustness = sensitivity(events)
    save(robustness, out_dir, "h65_cow_settlement_sensitivity")
    result = summarize(bins, robustness=robustness)
    save_json(result, out_dir, "h65_summary")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    print(run(args.events, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
