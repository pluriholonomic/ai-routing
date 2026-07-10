"""Render the screening memo from docs/memo_template.html + fresh analysis outputs.

The template's prose is the versioned research narrative (dated); this module
injects what changes daily:
  {{AS_OF}}          render date
  <!--LIVE_STATUS--> auto-generated dashboard of current market state
  /*__DATA__*/       chart series extracted from the latest analysis parquets

Run AFTER `orcap analyze` so the analysis/ directory is fresh. Output:
analysis/memo.html (pushed to the HF dataset under reports/ by CI; a local
scheduled job redeploys it to the claude.ai artifact).
"""

import html
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from .analysis import data

log = logging.getLogger(__name__)

TEMPLATE = Path("docs/memo_template.html")


def chart_data(analysis_dir: Path) -> dict:
    con = duckdb.connect()
    d: dict = {}
    d["h1_dlog"] = [
        round(r[0], 4)
        for r in con.sql(
            f"select dlog_price from '{analysis_dir}/h1_change_events.parquet' "
            "where changed and abs(dlog_price) < 3"
        ).fetchall()
    ]
    d["h2_scatter"] = [
        {"n": r[0], "cv": round(r[1], 4)}
        for r in con.sql(
            f"select n_providers, cv from '{analysis_dir}/h2_model_dispersion.parquet' "
            "where n_providers >= 2 and cv > 0"
        ).fetchall()
    ]
    d["h5_ranksize"] = [
        {"title": r[0], "tokens": float(r[1])}
        for r in con.sql(
            f"select app_title, total_tokens from '{analysis_dir}/h5_apps_snapshot.parquet' "
            "where scope='global' and section='popular' order by rank"
        ).fetchall()
    ]
    d["h6_ratios"] = [
        round(r[0], 4)
        for r in con.sql(
            f"select in_ratio from '{analysis_dir}/h6_effective_vs_listed.parquet' "
            "where in_ratio is not null and in_ratio between 0 and 1.5"
        ).fetchall()
    ]
    d["h10_rr"] = [
        round(r[0], 4)
        for r in con.sql(
            f"select reject_rate from '{analysis_dir}/h10_endpoint_ll.parquet' where not is_free"
        ).fetchall()
    ]

    # evolution figures (all optional — memo renders without them)
    try:
        tok = con.sql(
            f"select month_start, \"index\" from '{analysis_dir}/h7_token_index.parquet' order by 1"
        ).fetchall()
        gpu = con.sql(
            "select segment, period_start, usd_hr from 'data-static/gpu_index_periods.csv' "
            "where segment in ('marketplace','hyperscaler') order by 2"
        ).fetchall()
        series = {
            "Token index (matched-model)": [{"x": str(r[0])[:10], "y": round(r[1], 2)} for r in tok]
        }
        for seg in ("marketplace", "hyperscaler"):
            pts = [r for r in gpu if r[0] == seg]
            if pts:
                base = pts[0][2]
                series[f"GPU {seg} (H100)"] = [
                    {"x": str(r[1])[:10], "y": round(100 * r[2] / base, 2)} for r in pts
                ]
        d["evo_idx"] = series
    except Exception as exc:
        log.warning("evo_idx skipped: %s", exc)
    try:
        war = con.sql(
            f"""select provider_name, run_ts, price from '{analysis_dir}/h32_war_paths.parquet'
            order by run_ts"""
        ).fetchall()
        byp: dict = {}
        for prov, ts, p in war:
            byp.setdefault(prov, []).append({"x": ts, "y": round(p * 1e6, 3)})

        def _activity(pts: list) -> float:  # pick the lines that actually moved
            ys = [q["y"] for q in pts]
            import statistics

            return statistics.pstdev([__import__("math").log(v) for v in ys if v > 0])

        d["evo_war"] = dict(sorted(byp.items(), key=lambda kv: -_activity(kv[1]))[:6])
    except Exception as exc:
        log.warning("evo_war skipped: %s", exc)
    try:
        q = con.sql(
            f"""select run_ts, p_min, p50, p95 from '{analysis_dir}/h32_hot_quantile_path.parquet'
            order by run_ts"""
        ).fetchall()
        d["evo_quant"] = {
            lab: [{"x": r[0], "y": round(r[i] * 1e6, 3)} for r in q]
            for i, lab in [(1, "min quote"), (2, "median"), (3, "p95")]
        }
    except Exception as exc:
        log.warning("evo_quant skipped: %s", exc)
    return d


def _j(analysis_dir: Path, name: str) -> dict:
    p = analysis_dir / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _fmt(x, pct=False, nd=2):
    if x is None:
        return "—"
    return f"{x * 100:.1f}%" if pct else f"{x:.{nd}f}"


def monitor_badge() -> str:
    """Render source health without turning an unavailable ledger into a green claim."""
    try:
        from .quality import check

        healths = {
            "core": check("core"),
            "direct": check("direct"),
            "comparison": check("market"),
            "livepeer": check("livepeer"),
        }
    except Exception as exc:
        log.warning("monitor health unavailable: %s", exc)
        return '<p class="small sans">Monitor health: unavailable.</p>'
    state = ", ".join(f"{name} {health['overall']}" for name, health in healths.items())
    detail = "; ".join(
        ", ".join(f"{item['source']}: {item['state']}" for item in health["sources"])
        for health in healths.values()
    )
    return (
        '<p class="small sans">Monitor health: '
        f"<strong>{html.escape(state)}</strong> — {html.escape(detail)}.</p>"
    )


def live_status(analysis_dir: Path) -> str:
    h2 = _j(analysis_dir, "h2_summary")
    h4 = _j(analysis_dir, "h4_summary")
    h10 = _j(analysis_dir, "h10_summary")
    h13 = _j(analysis_dir, "h13_summary")
    h17 = _j(analysis_dir, "h17_summary")
    h42 = _j(analysis_dir, "h42_summary")
    h45 = _j(analysis_dir, "h45_shadow_execution_summary")
    h51 = _j(analysis_dir, "h51_summary")
    h52 = _j(analysis_dir, "h52_summary")
    h3 = _j(analysis_dir, "h3_summary")
    h42_data = h42.get("data") or {}
    h42_r2 = h42.get("r2_undercut_capture") or {}

    counts = data.q(
        f"""
        select count(*) n_rows, count(distinct run_ts) n_runs, max(run_ts) latest
        from read_parquet('{data.table_glob("endpoints_snapshots")}')
        """
    ).fetchone()
    events = data.q(
        f"""
        select count(*) from read_parquet('{data.table_glob("pricing_changes", "derived")}')
        where field like 'price%'
        """
    ).fetchone()[0]
    recent = data.q(
        f"""
        select changed_at_run_ts, model_id, provider_name,
               round(cast(old_value as double) * 1e6, 2),
               round(cast(new_value as double) * 1e6, 2)
        from read_parquet('{data.table_glob("pricing_changes", "derived")}')
        where field = 'price_completion'
        order by changed_at_run_ts desc limit 6
        """
    ).fetchall()

    tiles = [
        (f"{counts[0]:,}", "endpoint-price observations"),
        (str(events), "price-field change events"),
        (
            _fmt((h2.get("dispersion_fit") or {}).get("mean_cv_multiprovider"), pct=True),
            "cross-provider dispersion (CV)",
        ),
        (_fmt(h4.get("share_price_elasticity")), "routing share–price elasticity"),
        (_fmt(h10.get("reject_rate_p90"), pct=True), "p90 endpoint reject rate"),
        (_fmt(h13.get("share_exact_zero_basis"), pct=True), "venue quotes at exactly direct price"),
        ("$" + _fmt(h3.get("gpu_h100_usd_hr")), "H100 SXM $/hr (vast.ai median)"),
        (_fmt((h17.get("live") or {}).get("share_reversal"), pct=True), "live events reversed"),
        (str(h42_data.get("events_eligible_quote", "—")), "H42 eligible quote events"),
        (
            f"{h42_r2.get('n_events_with_balanced_intraday_window', '—')}/20",
            "H42 clean undercut windows",
        ),
        (str(h45.get("policy_groups", "—")), "H45 shadow-policy groups"),
        (_fmt(h51.get("median_switch_share"), pct=True), "H51 Gateway switch share"),
        (
            f"{h51.get('n_snapshot_runs', '—')}/1000",
            "H51 aggregate snapshots",
        ),
        (
            (
                _fmt(h52.get("median_cow_over_amm_gross_basis_pct")) + "%"
                if h52.get("median_cow_over_amm_gross_basis_pct") is not None
                else "—"
            ),
            "H52 CoW-over-AMM gross basis",
        ),
        (f"{h52.get('n_unique_cow_fills', '—')}/500", "H52 exact CoW fills"),
    ]
    tile_html = "".join(
        f'<div class="stat"><div class="v">{html.escape(str(v))}</div>'
        f'<div class="l">{html.escape(label)}</div></div>'
        for v, label in tiles
    )
    rows = "".join(
        f"<tr><td class='num'>{html.escape(ts[:8] + ' ' + ts[9:13])}</td>"
        f"<td>{html.escape(m)}</td><td>{html.escape(p)}</td>"
        f"<td class='num'>{o} → {n}</td></tr>"
        for ts, m, p, o, n in recent
    )
    return f"""
<h2>Live status <span class="sans" style="font-size:13px;color:var(--muted);font-weight:400">
auto-generated from the latest daily reanalysis</span></h2>
{monitor_badge()}
<div class="statrow">{tile_html}</div>
<table><thead><tr><th>UTC</th><th>Model</th><th>Provider</th>
<th class="num">$/Mtok out</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class="small sans">Most recent repricing events. All statistics recomputed nightly from
the full capture; the narrative sections below are the dated core screen.</p>
"""


def unavailable_live_status(analysis_dir: Path) -> str:
    """Keep locally computed event-study coverage visible during remote throttling."""
    h42 = _j(analysis_dir, "h42_summary")
    h42_data = h42.get("data") or {}
    h42_r2 = h42.get("r2_undercut_capture") or {}
    eligible = html.escape(str(h42_data.get("events_eligible_quote", "—")))
    windows = html.escape(str(h42_r2.get("n_events_with_balanced_intraday_window", "—")))
    return f"""
<h2>Live status <span class="sans" style="font-size:13px;color:var(--muted);font-weight:400">
temporarily unavailable</span></h2>
<p class="small sans">The historical analysis rendered, but the current source query failed.
Check monitor health before interpreting this as zero activity.</p>
<div class="statrow">
  <div class="stat"><div class="v">{eligible}</div>
  <div class="l">H42 eligible quote events</div></div>
  <div class="stat"><div class="v">{windows}/20</div>
  <div class="l">H42 clean undercut windows</div></div>
</div>
"""


def build(analysis_dir: Path = Path("analysis"), out: Path | None = None) -> Path:
    tpl = TEMPLATE.read_text()
    d = chart_data(analysis_dir)
    page = tpl.replace("/*__DATA__*/", json.dumps(d, separators=(",", ":")))
    try:
        status = live_status(analysis_dir)
    except Exception as exc:
        log.warning("live memo status unavailable: %s", exc)
        status = unavailable_live_status(analysis_dir)
    page = page.replace("<!--LIVE_STATUS-->", status)
    page = page.replace("{{AS_OF}}", datetime.now(UTC).strftime("%Y-%m-%d"))
    out = out or analysis_dir / "memo.html"
    out.write_text(page)
    log.info("memo rendered: %s (%d bytes)", out, len(page))
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print(build())


if __name__ == "__main__":
    main()
