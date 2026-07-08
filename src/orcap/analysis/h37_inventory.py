"""H37 — Inventory-control forensics: which capacity policy do providers run?

Four classical tests, each mapped to our measurements:

  (a) Square-root staffing (Halfin-Whitt): buffer = ceiling − load vs load.
      log-log slope ≈ 0.5 ⇒ QED staffing; ≈ 1 ⇒ proportional overcapacity;
      ≈ 0 ⇒ fixed buffer. Caveat: ceiling is the router's estimate, partly
      derived from observed peaks — interpret slopes, not levels.
  (b) Erlang-B inversion: from observed blocking (reject rate), arrival rate,
      and service time (tokens/req ÷ tok/s), invert the Erlang loss formula
      for implied servers; compare implied capacity to the fortuna ceiling.
  (c) Latency-utilization curves: pooled elasticity of p90 latency w.r.t.
      load (congestion panel, endpoint FE) — the queueing-law signature;
      per-endpoint fits gate on panel length.
  (d) Hawkes branching ratio of the repricing event stream: children within
      24h on the same model per event. Ratio → 1 = self-sustaining price-war
      regime. MLE gates at 100 events; counting estimate reported now.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h21_reactions import load_events

log = logging.getLogger(__name__)


def _endpoint_frame() -> pd.DataFrame:
    rows = data.q(
        f"""
        select model_permaslug, provider_display_name as provider, endpoint_uuid, record_json
        from read_parquet('{data.table_glob("endpoint_stats_daily")}')
        where dt = (select max(dt) from read_parquet('{data.table_glob("endpoint_stats_daily")}'))
          and variant = 'standard'
        """
    ).df()
    recs = []
    for r in rows.itertuples(index=False):
        d = json.loads(r.record_json)
        f = d.get("fortuna") or {}
        sh = d.get("status_heuristics_1d") or {}
        st = d.get("stats") or {}
        tot = sum(v or 0 for v in sh.values())
        recs.append(
            {
                "model_permaslug": r.model_permaslug,
                "provider": r.provider,
                "endpoint_uuid": r.endpoint_uuid,
                "ceiling_rpm": f.get("capacity_ceiling_rpm"),
                "peak_rpm": f.get("recent_peak_rpm"),
                "req_1d": tot,
                "reject_1d": ((sh.get("rateLimited") or 0) + (sh.get("derankableError") or 0)) / tot
                if tot >= 500
                else np.nan,
                "p50_tps": st.get("p50_throughput"),
            }
        )
    return pd.DataFrame(recs)


# ------------------------------------------------------- (a) staffing rule


def staffing_test(ep: pd.DataFrame) -> dict:
    d = ep.dropna(subset=["ceiling_rpm", "peak_rpm"]).copy()
    d["load"] = d["req_1d"] / 1440  # avg rpm
    d = d[(d["load"] > 1) & (d["ceiling_rpm"] > d["load"])]
    d["buffer"] = d["ceiling_rpm"] - d["load"]
    if len(d) < 100:
        return {"gated": f"needs >=100 endpoints (have {len(d)})"}
    d["log_buffer"] = np.log(d["buffer"])
    d["log_load"] = np.log(d["load"])
    m = smf.ols("log_buffer ~ log_load", data=d).fit(cov_type="HC1")
    slope = float(m.params["log_load"])
    regime = (
        "QED (square-root staffing)"
        if 0.35 <= slope <= 0.65
        else "ED (proportional overcapacity)"
        if slope > 0.8
        else "QD (fixed buffer / quality-driven)"
        if slope < 0.2
        else "intermediate"
    )
    return {
        "n_endpoints": int(m.nobs),
        "buffer_load_slope": round(slope, 3),
        "se": round(float(m.bse["log_load"]), 3),
        "r2": round(float(m.rsquared), 3),
        "regime": regime,
        "caveat": "ceiling is router-estimated; slope not level is informative",
    }


# ------------------------------------------------------ (b) Erlang inversion


def _erlang_b(E: float, c: int) -> float:
    b = 1.0
    for k in range(1, c + 1):
        b = E * b / (k + E * b)
    return b


def erlang_inversion(ep: pd.DataFrame) -> dict:
    tpr = data.q(
        f"""
        select model_permaslug,
               sum(total_completion_tokens) / greatest(sum(request_count), 1) as toks_per_req
        from read_parquet('{data.table_glob("model_activity_daily")}')
        where variant = 'standard' group by 1
        """
    ).df()
    d = ep.merge(tpr, on="model_permaslug").dropna(subset=["reject_1d", "p50_tps", "ceiling_rpm"])
    d = d[(d["reject_1d"] > 0.001) & (d["p50_tps"] > 0) & (d["toks_per_req"] > 0)]
    rows = []
    for r in d.itertuples(index=False):
        service_s = min(600.0, r.toks_per_req / r.p50_tps)
        lam = r.req_1d / 86400
        E = lam * service_s
        if E <= 0:
            continue
        c = 1
        while _erlang_b(E, c) > r.reject_1d and c < 5000:
            c += max(1, c // 10)
        implied_rpm = c * 60 / service_s
        rows.append(
            {
                "provider": r.provider,
                "model_permaslug": r.model_permaslug,
                "offered_erlangs": round(E, 1),
                "implied_servers": c,
                "implied_capacity_rpm": round(implied_rpm, 1),
                "fortuna_ceiling_rpm": r.ceiling_rpm,
                "implied_over_fortuna": round(implied_rpm / r.ceiling_rpm, 2)
                if r.ceiling_rpm
                else np.nan,
            }
        )
    inv = pd.DataFrame(rows)
    if inv.empty:
        return {"gated": "no endpoints with measurable blocking + throughput"}, inv
    ratio = inv["implied_over_fortuna"].dropna()
    return {
        "n_endpoints": int(len(inv)),
        "median_implied_over_fortuna": round(float(ratio.median()), 2),
        "iqr": [round(float(ratio.quantile(q)), 2) for q in (0.25, 0.75)],
        "read": "≈1 = fortuna ceiling consistent with Erlang loss; >1 = ceiling conservative",
    }, inv


# --------------------------------------------- (c) latency-utilization curve


def latency_curve() -> dict:
    try:
        cg = data.q(
            f"""
            select endpoint_uuid, run_ts, p90_latency_ms, request_count_30m
            from read_parquet('{data.table_glob("congestion_intraday")}')
            where p90_latency_ms > 0 and request_count_30m > 10
            """
        ).df()
    except Exception:
        return {"gated": "no congestion panel"}
    n_per = cg.groupby("endpoint_uuid").size()
    keep = n_per[n_per >= 50].index
    d = cg[cg["endpoint_uuid"].isin(keep)].copy()
    if d["endpoint_uuid"].nunique() < 20:
        return {
            "gated": f"needs >=20 endpoints with 50+ ticks (have {d['endpoint_uuid'].nunique()})"
        }
    d["log_lat"] = np.log(d["p90_latency_ms"])
    d["log_load"] = np.log(d["request_count_30m"])
    d["log_lat_dm"] = d["log_lat"] - d.groupby("endpoint_uuid")["log_lat"].transform("mean")
    d["log_load_dm"] = d["log_load"] - d.groupby("endpoint_uuid")["log_load"].transform("mean")
    m = smf.ols("log_lat_dm ~ log_load_dm - 1", data=d).fit(
        cov_type="cluster", cov_kwds={"groups": d["endpoint_uuid"]}
    )
    return {
        "n_endpoints": int(d["endpoint_uuid"].nunique()),
        "n_ticks": int(len(d)),
        "latency_load_elasticity": round(float(m.params["log_load_dm"]), 3),
        "se": round(float(m.bse["log_load_dm"]), 3),
        "read": ">0 = congestion regime; ≈0 = capacity slack (latency set by model size, not load)",
    }


# -------------------------------------------------- (d) Hawkes branching


def hawkes_branching() -> dict:
    ev = load_events()
    if len(ev) < 5:
        return {"gated": f"needs events (have {len(ev)})"}
    ev = ev.sort_values("ts")
    children = 0
    for _model, g in ev.groupby("model_id"):
        ts = g["ts"].to_list()
        for i, t in enumerate(ts):
            children += sum(1 for u in ts[i + 1 :] if (u - t).total_seconds() <= 86400)
    n = len(ev)
    ratio = children / n
    return {
        "n_events": n,
        "children_within_24h_per_event": round(ratio, 2),
        "read": "counting estimate (upper bound; double-counts chains); ratio→1 = "
        "self-sustaining cascade regime. Exponential-kernel MLE gates at 100 events.",
        "mle_gate": f"{n}/100",
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    ep = _endpoint_frame()
    erlang_summary, inv = erlang_inversion(ep)
    if len(inv):
        save(inv, out_dir, "h37_erlang_inversion")
    results = {
        "staffing": staffing_test(ep),
        "erlang": erlang_summary,
        "latency_curve": latency_curve(),
        "hawkes": hawkes_branching(),
    }
    save_json(results, out_dir, "h37_summary")
    log.info("H37: %s", results)
    return results
