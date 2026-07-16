"""PM-5 — Tie microstructure: the gap density, tie formation, and focality.

Adapts three collusion-econometrics designs to the 5-min quote panel:
  - Chassang et al. missing-mass logic: pooled density of the relative gap
    to the cheapest quote; an atom at exactly 0 with missing mass at small
    undercuts is the coordination-by-matching signature (competitive
    leapfrogging predicts smooth mass through small undercuts).
  - Tie formation/breaking direction: who moved to create a tie (moving DOWN
    to match = competitive price-matching; a below-min provider moving UP to
    the min = coordination signature), and whether ties break by undercut
    (down) or retreat (up).
  - Knittel-Stango focality: do third-party quotes exhibit excess mass at the
    model author's first-party price relative to adjacent placebo levels?  A
    conditional random-label benchmark audits the mechanically high selected-
    tie author-match statistic.

  pm5_summary.json
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h19_provider_types import provider_family, serves_own

log = logging.getLogger(__name__)

EPS = 1e-12
AUTHOR_PLACEBO_TICK_MTOK = 0.1
AUTHOR_PLACEBO_MAX_OFFSET_TICKS = 20
AUTHOR_BOOTSTRAP_DRAWS = 20_000
AUTHOR_BOOTSTRAP_SEED = 20260716


def quote_ticks() -> pd.DataFrame:
    return data.q(
        f"""
        select run_ts, model_id, provider_name,
               min(price_completion) as price
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        where price_completion > 0 and model_id not like '%:%'
        group by 1, 2, 3
        """
    ).df()


def gap_density(q: pd.DataFrame) -> dict:
    m = q.groupby(["model_id", "run_ts"])["price"].transform("min")
    n = q.groupby(["model_id", "run_ts"])["price"].transform("size")
    rel = (q["price"] - m) / m
    rel = rel[(n >= 2)]
    nonmin = rel[rel > EPS]
    return {
        "share_ticks_at_exact_min_excl_holder": float(
            ((rel <= EPS).groupby([q["model_id"], q["run_ts"]]).sum() >= 2).mean()
        ),
        "gap_bins_pct": {
            "0_to_0.5": float(((nonmin > 0) & (nonmin <= 0.005)).mean()),
            "0.5_to_2": float(((nonmin > 0.005) & (nonmin <= 0.02)).mean()),
            "2_to_5": float(((nonmin > 0.02) & (nonmin <= 0.05)).mean()),
            "5_to_15": float(((nonmin > 0.05) & (nonmin <= 0.15)).mean()),
            "gt_15": float((nonmin > 0.15).mean()),
        },
        "n_nonmin_obs": int(len(nonmin)),
    }


def tie_events(q: pd.DataFrame) -> pd.DataFrame:
    """Tie formations/breaks at the minimum, with the mover's direction."""
    q = q.sort_values("run_ts")
    events = []
    for model, g in q.groupby("model_id"):
        piv = g.pivot_table(index="run_ts", columns="provider_name", values="price")
        if piv.shape[1] < 2 or len(piv) < 10:
            continue
        mins = piv.min(axis=1)
        tied = piv.eq(mins, axis=0).sum(axis=1) >= 2
        moved = piv.diff()
        for i in range(1, len(piv)):
            if tied.iloc[i] == tied.iloc[i - 1]:
                continue
            movers = moved.iloc[i].dropna()
            movers = movers[movers != 0]
            if len(movers) != 1:  # ambiguous multi-mover ticks skipped
                continue
            events.append(
                {
                    "model_id": model,
                    "kind": "formation" if tied.iloc[i] else "break",
                    "mover_direction": "down" if movers.iloc[0] < 0 else "up",
                }
            )
    return pd.DataFrame(events)


def _author_mask(model_id: str, providers: pd.Series) -> np.ndarray:
    author = str(model_id).split("/")[0].lower()
    return np.asarray(
        [serves_own(provider_family(str(provider)), author) for provider in providers],
        dtype=bool,
    )


def _latest_provider_quotes(q: pd.DataFrame) -> pd.DataFrame:
    if q.empty:
        return q.copy()
    latest = q[q["run_ts"].eq(q["run_ts"].max())].copy()
    latest["price"] = pd.to_numeric(latest["price"], errors="coerce")
    latest = latest[latest["price"].gt(0)].copy()
    return (
        latest.groupby(["model_id", "provider_name"], as_index=False, sort=True)["price"]
        .min()
        .sort_values(["model_id", "provider_name"], kind="mergesort")
    )


def author_price_match_panel(
    q: pd.DataFrame,
    *,
    placebo_tick_mtok: float = AUTHOR_PLACEBO_TICK_MTOK,
    max_offset_ticks: int = AUTHOR_PLACEBO_MAX_OFFSET_TICKS,
) -> pd.DataFrame:
    """All-market third-party mass at the author's price and placebo ticks.

    The selected-tie statistic is mechanically high when every displayed
    provider is tied.  This panel instead starts from every multi-provider
    model with at least one author-operated and one third-party endpoint.  It
    compares any exact third-party match at the lowest first-party quote with
    matches at symmetric, equally spaced placebo levels around that quote.
    """
    columns = [
        "model_id",
        "author",
        "n_providers",
        "n_author_endpoints",
        "n_third_party_endpoints",
        "author_price",
        "exact_third_party_match",
        "placebo_match_share",
        "exact_minus_placebo",
    ]
    latest = _latest_provider_quotes(q)
    if latest.empty:
        return pd.DataFrame(columns=columns)

    tick = float(placebo_tick_mtok) / 1_000_000
    offsets = [
        value
        for value in range(-int(max_offset_ticks), int(max_offset_ticks) + 1)
        if value != 0
    ]
    rows = []
    for model_id, group in latest.groupby("model_id", sort=True):
        own = _author_mask(str(model_id), group["provider_name"])
        if not own.any() or own.all():
            continue
        author_price = float(group.loc[own, "price"].min())
        third_party = group.loc[~own, "price"].to_numpy(dtype=float)
        exact = bool(np.isclose(third_party, author_price, rtol=1e-9, atol=1e-12).any())
        placebo = [
            bool(
                np.isclose(
                    third_party,
                    author_price + offset * tick,
                    rtol=1e-9,
                    atol=1e-12,
                ).any()
            )
            for offset in offsets
            if author_price + offset * tick > 0
        ]
        placebo_share = float(np.mean(placebo)) if placebo else 0.0
        rows.append(
            {
                "model_id": str(model_id),
                "author": str(model_id).split("/")[0].lower(),
                "n_providers": int(len(group)),
                "n_author_endpoints": int(own.sum()),
                "n_third_party_endpoints": int((~own).sum()),
                "author_price": author_price,
                "exact_third_party_match": float(exact),
                "placebo_match_share": placebo_share,
                "exact_minus_placebo": float(exact) - placebo_share,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _poisson_binomial_upper_tail(probabilities: list[float], observed: int) -> float | None:
    if not probabilities:
        return None
    pmf = np.asarray([1.0])
    for probability in probabilities:
        pmf = np.convolve(pmf, [1 - probability, probability])
    return float(pmf[int(observed) :].sum())


def selected_tie_random_label_audit(q: pd.DataFrame) -> dict:
    """Show how much of the legacy selected-tie statistic is mechanical.

    Conditional on a model having ``t`` tied minimum providers among ``n``,
    with ``r`` author-operated labels, a random placement of those labels hits
    the tied set with probability ``1-C(n-t,r)/C(n,r)``.  The benchmark is
    combinatorial rather than causal because author identity was not randomized.
    """
    latest = _latest_provider_quotes(q)
    probabilities: list[float] = []
    matches: list[bool] = []
    for model_id, group in latest.groupby("model_id", sort=True):
        minimum = float(group["price"].min())
        tied = np.isclose(group["price"], minimum, rtol=1e-9, atol=1e-12)
        n_tied = int(tied.sum())
        own = _author_mask(str(model_id), group["provider_name"])
        n, n_author = int(len(group)), int(own.sum())
        if n < 2 or n_tied < 2 or n_author < 1:
            continue
        no_hit = (
            math.comb(n - n_tied, n_author) / math.comb(n, n_author)
            if n - n_tied >= n_author
            else 0.0
        )
        probabilities.append(float(1 - no_hit))
        matches.append(bool((tied & own).any()))

    observed = int(sum(matches))
    n_models = int(len(matches))
    expected = float(sum(probabilities))
    return {
        "n_selected_tied_models": n_models,
        "observed_author_at_tied_min": observed,
        "observed_share": observed / n_models if n_models else None,
        "random_label_expected_count": expected,
        "random_label_expected_share": expected / n_models if n_models else None,
        "poisson_binomial_upper_tail_p": _poisson_binomial_upper_tail(
            probabilities, observed
        ),
        "interpretation": (
            "A high selected-tie match rate is non-discriminating when the random-label "
            "expectation is also high; it does not by itself identify an author focal point."
        ),
    }


def author_cluster_inference(
    panel: pd.DataFrame,
    *,
    bootstrap_draws: int = AUTHOR_BOOTSTRAP_DRAWS,
    seed: int = AUTHOR_BOOTSTRAP_SEED,
) -> dict:
    if panel.empty:
        return {
            "n_models": 0,
            "n_author_clusters": 0,
            "exact_match_share": None,
            "placebo_match_share": None,
            "exact_minus_placebo": None,
            "author_cluster_bootstrap_ci95": [None, None],
            "positive_author_clusters": 0,
            "negative_author_clusters": 0,
            "author_sign_test_p_one_sided": None,
            "leave_one_author_out_excess_range": [None, None],
        }

    grouped = panel.groupby("author", sort=True)["exact_minus_placebo"]
    cluster_sums = grouped.sum().to_numpy(dtype=float)
    cluster_counts = grouped.size().to_numpy(dtype=float)
    cluster_means = grouped.mean().to_numpy(dtype=float)
    n_clusters = int(len(cluster_sums))
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n_clusters, size=(int(bootstrap_draws), n_clusters))
    boot = cluster_sums[draws].sum(axis=1) / cluster_counts[draws].sum(axis=1)
    nonzero = cluster_means[~np.isclose(cluster_means, 0.0)]
    positive = int((nonzero > 0).sum())

    total_sum, total_n = float(cluster_sums.sum()), float(cluster_counts.sum())
    leave_one_out = [
        (total_sum - value_sum) / (total_n - value_n)
        for value_sum, value_n in zip(cluster_sums, cluster_counts, strict=True)
        if total_n > value_n
    ]
    return {
        "n_models": int(len(panel)),
        "n_author_clusters": n_clusters,
        "exact_match_share": float(panel["exact_third_party_match"].mean()),
        "placebo_match_share": float(panel["placebo_match_share"].mean()),
        "exact_minus_placebo": float(panel["exact_minus_placebo"].mean()),
        "author_cluster_bootstrap_draws": int(bootstrap_draws),
        "author_cluster_bootstrap_seed": int(seed),
        "author_cluster_bootstrap_ci95": [
            float(value) for value in np.quantile(boot, [0.025, 0.975])
        ],
        "positive_author_clusters": positive,
        "negative_author_clusters": int((nonzero < 0).sum()),
        "zero_author_clusters": int(n_clusters - len(nonzero)),
        "author_sign_test_p_one_sided": float(
            binomtest(positive, len(nonzero), 0.5, alternative="greater").pvalue
        )
        if len(nonzero)
        else None,
        "leave_one_author_out_excess_range": [
            float(min(leave_one_out)), float(max(leave_one_out))
        ]
        if leave_one_out
        else [None, None],
    }


def author_focality_audit(q: pd.DataFrame) -> dict:
    primary = author_price_match_panel(q)
    sensitivity = {}
    for tick in (0.01, 0.1, 0.5, 1.0):
        panel = author_price_match_panel(q, placebo_tick_mtok=tick)
        sensitivity[f"{tick:g}"] = {
            "placebo_tick_usd_per_million_tokens": tick,
            "n_models": int(len(panel)),
            "exact_match_share": (
                float(panel["exact_third_party_match"].mean()) if len(panel) else None
            ),
            "placebo_match_share": (
                float(panel["placebo_match_share"].mean()) if len(panel) else None
            ),
            "exact_minus_placebo": (
                float(panel["exact_minus_placebo"].mean()) if len(panel) else None
            ),
        }
    return {
        "evidence_status": "post_freeze_exploratory_confirmatory_gate_registered",
        "latest_run_ts": str(q["run_ts"].max()) if len(q) else None,
        "primary_placebo_tick_usd_per_million_tokens": AUTHOR_PLACEBO_TICK_MTOK,
        "max_offset_ticks_each_direction": AUTHOR_PLACEBO_MAX_OFFSET_TICKS,
        "all_market_author_price_atom": author_cluster_inference(primary),
        "placebo_grid_sensitivity": sensitivity,
        "selected_tie_random_label_benchmark": selected_tie_random_label_audit(q),
        "confirmatory_gate": (
            "Recompute without specification changes on the earliest 30-date prefixes "
            "of both frozen quote vintages; cluster by author and retain all four grids."
        ),
        "claim_boundary": (
            "The all-market atom rejects adjacent equally spaced focal levels for the "
            "observed author families. It does not identify why third parties match, "
            "whether the author caused the match, or effects outside those families."
        ),
    }


def focality(q: pd.DataFrame) -> dict:
    last = q[q["run_ts"] == q["run_ts"].max()]
    m = last.groupby("model_id")["price"].transform("min")
    n = last.groupby("model_id")["provider_name"].transform("size")
    tied_rows = last[(last["price"] <= m * (1 + 1e-9)) & (n >= 2)]
    tie_levels = tied_rows.groupby("model_id")["price"].first()
    per_mtok = tie_levels * 1e6
    identity = author_focality_audit(q)
    selected = identity["selected_tie_random_label_benchmark"]
    return {
        "n_tied_models_latest_tick": int(len(tie_levels)),
        "share_tie_levels_round_tenth_mtok": float(
            np.isclose(per_mtok * 10, np.round(per_mtok * 10), atol=1e-6).mean()
        )
        if len(per_mtok)
        else None,
        "n_tied_models_with_first_party_quote": selected["n_selected_tied_models"],
        "share_ties_at_first_party_price": selected["observed_share"],
        "selected_tie_identity_status": "non_discriminating_against_random_label",
        "author_identity_audit": identity,
    }


def run(
    out_dir: Path = DEFAULT_OUT,
    *,
    q: pd.DataFrame | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    q = quote_ticks() if q is None else q.copy()
    if start_date is not None or end_date is not None:
        dates = pd.to_datetime(q["run_ts"], utc=True, errors="coerce").dt.strftime(
            "%Y-%m-%d"
        )
        if start_date is not None:
            q = q[dates.ge(str(start_date))].copy()
            dates = dates.loc[q.index]
        if end_date is not None:
            q = q[dates.le(str(end_date))].copy()
    save(author_price_match_panel(q), out_dir, "pm5_author_price_atom")
    ties = tie_events(q)
    formation = ties[ties["kind"] == "formation"] if len(ties) else pd.DataFrame()
    brk = ties[ties["kind"] == "break"] if len(ties) else pd.DataFrame()
    summary = {
        "evidence_status": "provisional_descriptive",
        "gap_density": gap_density(q),
        "tie_formation": {
            "n": int(len(formation)),
            "share_formed_by_downward_move": float((formation["mover_direction"] == "down").mean())
            if len(formation)
            else None,
        },
        "tie_break": {
            "n": int(len(brk)),
            "share_broken_by_downward_move": float((brk["mover_direction"] == "down").mean())
            if len(brk)
            else None,
        },
        "focality": focality(q),
        "signatures": {
            "coordination": "atom at 0 + missing mass at small undercuts; ties formed by "
            "upward moves; ties at first-party focal price; breaks upward",
            "competition": "smooth small-undercut mass; ties formed downward; breaks downward",
        },
        "claim_boundary": (
            "Single-mover tie events only (multi-mover ticks skipped); author identity "
            "uses the shared provider-family alias crosswalk; selected-tie identity is "
            "non-discriminating under its random-label benchmark; the 5-min grid leaves "
            "sub-tick sequencing unobserved."
        ),
    }
    save_json(summary, out_dir, "pm5_summary")
    return summary
