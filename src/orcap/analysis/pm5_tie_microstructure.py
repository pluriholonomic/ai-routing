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
  - Focality falsification ladder: adjacent levels detect an exact atom; endpoint-
    label randomization tests whether author identity is special; a matched global
    menu tests whether lagged exact landings exceed common asynchronous price menus.

  pm5_summary.json
"""

from __future__ import annotations

import logging
import math
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from . import data
from .common import DEFAULT_OUT, save, save_json
from .h19_provider_types import provider_family, serves_own
from .market_scope import paid_model_sql

log = logging.getLogger(__name__)

EPS = 1e-12
AUTHOR_PLACEBO_TICK_MTOK = 0.1
AUTHOR_PLACEBO_MAX_OFFSET_TICKS = 20
AUTHOR_BOOTSTRAP_DRAWS = 20_000
AUTHOR_BOOTSTRAP_SEED = 20260716
REFERENCE_MAX_GAP_MINUTES = 15
REFERENCE_GLOBAL_BAND_FACTOR = 1.25
REFERENCE_HISTORICAL_WASHOUT_HOURS = 24
REFERENCE_BOOTSTRAP_DRAWS = 20_000
REFERENCE_BOOTSTRAP_SEED = 20260716


def quote_ticks() -> pd.DataFrame:
    return data.q(
        f"""
        select run_ts, model_id, provider_name,
               min(price_completion) as price
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        where price_completion > 0 and {paid_model_sql("model_id")}
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


def author_anchor_symmetry_panel(q: pd.DataFrame) -> pd.DataFrame:
    """Compare the author endpoint with exchangeable provider anchors.

    Adjacent empty grid points are not a sufficient identity null when providers
    draw prices from a common discrete menu.  This panel preserves every model's
    realized price multiplicities and asks whether the unique author endpoint is
    more likely to occupy a shared price than a uniformly selected endpoint.
    Pair-density columns additionally compare author--third-party equality with
    equality among third parties, avoiding the reciprocal-tie artifact.
    """
    columns = [
        "model_id",
        "author",
        "n_providers",
        "n_third_party_endpoints",
        "author_shared_price",
        "shared_endpoint_count",
        "random_anchor_shared_probability",
        "author_minus_random_anchor",
        "third_party_shared_share",
        "author_minus_third_party_shared",
        "author_third_party_pair_share",
        "third_party_pair_share",
        "pair_density_difference",
    ]
    latest = _latest_provider_quotes(q)
    if latest.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for model_id, group in latest.groupby("model_id", sort=True):
        own = _author_mask(str(model_id), group["provider_name"])
        if int(own.sum()) != 1 or own.all():
            continue
        prices = group["price"].to_numpy(dtype=float)
        equal = np.isclose(
            prices[:, None],
            prices[None, :],
            rtol=1e-9,
            atol=1e-12,
        )
        np.fill_diagonal(equal, False)
        shared = equal.any(axis=1)
        author_index = int(np.flatnonzero(own)[0])
        third_party = np.flatnonzero(~own)
        author_pair_share = float(equal[author_index, third_party].mean())
        third_party_pair_share = math.nan
        if len(third_party) >= 2:
            pairs = equal[np.ix_(third_party, third_party)]
            third_party_pair_share = float(
                pairs[np.triu_indices(len(third_party), 1)].mean()
            )
        random_probability = float(shared.mean())
        author_shared = float(shared[author_index])
        third_party_shared = float(shared[third_party].mean())
        rows.append(
            {
                "model_id": str(model_id),
                "author": str(model_id).split("/")[0].lower(),
                "n_providers": int(len(group)),
                "n_third_party_endpoints": int(len(third_party)),
                "author_shared_price": author_shared,
                "shared_endpoint_count": int(shared.sum()),
                "random_anchor_shared_probability": random_probability,
                "author_minus_random_anchor": author_shared - random_probability,
                "third_party_shared_share": third_party_shared,
                "author_minus_third_party_shared": author_shared - third_party_shared,
                "author_third_party_pair_share": author_pair_share,
                "third_party_pair_share": third_party_pair_share,
                "pair_density_difference": (
                    author_pair_share - third_party_pair_share
                    if pd.notna(third_party_pair_share)
                    else math.nan
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _clustered_mean_inference(
    panel: pd.DataFrame,
    *,
    value_column: str,
    cluster_column: str,
    bootstrap_draws: int = REFERENCE_BOOTSTRAP_DRAWS,
    seed: int = REFERENCE_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    if value_column not in panel or cluster_column not in panel:
        return {
            "n_observations": 0,
            "n_clusters": 0,
            "mean": None,
            "cluster_bootstrap_ci95": [None, None],
            "leave_one_cluster_out_range": [None, None],
        }
    usable = panel.dropna(subset=[value_column, cluster_column]).copy()
    if usable.empty:
        return {
            "n_observations": 0,
            "n_clusters": 0,
            "mean": None,
            "cluster_bootstrap_ci95": [None, None],
            "leave_one_cluster_out_range": [None, None],
        }
    grouped = usable.groupby(cluster_column, sort=True)[value_column]
    sums = grouped.sum().to_numpy(dtype=float)
    counts = grouped.size().to_numpy(dtype=float)
    n_clusters = int(len(sums))
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n_clusters, size=(int(bootstrap_draws), n_clusters))
    boot = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    total_sum = float(sums.sum())
    total_count = float(counts.sum())
    leave_one_out = [
        (total_sum - cluster_sum) / (total_count - cluster_count)
        for cluster_sum, cluster_count in zip(sums, counts, strict=True)
        if total_count > cluster_count
    ]
    return {
        "n_observations": int(len(usable)),
        "n_clusters": n_clusters,
        "mean": float(usable[value_column].mean()),
        "bootstrap_draws": int(bootstrap_draws),
        "bootstrap_seed": int(seed),
        "cluster_bootstrap_ci95": [
            float(value) for value in np.quantile(boot, [0.025, 0.975])
        ],
        "leave_one_cluster_out_range": (
            [float(min(leave_one_out)), float(max(leave_one_out))]
            if leave_one_out
            else [None, None]
        ),
    }


def _clustered_difference_in_means(
    panel: pd.DataFrame,
    *,
    outcome_column: str,
    group_column: str,
    cluster_column: str,
    bootstrap_draws: int = REFERENCE_BOOTSTRAP_DRAWS,
    seed: int = REFERENCE_BOOTSTRAP_SEED,
) -> dict[str, Any]:
    columns = [outcome_column, group_column, cluster_column]
    if any(column not in panel for column in columns):
        return {
            "n_observations": 0,
            "n_clusters": 0,
            "group_one_mean": None,
            "group_zero_mean": None,
            "difference": None,
            "cluster_bootstrap_ci95": [None, None],
            "leave_one_cluster_out_range": [None, None],
        }
    usable = panel.dropna(subset=columns).copy()
    usable = usable[usable[group_column].isin([0, 1])]
    if usable.empty or usable[group_column].nunique() < 2:
        return {
            "n_observations": int(len(usable)),
            "n_clusters": int(usable[cluster_column].nunique()),
            "group_one_mean": None,
            "group_zero_mean": None,
            "difference": None,
            "cluster_bootstrap_ci95": [None, None],
            "leave_one_cluster_out_range": [None, None],
        }

    grouped = []
    for cluster, frame in usable.groupby(cluster_column, sort=True):
        one = frame[frame[group_column].eq(1)][outcome_column]
        zero = frame[frame[group_column].eq(0)][outcome_column]
        grouped.append(
            {
                "cluster": cluster,
                "one_sum": float(one.sum()),
                "one_n": int(len(one)),
                "zero_sum": float(zero.sum()),
                "zero_n": int(len(zero)),
            }
        )

    def contrast(rows: list[dict[str, Any]]) -> float | None:
        one_n = sum(int(row["one_n"]) for row in rows)
        zero_n = sum(int(row["zero_n"]) for row in rows)
        if one_n == 0 or zero_n == 0:
            return None
        one = sum(float(row["one_sum"]) for row in rows) / one_n
        zero = sum(float(row["zero_sum"]) for row in rows) / zero_n
        return float(one - zero)

    estimate = contrast(grouped)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(grouped), size=(int(bootstrap_draws), len(grouped)))
    boot = []
    for draw in draws:
        value = contrast([grouped[int(index)] for index in draw])
        if value is not None:
            boot.append(value)
    leave_one_out = [
        value
        for index in range(len(grouped))
        if (value := contrast(grouped[:index] + grouped[index + 1 :])) is not None
    ]
    group_one = usable[usable[group_column].eq(1)][outcome_column]
    group_zero = usable[usable[group_column].eq(0)][outcome_column]
    return {
        "n_observations": int(len(usable)),
        "n_clusters": int(len(grouped)),
        "group_one_mean": float(group_one.mean()),
        "group_zero_mean": float(group_zero.mean()),
        "difference": estimate,
        "bootstrap_draws": int(bootstrap_draws),
        "bootstrap_seed": int(seed),
        "cluster_bootstrap_ci95": (
            [float(value) for value in np.quantile(boot, [0.025, 0.975])]
            if boot
            else [None, None]
        ),
        "leave_one_cluster_out_range": (
            [float(min(leave_one_out)), float(max(leave_one_out))]
            if leave_one_out
            else [None, None]
        ),
    }


def author_anchor_randomization_audit(q: pd.DataFrame) -> dict[str, Any]:
    """Exact endpoint-label benchmark for the all-market author atom."""
    panel = author_anchor_symmetry_panel(q)
    probabilities = panel["random_anchor_shared_probability"].tolist()
    observed = int(panel["author_shared_price"].sum()) if len(panel) else 0
    expected = float(sum(probabilities))
    return {
        "n_models": int(len(panel)),
        "observed_author_shared_count": observed,
        "observed_author_shared_share": (
            float(panel["author_shared_price"].mean()) if len(panel) else None
        ),
        "random_anchor_expected_count": expected,
        "random_anchor_expected_share": expected / len(panel) if len(panel) else None,
        "poisson_binomial_upper_tail_p": _poisson_binomial_upper_tail(
            probabilities, observed
        ),
        "author_minus_random_anchor": _clustered_mean_inference(
            panel,
            value_column="author_minus_random_anchor",
            cluster_column="author",
        ),
        "author_minus_third_party_anchor": _clustered_mean_inference(
            panel,
            value_column="author_minus_third_party_shared",
            cluster_column="author",
        ),
        "pair_density_difference": _clustered_mean_inference(
            panel,
            value_column="pair_density_difference",
            cluster_column="author",
        ),
        "interpretation": (
            "This null preserves each model's complete realized price multiset. "
            "Failure to beat it means exact price mass is generic provider-price "
            "clustering, not evidence that author identity is the focal mechanism."
        ),
    }


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


def _normalized_quote_snapshots(q: pd.DataFrame) -> pd.DataFrame:
    columns = ["run_ts", "model_id", "provider_name", "price"]
    if q.empty:
        return pd.DataFrame(columns=columns)
    frame = q[columns].copy()
    frame["run_ts"] = pd.to_datetime(frame["run_ts"], utc=True, errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame = frame.dropna(subset=["run_ts", "model_id", "provider_name", "price"])
    frame = frame[frame["price"].gt(0)]
    return frame.groupby(
        ["run_ts", "model_id", "provider_name"],
        as_index=False,
        sort=True,
    )["price"].min()


def isolated_quote_change_events(
    q: pd.DataFrame,
    *,
    max_gap_minutes: int = REFERENCE_MAX_GAP_MINUTES,
    placebo_tick_mtok: float = AUTHOR_PLACEBO_TICK_MTOK,
    max_offset_ticks: int = AUTHOR_PLACEBO_MAX_OFFSET_TICKS,
) -> pd.DataFrame:
    """Isolate one-provider revisions with an observed strictly prior rival set."""
    columns = [
        "model_id",
        "provider_name",
        "previous_run_ts",
        "run_ts",
        "gap_minutes",
        "old_price",
        "new_price",
        "direction",
        "n_rival_quotes",
        "exact_lagged_rival_match",
        "adjacent_placebo_match_share",
        "exact_minus_adjacent_placebo",
    ]
    frame = _normalized_quote_snapshots(q)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    tick = float(placebo_tick_mtok) / 1_000_000
    offsets = [
        value
        for value in range(-int(max_offset_ticks), int(max_offset_ticks) + 1)
        if value != 0
    ]
    max_gap_seconds = int(max_gap_minutes) * 60
    rows: list[dict[str, Any]] = []
    for model_id, group in frame.groupby("model_id", sort=True):
        providers = pd.Index(sorted(group["provider_name"].astype(str).unique()))
        if len(providers) < 2:
            continue
        pivot = (
            group.pivot_table(
                index="run_ts",
                columns="provider_name",
                values="price",
                aggfunc="min",
            )
            .sort_index()
            .reindex(columns=providers)
        )
        values = pivot.to_numpy(dtype=float)
        for position in range(1, len(pivot)):
            gap = pivot.index[position] - pivot.index[position - 1]
            if gap.total_seconds() > max_gap_seconds:
                continue
            observed_twice = np.isfinite(values[position - 1]) & np.isfinite(
                values[position]
            )
            changed = observed_twice & ~np.isclose(
                values[position],
                values[position - 1],
                rtol=1e-9,
                atol=1e-12,
            )
            movers = np.flatnonzero(changed)
            if len(movers) != 1:
                continue
            mover = int(movers[0])
            rival_mask = np.arange(len(providers)) != mover
            rival_prices = values[position - 1][
                rival_mask & np.isfinite(values[position - 1])
            ]
            if not len(rival_prices):
                continue
            old_price = float(values[position - 1, mover])
            new_price = float(values[position, mover])
            exact = bool(
                np.isclose(
                    rival_prices,
                    new_price,
                    rtol=1e-9,
                    atol=1e-12,
                ).any()
            )
            placebo = [
                bool(
                    np.isclose(
                        rival_prices + offset * tick,
                        new_price,
                        rtol=1e-9,
                        atol=1e-12,
                    ).any()
                )
                for offset in offsets
            ]
            placebo_share = float(np.mean(placebo)) if placebo else 0.0
            rows.append(
                {
                    "model_id": str(model_id),
                    "provider_name": str(providers[mover]),
                    "previous_run_ts": pivot.index[position - 1],
                    "run_ts": pivot.index[position],
                    "gap_minutes": float(gap.total_seconds() / 60),
                    "old_price": old_price,
                    "new_price": new_price,
                    "direction": "down" if new_price < old_price else "up",
                    "n_rival_quotes": int(len(rival_prices)),
                    "exact_lagged_rival_match": float(exact),
                    "adjacent_placebo_match_share": placebo_share,
                    "exact_minus_adjacent_placebo": float(exact) - placebo_share,
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _hypergeometric_any_hit_probability(*, population: int, hits: int, draws: int) -> float:
    if population <= 0 or draws <= 0 or hits <= 0:
        return 0.0
    draws = min(int(draws), int(population))
    misses = int(population) - int(hits)
    no_hit = math.comb(misses, draws) / math.comb(population, draws) if misses >= draws else 0.0
    return float(1 - no_hit)


def attach_global_price_menu_null(
    events: pd.DataFrame,
    q: pd.DataFrame,
    *,
    band_factor: float = REFERENCE_GLOBAL_BAND_FACTOR,
) -> pd.DataFrame:
    """Attach a matched common-menu probability to each isolated revision.

    The control pool contains quotes on other models at the immediately prior
    snapshot, restricted to a symmetric multiplicative band around the mover's
    new price.  Drawing the same number of prices as observed rivals preserves
    local scale, risk-set size, and the global frequency of exact menu points.
    """
    out = events.copy()
    if out.empty:
        out["global_menu_band_factor"] = pd.Series(dtype=float)
        out["global_menu_pool_size"] = pd.Series(dtype="Int64")
        out["global_menu_exact_hits"] = pd.Series(dtype="Int64")
        out["global_menu_match_probability"] = pd.Series(dtype=float)
        out["exact_minus_global_menu"] = pd.Series(dtype=float)
        return out
    snapshots = _normalized_quote_snapshots(q)
    cache = {timestamp: group for timestamp, group in snapshots.groupby("run_ts")}
    probabilities: list[float] = []
    pool_sizes: list[int] = []
    hit_counts: list[int] = []
    factor = float(band_factor)
    for row in out.itertuples(index=False):
        snapshot = cache.get(row.previous_run_ts)
        if snapshot is None:
            probabilities.append(math.nan)
            pool_sizes.append(0)
            hit_counts.append(0)
            continue
        control = snapshot[
            snapshot["model_id"].astype(str).ne(str(row.model_id))
            & snapshot["price"].between(
                float(row.new_price) / factor,
                float(row.new_price) * factor,
                inclusive="both",
            )
        ]["price"].to_numpy(dtype=float)
        population = int(len(control))
        draws = int(row.n_rival_quotes)
        hits = int(
            np.isclose(
                control,
                float(row.new_price),
                rtol=1e-9,
                atol=1e-12,
            ).sum()
        )
        probability = (
            _hypergeometric_any_hit_probability(
                population=population,
                hits=hits,
                draws=draws,
            )
            if population >= draws and draws > 0
            else math.nan
        )
        probabilities.append(probability)
        pool_sizes.append(population)
        hit_counts.append(hits)
    out["global_menu_band_factor"] = factor
    out["global_menu_pool_size"] = pool_sizes
    out["global_menu_exact_hits"] = hit_counts
    out["global_menu_match_probability"] = probabilities
    out["exact_minus_global_menu"] = (
        out["exact_lagged_rival_match"] - out["global_menu_match_probability"]
    )
    return out


def attach_historical_model_menu_null(
    events: pd.DataFrame,
    q: pd.DataFrame,
    *,
    washout_hours: int = REFERENCE_HISTORICAL_WASHOUT_HOURS,
) -> pd.DataFrame:
    """Attach a past-only, same-model menu-frequency benchmark.

    Each eligible historical snapshot is separated from the event by the declared
    washout.  Within a snapshot, the mover is excluded and the null draws the same
    number of endpoints as the event's lagged rival set.  Averaging exact
    hypergeometric hit probabilities preserves model-specific menu conventions
    without using continuation or future quotes.
    """
    out = events.copy()
    if out.empty:
        out["historical_menu_washout_hours"] = pd.Series(dtype="Int64")
        out["historical_menu_snapshots"] = pd.Series(dtype="Int64")
        out["historical_menu_match_probability"] = pd.Series(dtype=float)
        out["exact_minus_historical_menu"] = pd.Series(dtype=float)
        return out
    snapshots = _normalized_quote_snapshots(q)
    cache = {model: group for model, group in snapshots.groupby("model_id")}
    washout = timedelta(hours=int(washout_hours))
    probabilities: list[float] = []
    snapshot_counts: list[int] = []
    for row in out.itertuples(index=False):
        history = cache.get(str(row.model_id))
        if history is None:
            probabilities.append(math.nan)
            snapshot_counts.append(0)
            continue
        history = history[
            history["run_ts"].le(row.previous_run_ts - washout)
            & history["provider_name"].astype(str).ne(str(row.provider_name))
        ]
        per_snapshot: list[float] = []
        for _, snapshot in history.groupby("run_ts", sort=False):
            prices = snapshot["price"].to_numpy(dtype=float)
            population = int(len(prices))
            draws = int(row.n_rival_quotes)
            if population < draws or draws <= 0:
                continue
            hits = int(
                np.isclose(
                    prices,
                    float(row.new_price),
                    rtol=1e-9,
                    atol=1e-12,
                ).sum()
            )
            per_snapshot.append(
                _hypergeometric_any_hit_probability(
                    population=population,
                    hits=hits,
                    draws=draws,
                )
            )
        probabilities.append(float(np.mean(per_snapshot)) if per_snapshot else math.nan)
        snapshot_counts.append(int(len(per_snapshot)))
    out["historical_menu_washout_hours"] = int(washout_hours)
    out["historical_menu_snapshots"] = snapshot_counts
    out["historical_menu_match_probability"] = probabilities
    out["exact_minus_historical_menu"] = (
        out["exact_lagged_rival_match"] - out["historical_menu_match_probability"]
    )
    return out


def attach_same_provider_menu_control(
    events: pd.DataFrame,
    q: pd.DataFrame,
    *,
    band_factor: float = REFERENCE_GLOBAL_BAND_FACTOR,
) -> pd.DataFrame:
    """Attach the preregistered same-provider/across-model negative control."""
    out = events.copy()
    columns = {
        "own_menu_band_factor": pd.Series(dtype=float),
        "own_menu_pool_size": pd.Series(dtype="Int64"),
        "own_menu_exact_hits": pd.Series(dtype="Int64"),
        "own_menu_exact": pd.Series(dtype=float),
        "own_menu_novel": pd.Series(dtype=float),
    }
    if out.empty:
        for name, values in columns.items():
            out[name] = values
        return out

    snapshots = _normalized_quote_snapshots(q)
    cache = {timestamp: group for timestamp, group in snapshots.groupby("run_ts")}
    factor = float(band_factor)
    pool_sizes: list[int] = []
    hit_counts: list[int] = []
    exact_values: list[float] = []
    novel_values: list[float] = []
    for row in out.itertuples(index=False):
        snapshot = cache.get(row.previous_run_ts)
        if snapshot is None:
            pool_sizes.append(0)
            hit_counts.append(0)
            exact_values.append(math.nan)
            novel_values.append(math.nan)
            continue
        control = snapshot[
            snapshot["provider_name"].astype(str).eq(str(row.provider_name))
            & snapshot["model_id"].astype(str).ne(str(row.model_id))
            & snapshot["price"].between(
                float(row.new_price) / factor,
                float(row.new_price) * factor,
                inclusive="both",
            )
        ]["price"].to_numpy(dtype=float)
        hits = int(
            np.isclose(
                control,
                float(row.new_price),
                rtol=1e-9,
                atol=1e-12,
            ).sum()
        )
        pool_sizes.append(int(len(control)))
        hit_counts.append(hits)
        if len(control):
            exact_values.append(float(hits > 0))
            novel_values.append(float(hits == 0))
        else:
            exact_values.append(math.nan)
            novel_values.append(math.nan)

    out["own_menu_band_factor"] = factor
    out["own_menu_pool_size"] = pool_sizes
    out["own_menu_exact_hits"] = hit_counts
    out["own_menu_exact"] = exact_values
    out["own_menu_novel"] = novel_values
    return out


def reference_price_landing_panel(
    q: pd.DataFrame,
    *,
    max_gap_minutes: int = REFERENCE_MAX_GAP_MINUTES,
    band_factor: float = REFERENCE_GLOBAL_BAND_FACTOR,
) -> pd.DataFrame:
    events = isolated_quote_change_events(q, max_gap_minutes=max_gap_minutes)
    panel = attach_global_price_menu_null(events, q, band_factor=band_factor)
    panel = attach_historical_model_menu_null(panel, q)
    return attach_same_provider_menu_control(panel, q, band_factor=band_factor)


def reference_price_landing_inference(panel: pd.DataFrame) -> dict[str, Any]:
    if panel.empty:
        return {
            "n_events": 0,
            "n_models": 0,
            "n_providers": 0,
            "exact_lagged_rival_match_share": None,
            "adjacent_placebo_match_share": None,
            "global_menu_match_probability": None,
            "exact_minus_adjacent_placebo": None,
            "exact_minus_global_menu": None,
        }
    usable = panel.dropna(subset=["global_menu_match_probability"]).copy()
    historical = (
        panel.dropna(subset=["historical_menu_match_probability"]).copy()
        if "historical_menu_match_probability" in panel
        else panel.iloc[0:0].copy()
    )
    copies = panel[panel["exact_lagged_rival_match"].eq(1)]

    def largest_share(frame: pd.DataFrame, column: str) -> float | None:
        if frame.empty:
            return None
        return float(frame.groupby(column).size().max() / len(frame))

    return {
        "n_events": int(len(panel)),
        "n_global_menu_comparable_events": int(len(usable)),
        "n_models": int(panel["model_id"].nunique()),
        "n_providers": int(panel["provider_name"].nunique()),
        "exact_lagged_rival_matches": int(panel["exact_lagged_rival_match"].sum()),
        "exact_lagged_rival_match_share": float(
            panel["exact_lagged_rival_match"].mean()
        ),
        "adjacent_placebo_match_share": float(
            panel["adjacent_placebo_match_share"].mean()
        ),
        "global_menu_match_probability": (
            float(usable["global_menu_match_probability"].mean()) if len(usable) else None
        ),
        "exact_minus_adjacent_placebo": float(
            panel["exact_minus_adjacent_placebo"].mean()
        ),
        "exact_minus_global_menu": (
            float(usable["exact_minus_global_menu"].mean()) if len(usable) else None
        ),
        "n_historical_menu_comparable_events": int(len(historical)),
        "historical_menu_match_probability": (
            float(historical["historical_menu_match_probability"].mean())
            if len(historical)
            else None
        ),
        "exact_minus_historical_menu": (
            float(historical["exact_minus_historical_menu"].mean())
            if len(historical)
            else None
        ),
        "model_cluster_adjacent_placebo": _clustered_mean_inference(
            panel,
            value_column="exact_minus_adjacent_placebo",
            cluster_column="model_id",
        ),
        "model_cluster_global_menu": _clustered_mean_inference(
            usable,
            value_column="exact_minus_global_menu",
            cluster_column="model_id",
        ),
        "provider_cluster_global_menu": _clustered_mean_inference(
            usable,
            value_column="exact_minus_global_menu",
            cluster_column="provider_name",
        ),
        "model_cluster_historical_menu": _clustered_mean_inference(
            historical,
            value_column="exact_minus_historical_menu",
            cluster_column="model_id",
        ),
        "provider_cluster_historical_menu": _clustered_mean_inference(
            historical,
            value_column="exact_minus_historical_menu",
            cluster_column="provider_name",
        ),
        "downward_share_of_exact_landings": (
            float(copies["direction"].eq("down").mean()) if len(copies) else None
        ),
        "largest_model_event_share": largest_share(panel, "model_id"),
        "largest_provider_event_share": largest_share(panel, "provider_name"),
        "largest_model_copy_share": largest_share(copies, "model_id"),
        "largest_provider_copy_share": largest_share(copies, "provider_name"),
    }


def same_provider_control_inference(panel: pd.DataFrame) -> dict[str, Any]:
    """Summarize the frozen same-provider/across-model negative control."""
    if "own_menu_exact" not in panel:
        return {
            "n_comparable_events": 0,
            "n_own_menu_novel_events": 0,
            "own_menu_exact_share": None,
            "four_cell_counts": {},
        }
    comparable = panel.dropna(subset=["own_menu_exact"]).copy()
    novel = comparable[comparable["own_menu_novel"].eq(1)].copy()
    four_cell = {
        f"rival_{rival}_own_{own}": int(
            (
                comparable["exact_lagged_rival_match"].eq(rival)
                & comparable["own_menu_exact"].eq(own)
            ).sum()
        )
        for rival in (0, 1)
        for own in (0, 1)
    }

    def largest_share(frame: pd.DataFrame, column: str) -> float | None:
        if frame.empty:
            return None
        return float(frame.groupby(column).size().max() / len(frame))

    novel_inference = reference_price_landing_inference(novel)
    own_matches = comparable[comparable["own_menu_exact"].eq(1)]
    return {
        "evidence_status": "post_nine_date_control_preregistered_before_estimation",
        "n_comparable_events": int(len(comparable)),
        "n_own_menu_novel_events": int(len(novel)),
        "own_menu_exact_share": (
            float(comparable["own_menu_exact"].mean()) if len(comparable) else None
        ),
        "four_cell_counts": four_cell,
        "model_cluster_association": _clustered_difference_in_means(
            comparable,
            outcome_column="own_menu_exact",
            group_column="exact_lagged_rival_match",
            cluster_column="model_id",
        ),
        "provider_cluster_association": _clustered_difference_in_means(
            comparable,
            outcome_column="own_menu_exact",
            group_column="exact_lagged_rival_match",
            cluster_column="provider_name",
        ),
        "largest_model_comparable_share": largest_share(comparable, "model_id"),
        "largest_provider_comparable_share": largest_share(
            comparable, "provider_name"
        ),
        "largest_model_own_match_share": largest_share(own_matches, "model_id"),
        "largest_provider_own_match_share": largest_share(
            own_matches, "provider_name"
        ),
        "own_menu_novel_reference_landing": novel_inference,
        "promotion_rule": (
            "Strategic following survives only if the own-menu-novel "
            "exact-minus-global-menu model-cluster interval excludes zero and "
            "every leave-one-model-out estimate is positive."
        ),
        "claim_boundary": (
            "Own-provider cross-model support identifies a public provider-menu "
            "alternative, not intent, collusion, or literal request front-running."
        ),
    }


def reference_price_landing_audit(
    q: pd.DataFrame,
    *,
    primary_panel: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if primary_panel is None:
        primary_events = isolated_quote_change_events(
            q,
            max_gap_minutes=REFERENCE_MAX_GAP_MINUTES,
        )
        primary = attach_global_price_menu_null(
            primary_events,
            q,
            band_factor=REFERENCE_GLOBAL_BAND_FACTOR,
        )
        primary = attach_historical_model_menu_null(primary, q)
    else:
        primary = primary_panel.copy()
        primary_events = primary_panel.copy()
    band_sensitivity = {}
    for factor in (1.25, 1.5, 2.0, 4.0, 10.0):
        panel = attach_global_price_menu_null(primary_events, q, band_factor=factor)
        inference = reference_price_landing_inference(panel)
        band_sensitivity[f"{factor:g}"] = {
            "band_factor": factor,
            "n_events": inference["n_global_menu_comparable_events"],
            "global_menu_match_probability": inference[
                "global_menu_match_probability"
            ],
            "exact_minus_global_menu": inference["exact_minus_global_menu"],
            "model_cluster_ci95": (
                inference.get("model_cluster_global_menu") or {}
            ).get("cluster_bootstrap_ci95"),
        }
    continuity_sensitivity = {}
    for minutes in (10, 15, 30):
        events = isolated_quote_change_events(q, max_gap_minutes=minutes)
        panel = attach_global_price_menu_null(
            events,
            q,
            band_factor=REFERENCE_GLOBAL_BAND_FACTOR,
        )
        inference = reference_price_landing_inference(panel)
        continuity_sensitivity[str(minutes)] = {
            "max_gap_minutes": minutes,
            "n_events": inference["n_events"],
            "exact_lagged_rival_match_share": inference[
                "exact_lagged_rival_match_share"
            ],
            "exact_minus_global_menu": inference["exact_minus_global_menu"],
            "model_cluster_ci95": (
                inference.get("model_cluster_global_menu") or {}
            ).get("cluster_bootstrap_ci95"),
        }
    return {
        "evidence_status": "post_freeze_exploratory_hard_null_registered",
        "primary_max_gap_minutes": REFERENCE_MAX_GAP_MINUTES,
        "primary_global_menu_band_factor": REFERENCE_GLOBAL_BAND_FACTOR,
        "historical_model_menu_washout_hours": REFERENCE_HISTORICAL_WASHOUT_HOURS,
        "primary": reference_price_landing_inference(primary),
        "same_provider_across_model_control": same_provider_control_inference(
            primary
        ),
        "global_menu_band_sensitivity": band_sensitivity,
        "continuity_sensitivity": continuity_sensitivity,
        "confirmatory_gate": (
            "Recompute unchanged on the earliest 30-date vintage. Promote a "
            "lagged-price-landing claim only if the 1.25-band model-cluster "
            "interval excludes zero and leave-one-model-out estimates stay positive."
        ),
        "claim_boundary": (
            "An adjacent-grid atom alone cannot distinguish strategic following from "
            "a common discrete price menu updated asynchronously. The matched global-menu "
            "null preserves price scale, exact menu frequency, and rival-set size."
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
    anchor_randomization = author_anchor_randomization_audit(q)
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
        "evidence_status": "post_freeze_exploratory_hard_null_registered",
        "latest_run_ts": str(q["run_ts"].max()) if len(q) else None,
        "primary_placebo_tick_usd_per_million_tokens": AUTHOR_PLACEBO_TICK_MTOK,
        "max_offset_ticks_each_direction": AUTHOR_PLACEBO_MAX_OFFSET_TICKS,
        "all_market_author_price_atom": author_cluster_inference(primary),
        "author_anchor_randomization_benchmark": anchor_randomization,
        "placebo_grid_sensitivity": sensitivity,
        "selected_tie_random_label_benchmark": selected_tie_random_label_audit(q),
        "confirmatory_gate": (
            "Recompute without specification changes on the earliest 30-date prefixes "
            "of both frozen quote vintages; retain the exact endpoint-label null, "
            "author clustering, pair-density comparison, and all four grids."
        ),
        "claim_boundary": (
            "The all-market atom rejects adjacent equally spaced levels, but the exact "
            "endpoint-label benchmark determines whether author identity is special. "
            "Failure against that harder null reclassifies the fact as generic provider "
            "price clustering rather than author focality."
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
    anchor = identity["author_anchor_randomization_benchmark"]
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
        "author_identity_status": (
            "non_discriminating_against_random_endpoint_anchor"
            if (anchor.get("poisson_binomial_upper_tail_p") or 0) > 0.05
            else "author_specific_against_random_endpoint_anchor"
        ),
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
    save(author_anchor_symmetry_panel(q), out_dir, "pm5_author_anchor_symmetry")
    reference_panel = reference_price_landing_panel(q)
    save(reference_panel, out_dir, "pm5_reference_price_landing")
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
        "reference_price_landing": reference_price_landing_audit(
            q,
            primary_panel=reference_panel,
        ),
        "signatures": {
            "coordination": "atom at 0 + missing mass at small undercuts; ties formed by "
            "upward moves; strategic landing beyond the hard common-menu null; breaks upward",
            "competition": "smooth small-undercut mass; ties formed downward; breaks downward",
        },
        "claim_boundary": (
            "Single-mover tie events only (multi-mover ticks skipped); author identity "
            "uses the shared provider-family alias crosswalk; both selected-tie and "
            "all-market author identity are tested against price-multiplicity-preserving "
            "label nulls; the 5-min grid leaves sub-tick sequencing unobserved."
        ),
    }
    save_json(summary, out_dir, "pm5_summary")
    return summary
