"""H93 — cross-router price segmentation and policy-response panel.

The primary design holds the provider/model commodity fixed and compares its
posted quote across routers.  The longitudinal promotion gate then requires
repeated same-provider/model price changes and simulated cheapest-provider
switches.  Until that gate opens, H93 is a coverage and price-basis diagnostic,
not evidence about realized routing or a causal router-policy effect.
"""

from __future__ import annotations

import base64
import html as html_lib
import itertools
import json
import math
import re
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

INPUT_TOKENS = 1_000
OUTPUT_TOKENS = 500
MAX_SIMULTANEOUS_GAP_HOURS = 2.0
MAX_COINCIDENT_SHOCK_GAP_MINUTES = 90.0
PROMOTION_REQUIREMENTS = {
    "elapsed_days": 7.0,
    "routers_with_repeated_snapshots": 3,
    "minimum_snapshots_per_router": 48,
    "hf_linked_exact_matched_competitive_models": 10,
    "price_events": 30,
    "coincident_same_provider_model_events": 15,
    "simulated_route_switches": 15,
}


def _provider_key(value: Any) -> str:
    """Punctuation-only normalization; intentionally no provider alias map."""
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _model_key(value: Any) -> str:
    return str(value).strip().lower().rsplit("/", 1)[-1]


def exact_openrouter_model_map(models: pd.DataFrame) -> pd.DataFrame:
    """Admit a source suffix only when it identifies one official model id."""
    if models.empty or "id" not in models:
        return pd.DataFrame(
            columns=[
                "source_model_key",
                "openrouter_model_id",
                "openrouter_hugging_face_id",
                "match_count",
            ]
        )
    frame = models.loc[models["id"].notna()].copy()
    if "hugging_face_id" not in frame:
        frame["hugging_face_id"] = pd.NA
    frame = frame[["id", "hugging_face_id"]].drop_duplicates().copy()
    frame["source_model_key"] = frame["id"].map(_model_key)

    def first_hf_id(values: pd.Series) -> Any:
        present = values.dropna().astype(str)
        return present.iloc[0] if len(present) else pd.NA

    grouped = (
        frame.groupby("source_model_key", as_index=False)
        .agg(
            openrouter_model_id=("id", "first"),
            openrouter_hugging_face_id=("hugging_face_id", first_hf_id),
            match_count=("id", "nunique"),
        )
    )
    grouped.loc[grouped["match_count"].ne(1), "openrouter_model_id"] = pd.NA
    grouped.loc[
        grouped["match_count"].ne(1), "openrouter_hugging_face_id"
    ] = pd.NA
    return grouped


def attach_exact_model_matches(quotes: pd.DataFrame, models: pd.DataFrame) -> pd.DataFrame:
    out = quotes.copy()
    if out.empty:
        out["openrouter_model_id"] = pd.Series(dtype="string")
        out["model_match_status"] = pd.Series(dtype="string")
        return out
    out["source_model_key"] = out["source_model_key"].map(_model_key)
    mapping = exact_openrouter_model_map(models)
    out = out.merge(mapping, on="source_model_key", how="left", validate="many_to_one")
    out["model_match_status"] = np.select(
        [out["match_count"].eq(1), out["match_count"].gt(1)],
        ["exact_unique_official_suffix", "ambiguous_official_suffix"],
        default="no_official_suffix_match",
    )
    return out


def prepare_public_quotes(quotes: pd.DataFrame, models: pd.DataFrame) -> pd.DataFrame:
    out = attach_exact_model_matches(quotes, models)
    if out.empty:
        return out
    out["ts"] = pd.to_datetime(out["run_ts"], utc=True, errors="coerce")
    for column in ["price_input_usd_per_mtok", "price_output_usd_per_mtok"]:
        out[column] = pd.to_numeric(out.get(column), errors="coerce")
    out["scenario_cost_usd"] = (
        out["price_input_usd_per_mtok"] * INPUT_TOKENS
        + out["price_output_usd_per_mtok"] * OUTPUT_TOKENS
    ) / 1_000_000
    out.loc[out["scenario_cost_usd"].lt(0), "scenario_cost_usd"] = np.nan
    out["provider_key"] = out["provider_name"].map(_provider_key)
    return out


def latest_router_coverage(panel: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "router",
        "latest_run_ts",
        "rows",
        "priced_rows",
        "models",
        "providers",
        "multi_provider_models",
        "exact_matched_models",
        "exact_matched_competitive_models",
        "hf_linked_exact_matched_models",
        "hf_linked_exact_matched_competitive_models",
    ]
    if panel.empty:
        return pd.DataFrame(columns=columns)
    records: list[dict[str, Any]] = []
    for router, router_panel in panel.groupby("router", sort=True):
        latest_ts = router_panel["ts"].max()
        current = router_panel.loc[router_panel["ts"].eq(latest_ts)].copy()
        provider_counts = current.groupby("source_model_key")["provider_key"].nunique()
        exact = current.loc[current["model_match_status"].eq("exact_unique_official_suffix")]
        exact_provider_counts = exact.groupby("openrouter_model_id")["provider_key"].nunique()
        hf_linked = exact.loc[exact["openrouter_hugging_face_id"].notna()]
        hf_provider_counts = hf_linked.groupby("openrouter_model_id")["provider_key"].nunique()
        records.append(
            {
                "router": router,
                "latest_run_ts": latest_ts,
                "rows": len(current),
                "priced_rows": int(current["scenario_cost_usd"].notna().sum()),
                "models": int(current["source_model_key"].nunique()),
                "providers": int(current["provider_key"].nunique()),
                "multi_provider_models": int(provider_counts.ge(2).sum()),
                "exact_matched_models": int(exact["openrouter_model_id"].nunique()),
                "exact_matched_competitive_models": int(exact_provider_counts.ge(2).sum()),
                "hf_linked_exact_matched_models": int(
                    hf_linked["openrouter_model_id"].nunique()
                ),
                "hf_linked_exact_matched_competitive_models": int(
                    hf_provider_counts.ge(2).sum()
                ),
            }
        )
    return pd.DataFrame.from_records(records, columns=columns)


def price_event_rows(panel: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "router",
        "openrouter_model_id",
        "provider_key",
        "provider_name",
        "run_ts",
        "ts",
        "scenario_cost_usd",
        "previous_cost_usd",
        "log_price_change",
    ]
    eligible = panel.loc[
        panel["openrouter_model_id"].notna()
        & panel["provider_key"].ne("")
        & panel["scenario_cost_usd"].gt(0)
        & panel["ts"].notna()
    ].copy()
    if eligible.empty:
        return pd.DataFrame(columns=columns)
    eligible = eligible.sort_values("ts").drop_duplicates(
        ["router", "openrouter_model_id", "provider_key", "run_ts"], keep="last"
    )
    group = ["router", "openrouter_model_id", "provider_key"]
    eligible["previous_cost_usd"] = eligible.groupby(group)["scenario_cost_usd"].shift()
    eligible["log_price_change"] = np.log(
        eligible["scenario_cost_usd"] / eligible["previous_cost_usd"]
    )
    changed = eligible["previous_cost_usd"].notna() & eligible["log_price_change"].abs().gt(1e-12)
    return eligible.loc[changed, columns].reset_index(drop=True)


def simulated_cheapest_routes(panel: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "router",
        "run_ts",
        "ts",
        "openrouter_model_id",
        "eligible_provider_count",
        "minimum_scenario_cost_usd",
        "winner_provider_set",
    ]
    eligible = panel.loc[
        panel["openrouter_model_id"].notna()
        & panel["scenario_cost_usd"].gt(0)
        & panel["provider_key"].ne("")
    ].copy()
    if eligible.empty:
        return pd.DataFrame(columns=columns)
    records: list[dict[str, Any]] = []
    group_columns = ["router", "run_ts", "ts", "openrouter_model_id"]
    for keys, group in eligible.groupby(group_columns, dropna=False, sort=True):
        by_provider = group.groupby("provider_key", as_index=False)["scenario_cost_usd"].min()
        if len(by_provider) < 2:
            continue
        minimum = float(by_provider["scenario_cost_usd"].min())
        winners = sorted(
            by_provider.loc[
                np.isclose(by_provider["scenario_cost_usd"], minimum), "provider_key"
            ].tolist()
        )
        records.append(
            {
                "router": keys[0],
                "run_ts": keys[1],
                "ts": keys[2],
                "openrouter_model_id": keys[3],
                "eligible_provider_count": len(by_provider),
                "minimum_scenario_cost_usd": minimum,
                "winner_provider_set": ",".join(winners),
            }
        )
    return pd.DataFrame.from_records(records, columns=columns)


def simulated_route_switches(routes: pd.DataFrame) -> pd.DataFrame:
    if routes.empty:
        return routes.assign(previous_winner_provider_set=pd.Series(dtype="string"))
    out = routes.sort_values("ts").copy()
    groups = ["router", "openrouter_model_id"]
    out["previous_winner_provider_set"] = out.groupby(groups)["winner_provider_set"].shift()
    return out.loc[
        out["previous_winner_provider_set"].notna()
        & out["winner_provider_set"].ne(out["previous_winner_provider_set"])
    ].reset_index(drop=True)


def simultaneous_price_basis(panel: pd.DataFrame) -> pd.DataFrame:
    """Pair latest router quotes for an exact provider/model commodity."""
    columns = [
        "openrouter_model_id",
        "provider_key",
        "router_a",
        "router_b",
        "run_ts_a",
        "run_ts_b",
        "hours_apart",
        "scenario_cost_usd_a",
        "scenario_cost_usd_b",
        "input_price_usd_per_mtok_a",
        "input_price_usd_per_mtok_b",
        "output_price_usd_per_mtok_a",
        "output_price_usd_per_mtok_b",
        "log_price_ratio_a_to_b",
        "absolute_percent_wedge",
        "exact_input_output_price_match",
        "hf_linked_openrouter_model",
    ]
    eligible = panel.loc[
        panel["openrouter_model_id"].notna()
        & panel["scenario_cost_usd"].gt(0)
        & panel["provider_key"].ne("")
        & panel["ts"].notna()
    ].copy()
    if eligible.empty:
        return pd.DataFrame(columns=columns)
    latest = eligible.sort_values("ts").drop_duplicates(
        ["router", "openrouter_model_id", "provider_key"], keep="last"
    )
    records: list[dict[str, Any]] = []
    for (model, provider), group in latest.groupby(
        ["openrouter_model_id", "provider_key"], sort=True
    ):
        by_router = list(group.sort_values("router").itertuples(index=False))
        for left, right in itertools.combinations(by_router, 2):
            if left.router == right.router:
                continue
            hours = abs((left.ts - right.ts).total_seconds()) / 3_600
            if hours > MAX_SIMULTANEOUS_GAP_HOURS:
                continue
            log_ratio = math.log(left.scenario_cost_usd / right.scenario_cost_usd)
            records.append(
                {
                    "openrouter_model_id": model,
                    "provider_key": provider,
                    "router_a": left.router,
                    "router_b": right.router,
                    "run_ts_a": left.run_ts,
                    "run_ts_b": right.run_ts,
                    "hours_apart": hours,
                    "scenario_cost_usd_a": left.scenario_cost_usd,
                    "scenario_cost_usd_b": right.scenario_cost_usd,
                    "input_price_usd_per_mtok_a": left.price_input_usd_per_mtok,
                    "input_price_usd_per_mtok_b": right.price_input_usd_per_mtok,
                    "output_price_usd_per_mtok_a": left.price_output_usd_per_mtok,
                    "output_price_usd_per_mtok_b": right.price_output_usd_per_mtok,
                    "log_price_ratio_a_to_b": log_ratio,
                    "absolute_percent_wedge": 100 * (math.exp(abs(log_ratio)) - 1),
                    "exact_input_output_price_match": bool(
                        np.isclose(
                            left.price_input_usd_per_mtok,
                            right.price_input_usd_per_mtok,
                            rtol=1e-12,
                            atol=1e-12,
                        )
                        and np.isclose(
                            left.price_output_usd_per_mtok,
                            right.price_output_usd_per_mtok,
                            rtol=1e-12,
                            atol=1e-12,
                        )
                    ),
                    "hf_linked_openrouter_model": bool(
                        group["openrouter_hugging_face_id"].notna().any()
                    ),
                }
            )
    return pd.DataFrame.from_records(records, columns=columns)


def coincident_price_shocks(events: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "openrouter_model_id",
        "provider_key",
        "router_a",
        "router_b",
        "run_ts_a",
        "run_ts_b",
        "minutes_apart",
        "log_price_change_a",
        "log_price_change_b",
        "same_direction",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)
    records: list[dict[str, Any]] = []
    for (model, provider), group in events.groupby(
        ["openrouter_model_id", "provider_key"], sort=True
    ):
        routers = sorted(group["router"].unique())
        for router_a, router_b in itertools.combinations(routers, 2):
            left = group.loc[group["router"].eq(router_a)]
            right = group.loc[group["router"].eq(router_b)]
            for event in left.itertuples(index=False):
                gaps = (right["ts"] - event.ts).abs().dt.total_seconds() / 60
                if gaps.empty or float(gaps.min()) > MAX_COINCIDENT_SHOCK_GAP_MINUTES:
                    continue
                peer = right.loc[gaps.idxmin()]
                records.append(
                    {
                        "openrouter_model_id": model,
                        "provider_key": provider,
                        "router_a": router_a,
                        "router_b": router_b,
                        "run_ts_a": event.run_ts,
                        "run_ts_b": peer["run_ts"],
                        "minutes_apart": float(gaps.min()),
                        "log_price_change_a": float(event.log_price_change),
                        "log_price_change_b": float(peer["log_price_change"]),
                        "same_direction": bool(
                            np.sign(event.log_price_change) == np.sign(peer["log_price_change"])
                        ),
                    }
                )
    return pd.DataFrame.from_records(records, columns=columns).drop_duplicates(
        ["openrouter_model_id", "provider_key", "router_a", "router_b", "run_ts_a", "run_ts_b"]
    )


def wilson_interval(
    successes: int, trials: int, z: float = 1.959963984540054
) -> tuple[float, float]:
    if trials <= 0:
        return math.nan, math.nan
    share = successes / trials
    denominator = 1 + z**2 / trials
    center = (share + z**2 / (2 * trials)) / denominator
    half_width = z * math.sqrt(
        share * (1 - share) / trials + z**2 / (4 * trials**2)
    ) / denominator
    return center - half_width, center + half_width


def evidence_summary(panel: pd.DataFrame) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    coverage = latest_router_coverage(panel)
    events = price_event_rows(panel)
    routes = simulated_cheapest_routes(panel)
    switches = simulated_route_switches(routes)
    basis = simultaneous_price_basis(panel)
    coincident = coincident_price_shocks(events)

    valid_ts = panel["ts"].dropna() if "ts" in panel else pd.Series(dtype="datetime64[ns, UTC]")
    elapsed_days = (
        float((valid_ts.max() - valid_ts.min()).total_seconds() / 86_400)
        if len(valid_ts) >= 2
        else 0.0
    )
    snapshots = (
        panel.groupby("router")["run_ts"].nunique()
        if not panel.empty
        else pd.Series(dtype=int)
    )
    routers_repeated = int(snapshots.ge(2).sum())
    minimum_snapshots = int(snapshots.min()) if len(snapshots) else 0
    hf_linked_competitive = (
        int(coverage["hf_linked_exact_matched_competitive_models"].sum())
        if not coverage.empty
        else 0
    )
    observed = {
        "elapsed_days": elapsed_days,
        "routers_with_repeated_snapshots": routers_repeated,
        "minimum_snapshots_per_router": minimum_snapshots,
        "hf_linked_exact_matched_competitive_models": hf_linked_competitive,
        "price_events": len(events),
        "coincident_same_provider_model_events": len(coincident),
        "simulated_route_switches": len(switches),
    }
    gates = {
        name: observed[name] >= requirement
        for name, requirement in PROMOTION_REQUIREMENTS.items()
    }
    hf_basis = (
        basis.loc[basis["hf_linked_openrouter_model"]].copy()
        if not basis.empty
        else basis.copy()
    )
    hf_exact = (
        int(hf_basis["exact_input_output_price_match"].sum())
        if not hf_basis.empty
        else 0
    )
    hf_exact_ci = wilson_interval(hf_exact, len(hf_basis))
    basis_summary = {
        "simultaneous_same_provider_model_pairs": len(basis),
        "median_absolute_percent_wedge": (
            float(basis["absolute_percent_wedge"].median()) if not basis.empty else None
        ),
        "pairs_within_one_percent": (
            int(basis["absolute_percent_wedge"].le(1).sum()) if not basis.empty else 0
        ),
        "hf_linked_simultaneous_pairs": len(hf_basis),
        "hf_linked_exact_input_output_matches": hf_exact,
        "hf_linked_exact_match_share": (
            hf_exact / len(hf_basis) if len(hf_basis) else None
        ),
        "hf_linked_exact_match_share_wilson_95_ci": (
            [float(hf_exact_ci[0]), float(hf_exact_ci[1])]
            if len(hf_basis)
            else None
        ),
        "hf_linked_median_absolute_percent_wedge": (
            float(
                basis.loc[
                    basis["hf_linked_openrouter_model"], "absolute_percent_wedge"
                ].median()
            )
            if not hf_basis.empty
            else None
        ),
        "claim": (
            "cross-sectional posted-price segmentation diagnostic only; same provider labels "
            "do not prove identical contracts, capacity, or realized execution"
        ),
    }
    summary = {
        "hypothesis": "H93 cross-router same-provider/model pricing and policy response",
        "evidence_status": (
            "longitudinal_cross_router_gate_open" if all(gates.values())
            else "initial_cross_sectional_coverage_only"
        ),
        "scenario": {"input_tokens": INPUT_TOKENS, "output_tokens": OUTPUT_TOKENS},
        "observed": observed,
        "requirements": PROMOTION_REQUIREMENTS,
        "gates": gates,
        "coverage": json.loads(coverage.to_json(orient="records", date_format="iso")),
        "posted_price_basis": basis_summary,
        "claim_boundary": (
            "H93 currently observes posted public catalog quotes and simulated cheapest-provider "
            "choices. It does not observe market-wide flow, private eligibility, or realized "
            "routing. A causal router-policy claim additionally requires repeated common shocks, "
            "pre-trends, and owned-route validation."
        ),
    }
    frames = {
        "coverage": coverage,
        "price_events": events,
        "simulated_routes": routes,
        "simulated_switches": switches,
        "simultaneous_basis": basis,
        "coincident_shocks": coincident,
    }
    return summary, frames


def render_price_policy_panel(
    summary: dict[str, Any], frames: dict[str, pd.DataFrame], out_dir: Path
) -> tuple[Path, Path]:
    """Render the cross-sectional result and longitudinal promotion gates."""
    coverage = frames.get("coverage", pd.DataFrame()).copy()
    basis = frames.get("simultaneous_basis", pd.DataFrame()).copy()
    hf_basis = (
        basis.loc[basis.get("hf_linked_openrouter_model", False)].copy()
        if not basis.empty
        else basis.copy()
    )

    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "figure.facecolor": "white",
            "axes.facecolor": "#fbfcfe",
        }
    )
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2), constrained_layout=True)

    ax = axes[0]
    if coverage.empty:
        ax.text(0.5, 0.5, "No public catalog capture", ha="center", va="center")
    else:
        coverage = coverage.sort_values("router")
        y = np.arange(len(coverage))
        ax.barh(y + 0.22, coverage["models"], height=0.2, color="#94a3b8", label="listed")
        ax.barh(
            y,
            coverage["hf_linked_exact_matched_models"],
            height=0.2,
            color="#2563eb",
            label="HF-linked exact match",
        )
        ax.barh(
            y - 0.22,
            coverage["hf_linked_exact_matched_competitive_models"],
            height=0.2,
            color="#f59e0b",
            label="multi-provider",
        )
        ax.set_yticks(y, coverage["router"])
        ax.set_xlabel("model or router-model count")
        ax.legend(frameon=False, fontsize=7, loc="lower right")
    ax.set_title("A. Public catalog support", loc="left", fontweight="bold")
    ax.grid(axis="x", alpha=0.2)

    ax = axes[1]
    if hf_basis.empty:
        ax.text(0.5, 0.5, "No exact cross-router pairs", ha="center", va="center")
    else:
        hf_basis = hf_basis.sort_values("absolute_percent_wedge").reset_index(drop=True)
        plotted = hf_basis["absolute_percent_wedge"].clip(lower=0.03)
        colors = np.where(hf_basis["exact_input_output_price_match"], "#2563eb", "#dc2626")
        ax.scatter(np.arange(len(hf_basis)), plotted, c=colors, s=25, alpha=0.9)
        ax.set_yscale("log")
        ax.axhline(1.0, color="#64748b", linewidth=1, linestyle="--")
        ax.set_ylabel("absolute price wedge (%)")
        ax.set_xlabel("same provider-model pair")
        outliers = hf_basis.nlargest(3, "absolute_percent_wedge")
        for index, row in outliers.iterrows():
            if row["absolute_percent_wedge"] <= 1:
                continue
            ax.annotate(
                str(row["openrouter_model_id"]).rsplit("/", 1)[-1],
                (index, max(row["absolute_percent_wedge"], 0.03)),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=7,
            )
    ax.set_title("B. Law of one posted price", loc="left", fontweight="bold")
    ax.grid(axis="y", alpha=0.2, which="both")

    ax = axes[2]
    observed = summary.get("observed", {})
    requirements = summary.get("requirements", {})
    labels = [
        "days",
        "routers",
        "snapshots",
        "competitive\nrouter-models",
        "price events",
        "common shocks",
        "route switches",
    ]
    keys = list(requirements)
    progress = [
        min(1.0, float(observed.get(key, 0)) / float(requirements[key]))
        if float(requirements[key]) > 0
        else 0.0
        for key in keys
    ]
    y = np.arange(len(keys))
    ax.barh(y, progress, color=["#16a34a" if value >= 1 else "#cbd5e1" for value in progress])
    ax.set_yticks(y, labels[: len(keys)])
    ax.set_xlim(0, 1)
    ax.set_xlabel("fraction of promotion requirement")
    ax.invert_yaxis()
    for index, key in enumerate(keys):
        ax.text(
            min(0.98, progress[index] + 0.02),
            index,
            f"{observed.get(key, 0):g}/{requirements[key]:g}",
            va="center",
            fontsize=7,
        )
    ax.set_title("C. Longitudinal claim gate", loc="left", fontweight="bold")
    ax.grid(axis="x", alpha=0.2)

    fig.suptitle(
        "Cross-router posted prices: broad overlap, one initial open-weight exception",
        fontsize=13,
        fontweight="bold",
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / "h93_cross_router_price_policy_panel.png"
    pdf = out_dir / "h93_cross_router_price_policy_panel.pdf"
    fig.savefig(png, dpi=180)
    fig.savefig(pdf)
    plt.close(fig)
    return png, pdf


def render_html_dashboard(
    summary: dict[str, Any],
    frames: dict[str, pd.DataFrame],
    png: Path,
    out_dir: Path,
) -> Path:
    """Write a script-free, fully inline H93 dashboard."""
    coverage = frames.get("coverage", pd.DataFrame())
    basis = frames.get("simultaneous_basis", pd.DataFrame())
    outliers = (
        basis.loc[basis["absolute_percent_wedge"].gt(1)]
        .sort_values("absolute_percent_wedge", ascending=False)
        .head(12)
        if not basis.empty
        else basis
    )
    posted = summary.get("posted_price_basis", {})
    observed = summary.get("observed", {})
    interval = posted.get("hf_linked_exact_match_share_wilson_95_ci") or [None, None]

    def value(number: Any, *, percent: bool = False) -> str:
        if number is None or (isinstance(number, float) and not math.isfinite(number)):
            return "--"
        return f"{100 * float(number):.1f}%" if percent else f"{float(number):g}"

    def table(frame: pd.DataFrame, fields: list[tuple[str, str]]) -> str:
        if frame.empty:
            return '<p class="muted">No rows yet.</p>'
        header = "".join(f"<th>{html_lib.escape(label)}</th>" for _, label in fields)
        body = []
        for row in frame.itertuples(index=False):
            cells = "".join(
                f"<td>{html_lib.escape(str(getattr(row, field)))}</td>"
                for field, _ in fields
            )
            body.append(f"<tr>{cells}</tr>")
        return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"

    image_data = base64.b64encode(png.read_bytes()).decode("ascii")
    exact_matches = (
        f"{posted.get('hf_linked_exact_input_output_matches', 0)}/"
        f"{posted.get('hf_linked_simultaneous_pairs', 0)}"
    )
    interval_text = (
        f"{value(interval[0], percent=True)}–{value(interval[1], percent=True)}"
    )
    cards = [
        ("HF-linked exact matches", exact_matches),
        ("Exact-match share", value(posted.get("hf_linked_exact_match_share"), percent=True)),
        ("Wilson 95% interval", interval_text),
        ("Elapsed days", value(observed.get("elapsed_days"))),
        ("Price events", value(observed.get("price_events"))),
        ("Common shocks", value(observed.get("coincident_same_provider_model_events"))),
        ("Simulated switches", value(observed.get("simulated_route_switches"))),
    ]
    card_html = "".join(
        f'<div class="card"><div class="label">{html_lib.escape(label)}</div>'
        f'<div class="metric">{html_lib.escape(metric)}</div></div>'
        for label, metric in cards
    )
    coverage_table = table(
        coverage,
        [
            ("router", "Router"),
            ("rows", "Rows"),
            ("models", "Models"),
            ("providers", "Providers"),
            ("multi_provider_models", "Multi-provider"),
            ("hf_linked_exact_matched_models", "HF-linked exact"),
        ],
    )
    outlier_table = table(
        outliers,
        [
            ("openrouter_model_id", "Model"),
            ("provider_key", "Provider"),
            ("router_a", "Router A"),
            ("router_b", "Router B"),
            ("absolute_percent_wedge", "Wedge (%)"),
        ],
    )
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>H93 cross-router posted-price panel</title>
<style>
body{{font-family:Inter,ui-sans-serif,system-ui,sans-serif;margin:0;background:#f8fafc;color:#0f172a}}
main{{max-width:1180px;margin:auto;padding:28px}} h1{{margin-bottom:4px}} .muted{{color:#64748b}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:10px;margin:20px 0}}
.card,section{{background:white;border:1px solid #e2e8f0;border-radius:10px;padding:14px}}
.label{{font-size:12px;color:#64748b}} .metric{{font-size:24px;font-weight:700;margin-top:5px}}
section{{margin:14px 0}} img{{width:100%;height:auto}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;border-bottom:1px solid #e2e8f0;padding:8px}} th{{background:#f8fafc}}
.boundary{{border-left:4px solid #f59e0b}}
</style></head><body><main>
<h1>H93: cross-router law of one posted price</h1>
<p class="muted">{html_lib.escape(summary.get('evidence_status', ''))}</p>
<div class="cards">{card_html}</div>
<section><img alt="Cross-router price-policy plot"
src="data:image/png;base64,{image_data}"></section>
<section><h2>Current coverage</h2>{coverage_table}</section>
<section><h2>Price wedges above 1%</h2>{outlier_table}</section>
<section class="boundary"><h2>Claim boundary</h2>
<p>{html_lib.escape(summary.get('claim_boundary', ''))}</p></section>
</main></body></html>"""
    path = out_dir / "h93_cross_router_price_policy_panel.html"
    path.write_text(document)
    return path


def _load_public_quotes() -> pd.DataFrame:
    glob = data.table_glob("router_public_quote_snapshots")
    return data.q(f"select * from read_parquet('{glob}')").df()


def _load_latest_openrouter_models() -> pd.DataFrame:
    glob = data.table_glob("models_snapshots")
    return data.q(
        f"""
        with latest as (select max(run_ts) run_ts from read_parquet('{glob}'))
        select distinct models.id, models.hugging_face_id
        from read_parquet('{glob}') as models
        cross join latest
        where models.run_ts = latest.run_ts and models.id is not null
        """
    ).df()


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    try:
        quotes = _load_public_quotes()
        models = _load_latest_openrouter_models()
        panel = prepare_public_quotes(quotes, models)
        summary, frames = evidence_summary(panel)
    except Exception as exc:
        summary = {
            "hypothesis": "H93 cross-router same-provider/model pricing and policy response",
            "evidence_status": "public_router_catalog_panel_unavailable",
            "error": str(exc),
            "requirements": PROMOTION_REQUIREMENTS,
            "claim_boundary": "No H93 empirical claim is available without the public panel.",
        }
        frames = {}

    for name, frame in frames.items():
        save(frame, out_dir, f"h93_{name}")
    if frames:
        png, _ = render_price_policy_panel(summary, frames, out_dir)
        render_html_dashboard(summary, frames, png, out_dir)
    save_json(summary, out_dir, "h93_summary")
    return summary
