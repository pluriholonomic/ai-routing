"""H7 (coarse) — Do token prices track GPU rental prices?

Token side: a chained MATCHED-MODEL index from the wayback panel (BLS-style:
monthly mean of Δlog listed completion price across models present in both
adjacent months, chained). Handles model entry/exit without survivor bias.

GPU side: data-static/gpu_index_periods.csv — Silicon Data's published H100
medians by segment (2023-08→2025-12) spliced with Fabryka, Ornn, and our
Vast.ai capture. Commercial series (Bloomberg SDH100RT, OCPI-H100) drop in as extra
CSV rows if the user subscribes.

Outputs the aligned panel and Δlog correlations + cumulative declines. The
proper daily cointegration/ECM version is pre-registered and unlocks as the
vast.ai and 5-min token panels accumulate.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

GPU_CSV = Path("data-static/gpu_index_periods.csv")


def token_matched_model_index() -> pd.DataFrame:
    panel = data.q(
        f"""
        select id as model_id, run_ts, price_completion
        from {data.wayback_models()}
        where price_completion > 0 and id not like '%:free'
        """
    ).df()
    panel["month"] = pd.to_datetime(
        panel["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True
    ).dt.to_period("M")
    monthly = panel.groupby(["model_id", "month"])["price_completion"].median().reset_index()
    months = sorted(monthly["month"].unique())
    idx_rows = [{"month": months[0], "dlog": 0.0, "n_matched": 0, "index": 100.0}]
    level = 100.0
    for prev, cur in zip(months[:-1], months[1:], strict=True):
        a = monthly[monthly["month"] == prev].set_index("model_id")["price_completion"]
        b = monthly[monthly["month"] == cur].set_index("model_id")["price_completion"]
        common = a.index.intersection(b.index)
        dlog = float(np.log(b[common] / a[common]).mean()) if len(common) else 0.0
        level *= float(np.exp(dlog))
        idx_rows.append({"month": cur, "dlog": dlog, "n_matched": int(len(common)), "index": level})
    out = pd.DataFrame(idx_rows)
    out["month_start"] = out["month"].dt.to_timestamp()
    return out.drop(columns=["month"])


def align_gpu(token_idx: pd.DataFrame) -> pd.DataFrame:
    gpu = pd.read_csv(GPU_CSV, parse_dates=["period_start", "period_end"])
    rows = []
    for seg, g in gpu.groupby("segment"):
        g = g.sort_values("period_start")
        for r in g.itertuples(index=False):
            mask = (token_idx["month_start"] >= r.period_start) & (
                token_idx["month_start"] <= r.period_end
            )
            tok = token_idx.loc[mask, "index"].mean()
            if np.isnan(tok):
                continue
            rows.append(
                {
                    "segment": seg,
                    "period_start": r.period_start,
                    "gpu_usd_hr": r.usd_hr,
                    "token_index": float(tok),
                    "source": "static_gpu_history",
                    "series_unit": "usd_per_gpu_hour",
                }
            )
    return pd.DataFrame(rows)


def load_ornn_history() -> pd.DataFrame:
    """Load the full-history Ornn collector table when it has been captured."""
    try:
        return data.q(
            f"""
            select run_ts, gpu_class, observed_at, index_value, source_unit
            from read_parquet('{data.table_glob("ornn_gpu_index_history")}')
            where index_value > 0
            """
        ).df()
    except Exception as exc:
        log.info("Ornn history unavailable: %s", exc)
        return pd.DataFrame(
            columns=["run_ts", "gpu_class", "observed_at", "index_value", "source_unit"]
        )


def align_ornn_h100(token_idx: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Align Ornn's source-defined H100 SXM index to the monthly token index.

    The collector rewrites complete history each run. Deduplicate by observed
    timestamp and retain the latest fetch before taking a monthly median.
    The numerical values are retained in the existing GPU-value column for
    comparability with the H7 correlation machinery, while series_unit makes
    clear this is Ornn's compute index rather than a raw Vast offer.
    """
    columns = [
        "segment",
        "period_start",
        "gpu_usd_hr",
        "token_index",
        "source",
        "series_unit",
    ]
    if history.empty:
        return pd.DataFrame(columns=columns)
    h = history.copy()
    h = h[h["gpu_class"] == "H100 SXM"]
    h["observed_at"] = pd.to_datetime(h["observed_at"], utc=True, errors="coerce")
    h["index_value"] = pd.to_numeric(h["index_value"], errors="coerce")
    h = h.dropna(subset=["observed_at", "index_value"])
    h = h.sort_values(["observed_at", "run_ts"]).drop_duplicates(
        ["observed_at"], keep="last"
    )
    h["month_start"] = h["observed_at"].dt.tz_localize(None).dt.to_period("M").dt.to_timestamp()
    monthly = h.groupby("month_start", as_index=False)["index_value"].median()
    aligned = token_idx.merge(monthly, on="month_start", how="inner")
    if aligned.empty:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        {
            "segment": "ornn_h100_sxm_index",
            "period_start": aligned["month_start"],
            "gpu_usd_hr": aligned["index_value"],
            "token_index": aligned["index"],
            "source": "ornn",
            "series_unit": "ornn_compute_index",
        }
    )


def correlations(aligned: pd.DataFrame) -> dict:
    out = {}
    for seg, g in aligned.groupby("segment"):
        g = g.sort_values("period_start")
        if len(g) < 4:
            out[seg] = {"n_periods": int(len(g)), "note": "too few periods"}
            continue
        dl_gpu = np.diff(np.log(g["gpu_usd_hr"]))
        dl_tok = np.diff(np.log(g["token_index"]))
        corr = float(np.corrcoef(dl_gpu, dl_tok)[0, 1]) if len(dl_gpu) > 2 else None
        out[seg] = {
            "n_periods": int(len(g)),
            "source": str(g["source"].iloc[0]) if "source" in g else "unknown",
            "series_unit": str(g["series_unit"].iloc[0])
            if "series_unit" in g
            else "unknown",
            "corr_dlog": corr,
            "gpu_total_decline_pct": float(
                (g["gpu_usd_hr"].iloc[-1] / g["gpu_usd_hr"].iloc[0] - 1) * 100
            ),
            "token_total_decline_pct": float(
                (g["token_index"].iloc[-1] / g["token_index"].iloc[0] - 1) * 100
            ),
        }
    return out


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    tok = token_matched_model_index()
    save(tok, out_dir, "h7_token_index")
    aligned_static = align_gpu(tok)
    aligned_ornn = align_ornn_h100(tok, load_ornn_history())
    aligned = pd.concat([aligned_static, aligned_ornn], ignore_index=True)
    save(aligned, out_dir, "h7_aligned")
    results = {
        "token_index_span": [
            str(tok["month_start"].min())[:10],
            str(tok["month_start"].max())[:10],
        ],
        "token_index_total_change_pct": float(tok["index"].iloc[-1] - 100.0),
        "median_matched_models_per_month": float(tok["n_matched"].median()),
        "by_segment": correlations(aligned),
        "note": "coarse period-level; Ornn's H100 SXM source-defined index is included "
        "when captured. Daily ECM pre-registered as panels accumulate; commercial "
        "series (SDH100RT, OCPI-H100) drop into data-static/gpu_index_periods.csv",
    }
    save_json(results, out_dir, "h7_summary")
    log.info("H7: %s", results)
    return results
