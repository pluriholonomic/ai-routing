# ruff: noqa: E501
"""Build a self-contained, script-free Brown-MacKay/welfare results panel."""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

from .common import DEFAULT_OUT, save_json


def _json(out_dir: Path, name: str) -> dict:
    try:
        return json.loads((out_dir / f"{name}.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _fmt(value, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return html.escape(str(value))


def _badge(status: str) -> str:
    safe = html.escape(status or "not_run")
    klass = "good" if status == "supported_in_study_domain" else "warn"
    if status in {
        "rejected",
        "inconsistent_with_condition",
        "decentralization_conditions_not_satisfied",
    }:
        klass = "bad"
    return f'<span class="badge {klass}">{safe}</span>'


def _condition_table(conditions: list[dict]) -> str:
    body = "".join(
        "<tr>"
        f"<td><b>{html.escape(row.get('condition', ''))}</b></td>"
        f"<td>{html.escape(row.get('name', ''))}</td>"
        f"<td>{_badge(row.get('status', ''))}</td>"
        f"<td>{html.escape(row.get('evidence', ''))}</td>"
        "</tr>"
        for row in conditions
    )
    return (
        "<table><thead><tr><th>Condition</th><th>Requirement</th><th>Status</th>"
        f"<th>Current evidence</th></tr></thead><tbody>{body}</tbody></table>"
    )


def _scenario_table(out_dir: Path) -> str:
    path = out_dir / "wcv2_welfare_scenarios.parquet"
    if not path.exists():
        return "<p>No sensitivity scenarios were estimable.</p>"
    frame = pd.read_parquet(path)
    if frame.empty:
        return "<p>No sensitivity scenarios were estimable.</p>"
    columns = [
        "beta_source",
        "demand_elasticity",
        "cost_ratio",
        "price_change_pct",
        "demand_change_pct",
        "spend_change_pct",
        "provider_surplus_change_pct",
    ]
    body = "".join(
        "<tr>" + "".join(f"<td>{_fmt(row[column])}</td>" for column in columns) + "</tr>"
        for _, row in frame.iterrows()
    )
    labels = [
        "Cadence estimate",
        "Demand e",
        "Cost/price",
        "Price %",
        "Demand %",
        "Spend %",
        "Provider surplus %",
    ]
    return (
        "<table><thead><tr>"
        + "".join(f"<th>{label}</th>" for label in labels)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    bm1 = _json(out_dir, "bm1_summary")
    bm2 = _json(out_dir, "bm2_summary")
    bm3 = _json(out_dir, "bm3_summary")
    bm5 = _json(out_dir, "bm5_summary")
    wcv1 = _json(out_dir, "wcv1_summary")
    wcv3 = _json(out_dir, "wcv3_summary")
    verdict = _json(out_dir, "wcv5_summary")
    adjusted = bm3.get("quality_adjusted", {})
    focal = bm2.get("fast_response_after_slow_initiator", {})
    state = bm5.get("state_dependent_L3", {})
    strategic = bm5.get("strategic_L5", {})
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Pricing technology and welfare validation</title>
<style>
:root{{--ink:#172033;--muted:#637083;--paper:#f5f7fb;--card:#fff;--line:#dde3ec;--blue:#245eea;--red:#bb2e3c;--amber:#9a6500;--green:#177245}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 ui-sans-serif,system-ui,sans-serif}}
main{{max-width:1220px;margin:auto;padding:28px}} h1{{font-size:28px;margin:0 0 5px}} h2{{margin:28px 0 10px}} .sub{{color:var(--muted);margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}} .card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:0 2px 8px #1720330b}}
.metric{{font-size:26px;font-weight:750;margin:4px 0}} .label{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
.badge{{display:inline-block;border-radius:99px;padding:3px 8px;background:#fff3cf;color:var(--amber);font-size:12px}} .badge.good{{background:#def5e8;color:var(--green)}} .badge.bad{{background:#fde2e4;color:var(--red)}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line)}} th,td{{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}} th{{background:#edf1f7;font-size:12px}} tr:last-child td{{border-bottom:0}}
.note{{border-left:4px solid var(--blue);background:#e9efff;padding:12px 14px;margin:14px 0}} .small{{font-size:12px;color:var(--muted)}}
</style></head><body><main>
<h1>Brown–MacKay and welfare validation panel</h1>
<div class="sub">Authoritative captures · conservative claim boundaries · script-free inline report</div>
<div class="grid">
 <div class="card"><div class="label">Panel span</div><div class="metric">{_fmt(bm1.get('panel_span_days'))} days</div>{_badge(bm1.get('evidence_status',''))}</div>
 <div class="card"><div class="label">Completion-price changes</div><div class="metric">{bm1.get('n_price_changes','n/a')}</div><span class="small">{bm1.get('n_repricing_providers','n/a')} repricing providers</span></div>
 <div class="card"><div class="label">Quality-adjusted slow premium</div><div class="metric">{_fmt(adjusted.get('slow_over_fast_premium_pct'))}%</div><span class="small">CI on fast log-price: {_fmt((adjusted.get('ci95') or [None])[0],3)} to {_fmt((adjusted.get('ci95') or [None,None])[1],3)}</span></div>
 <div class="card"><div class="label">Fast-after-slow reaction uplift</div><div class="metric">{_fmt(100*(focal.get('uplift') or 0))} pp</div><span class="small">post minus equal pre-window placebo, n={focal.get('n','n/a')}</span></div>
 <div class="card"><div class="label">State-only holdout log loss</div><div class="metric">{_fmt(state.get('log_loss'),3)}</div></div>
 <div class="card"><div class="label">Strategic holdout log loss</div><div class="metric">{_fmt(strategic.get('log_loss'),3)}</div>{_badge(bm5.get('evidence_status',''))}</div>
</div>
<h2>C1–C10 condition audit</h2>{_condition_table(wcv1.get('conditions',[]))}
<h2>Cadence-neutral sensitivity bounds</h2>
<div class="note">These are partial-equilibrium sensitivity calculations, not structural welfare estimates.</div>
{_scenario_table(out_dir)}
<h2>Agent regret screens</h2>
<div class="grid">
 <div class="card"><div class="label">Median provider normalized regret</div><div class="metric">{_fmt(100*(wcv3.get('median_provider_normalized_regret') or 0))}%</div></div>
 <div class="card"><div class="label">Scenarios at ≤5% provider regret</div><div class="metric">{_fmt(100*(wcv3.get('share_provider_scenarios_below_5pct_regret') or 0))}%</div></div>
 <div class="card"><div class="label">User price-only regret</div><div class="metric">{_fmt(wcv3.get('token_weighted_user_price_only_regret_pct'))}%</div></div>
</div>
<h2>Integrated verdict</h2>
<div class="card"><p><b>Full conjecture:</b> {_badge(verdict.get('full_conjecture_verdict',''))}</p>
<p><b>Naive price-score model:</b> {_badge(verdict.get('naive_static_score_verdict',''))}</p>
<p><b>Brown–MacKay competitive null:</b> {_badge(verdict.get('brown_mackay_competitive_null',''))}</p>
<p class="small">{html.escape(verdict.get('claim_boundary',''))}</p></div>
</main></body></html>"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "welfare_validation_panel.html"
    path.write_text(document)
    summary = {"evidence_status": "rendered", "path": str(path), "script_free": True}
    save_json(summary, out_dir, "wcv_dashboard_summary")
    return summary
