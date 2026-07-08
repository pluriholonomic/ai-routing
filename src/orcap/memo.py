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
    return d


def _j(analysis_dir: Path, name: str) -> dict:
    p = analysis_dir / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _fmt(x, pct=False, nd=2):
    if x is None:
        return "—"
    return f"{x * 100:.1f}%" if pct else f"{x:.{nd}f}"


def live_status(analysis_dir: Path) -> str:
    h2 = _j(analysis_dir, "h2_summary")
    h4 = _j(analysis_dir, "h4_summary")
    h10 = _j(analysis_dir, "h10_summary")
    h13 = _j(analysis_dir, "h13_summary")
    h17 = _j(analysis_dir, "h17_summary")
    h3 = _j(analysis_dir, "h3_summary")

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
<div class="statrow">{tile_html}</div>
<table><thead><tr><th>UTC</th><th>Model</th><th>Provider</th><th class="num">$/Mtok out</th></tr></thead>
<tbody>{rows}</tbody></table>
<p class="small sans">Most recent repricing events. All statistics recomputed nightly from
the full capture; the narrative sections below are the dated core screen.</p>
"""


def build(analysis_dir: Path = Path("analysis"), out: Path | None = None) -> Path:
    tpl = TEMPLATE.read_text()
    d = chart_data(analysis_dir)
    page = tpl.replace("/*__DATA__*/", json.dumps(d, separators=(",", ":")))
    page = page.replace("<!--LIVE_STATUS-->", live_status(analysis_dir))
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
