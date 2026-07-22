"""H91 — is apparent unit elasticity a revenue FOC or a cross-sectional mirage?

For zero marginal cost and negligible market-demand feedback, a provider that
maximizes gross revenue satisfies d log share / d log price = -1. H4's public
cross-sectional estimate is close to that value, but a first-order condition is
a derivative of the provider's own residual demand, not a comparison of unlike
providers. H91 separates between-provider/model and within-provider/model price
variation, repeats the decomposition with listed rather than transacted prices,
and estimates a sparse listed-price-change response with pre/post placebos.

None of these public regressions identifies a causal demand curve or provider
profit. The dynamic estimates remain power-gated until their registered time-
variation and event-count thresholds clear.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm

from . import data
from .bm_common import load_gates
from .common import DEFAULT_OUT, save, save_json
from .h4_routing import load_shares
from .h68_competition import demand_shares


def revenue_foc_test(
    elasticity: float,
    standard_error: float,
    *,
    target: float = -1.0,
    equivalence_margin: float = 0.25,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Two-sided equality and TOST equivalence tests around a revenue FOC."""
    values = [elasticity, standard_error, target, equivalence_margin, alpha]
    if any(not np.isfinite(value) for value in values):
        raise ValueError("FOC-test inputs must be finite")
    if standard_error <= 0 or equivalence_margin <= 0 or not 0 < alpha < 1:
        raise ValueError("standard error/margin must be positive and alpha in (0,1)")
    z_equal = (elasticity - target) / standard_error
    p_equal = float(2.0 * norm.sf(abs(z_equal)))
    lower = target - equivalence_margin
    upper = target + equivalence_margin
    p_above_lower = float(norm.sf((elasticity - lower) / standard_error))
    p_below_upper = float(norm.cdf((elasticity - upper) / standard_error))
    equivalence_p = max(p_above_lower, p_below_upper)
    return {
        "revenue_foc_target": target,
        "distance_to_revenue_foc": elasticity - target,
        "z_equal_revenue_foc": float(z_equal),
        "p_equal_revenue_foc": p_equal,
        "equivalence_margin": equivalence_margin,
        "equivalence_p": equivalence_p,
        "equivalent_to_revenue_foc": bool(equivalence_p < alpha),
        "p_equal_zero": float(2.0 * norm.sf(abs(elasticity / standard_error))),
        "p_equal_inverse_square": float(2.0 * norm.sf(abs((elasticity + 2.0) / standard_error))),
    }


def _fit_group_fe(
    frame: pd.DataFrame,
    *,
    outcome: str,
    price: str,
    group: str,
    cluster: str,
    controls: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    columns = list(dict.fromkeys([outcome, price, group, cluster, *controls]))
    data = frame[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(data) < 20 or data[group].nunique() < 2 or data[cluster].nunique() < 2:
        return None
    transformed = []
    for column in [outcome, price, *controls]:
        name = f"{column}_g"
        data[name] = data[column] - data.groupby(group)[column].transform("mean")
        transformed.append(name)
    if float(data[f"{price}_g"].abs().sum()) <= 0:
        return None
    weights = 1.0 / data.groupby(group)[group].transform("size")
    model = sm.WLS(
        data[f"{outcome}_g"],
        data[[f"{price}_g", *[f"{column}_g" for column in controls]]],
        weights=weights,
    ).fit(cov_type="cluster", cov_kwds={"groups": data[cluster]})
    beta = float(model.params[f"{price}_g"])
    se = float(model.bse[f"{price}_g"])
    return {
        "elasticity": beta,
        "standard_error": se,
        "ci95_low": beta - 1.96 * se,
        "ci95_high": beta + 1.96 * se,
        "p_value": float(model.pvalues[f"{price}_g"]),
        "n_observations": int(model.nobs),
        "n_groups": int(data[group].nunique()),
        "n_clusters": int(data[cluster].nunique()),
    }


def _absorb_two_way(
    values: pd.DataFrame,
    first_effect: pd.Series,
    second_effect: pd.Series,
    *,
    tolerance: float = 1e-10,
    max_iterations: int = 10_000,
) -> tuple[pd.DataFrame, int, float]:
    """Residualize columns against two high-dimensional fixed effects."""
    residual = values.astype(float).copy()
    final_change = np.inf
    for iteration in range(1, max_iterations + 1):
        previous = residual.to_numpy(copy=True)
        residual -= residual.groupby(first_effect, sort=False).transform("mean")
        residual -= residual.groupby(second_effect, sort=False).transform("mean")
        final_change = float(np.max(np.abs(residual.to_numpy() - previous)))
        if final_change <= tolerance:
            return residual, iteration, final_change
    raise RuntimeError(
        f"two-way fixed-effect absorption did not converge after {max_iterations} iterations; "
        f"last change={final_change}"
    )


def fit_two_way_fe(
    frame: pd.DataFrame,
    *,
    outcome: str,
    price: str,
    market_time: str,
    entity: str,
    cluster: str,
) -> dict[str, Any]:
    """OLS after exact alternating absorption of market-time and entity FEs."""
    columns = list(dict.fromkeys([outcome, price, market_time, entity, cluster]))
    panel = frame[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if (
        len(panel) < 20
        or panel[market_time].nunique() < 2
        or panel[entity].nunique() < 2
        or panel[cluster].nunique() < 2
    ):
        raise ValueError("two-way fixed-effect regression has insufficient support")
    residual, iterations, final_change = _absorb_two_way(
        panel[[outcome, price]], panel[market_time], panel[entity]
    )
    if float(residual[price].abs().sum()) <= 0:
        raise ValueError("two-way fixed-effect price residual has no variation")
    model = sm.OLS(residual[outcome], residual[[price]]).fit(
        cov_type="cluster", cov_kwds={"groups": panel[cluster]}
    )
    beta = float(model.params[price])
    se = float(model.bse[price])
    panel["_residual_price"] = residual[price].to_numpy()
    entity_varies = panel.groupby(entity)[price].nunique().gt(1)
    varying_entities = set(entity_varies[entity_varies].index)
    varying_mask = panel[entity].isin(varying_entities)
    entity_ss = panel.groupby(entity)["_residual_price"].apply(lambda value: float(value @ value))
    cluster_ss = panel.groupby(cluster)["_residual_price"].apply(lambda value: float(value @ value))
    total_ss = float(panel["_residual_price"] @ panel["_residual_price"])
    raw_centered_price = panel[price] - panel[price].mean()
    raw_price_ss = float(raw_centered_price @ raw_centered_price)
    return {
        "elasticity": beta,
        "standard_error": se,
        "ci95_low": beta - 1.96 * se,
        "ci95_high": beta + 1.96 * se,
        "p_value": float(model.pvalues[price]),
        "n_observations": int(model.nobs),
        "n_market_time_effects": int(panel[market_time].nunique()),
        "n_entity_effects": int(panel[entity].nunique()),
        "n_clusters": int(panel[cluster].nunique()),
        "price_varying_entities": int(entity_varies.sum()),
        "price_varying_entity_share": float(entity_varies.mean()),
        "price_changing_clusters": int(panel.loc[varying_mask, cluster].nunique()),
        "residual_price_ss_share_from_varying_entities": (
            float((panel.loc[varying_mask, "_residual_price"] ** 2).sum() / total_ss)
            if total_ss > 0
            else None
        ),
        "largest_entity_residual_price_ss_share": (
            float(entity_ss.max() / total_ss) if total_ss > 0 else None
        ),
        "top_five_entity_residual_price_ss_share": (
            float(entity_ss.nlargest(5).sum() / total_ss) if total_ss > 0 else None
        ),
        "largest_cluster_residual_price_ss_share": (
            float(cluster_ss.max() / total_ss) if total_ss > 0 else None
        ),
        "residual_price_cluster_hhi": (
            float(((cluster_ss / total_ss) ** 2).sum()) if total_ss > 0 else None
        ),
        "residual_price_sum_squares": total_ss,
        "raw_centered_price_sum_squares": raw_price_ss,
        "residual_to_raw_price_ss_ratio": total_ss / raw_price_ss if raw_price_ss > 0 else None,
        "absorption_iterations": iterations,
        "absorption_final_change": final_change,
    }


def fit_one_way_fe(
    frame: pd.DataFrame,
    *,
    outcome: str,
    price: str,
    effect: str,
    cluster: str,
) -> dict[str, Any]:
    """Unweighted OLS after absorbing one fixed effect."""
    columns = list(dict.fromkeys([outcome, price, effect, cluster]))
    panel = frame[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()
    residual = panel[[outcome, price]] - panel.groupby(effect)[[outcome, price]].transform("mean")
    if float(residual[price].abs().sum()) <= 0:
        raise ValueError("one-way fixed-effect price residual has no variation")
    model = sm.OLS(residual[outcome], residual[[price]]).fit(
        cov_type="cluster", cov_kwds={"groups": panel[cluster]}
    )
    beta = float(model.params[price])
    se = float(model.bse[price])
    return {
        "elasticity": beta,
        "standard_error": se,
        "ci95_low": beta - 1.96 * se,
        "ci95_high": beta + 1.96 * se,
        "p_value": float(model.pvalues[price]),
        "n_observations": int(model.nobs),
        "n_effects": int(panel[effect].nunique()),
        "n_clusters": int(panel[cluster].nunique()),
    }


def cluster_sign_flip_score_test(
    frame: pd.DataFrame,
    *,
    outcome: str,
    price: str,
    market_time: str,
    entity: str,
    cluster: str,
    null_coefficient: float,
    seed: int = 20260716,
    monte_carlo_draws: int = 99_999,
) -> dict[str, Any]:
    """Cluster sign-flip score test after exact two-way FE absorption."""
    columns = list(dict.fromkeys([outcome, price, market_time, entity, cluster]))
    panel = frame[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()
    residual, _, _ = _absorb_two_way(panel[[outcome, price]], panel[market_time], panel[entity])
    panel["_x"] = residual[price].to_numpy()
    panel["_u0"] = residual[outcome].to_numpy() - null_coefficient * panel["_x"]
    by_cluster = panel.groupby(cluster, as_index=False).agg(
        score=("_x", lambda values: 0.0),
        price_ss=("_x", lambda values: float(values @ values)),
    )
    score_map = panel.assign(_score=panel["_x"] * panel["_u0"]).groupby(cluster)["_score"].sum()
    by_cluster["score"] = by_cluster[cluster].map(score_map)
    total_price_ss = float(by_cluster["price_ss"].sum())
    threshold = max(total_price_ss * 1e-12, np.finfo(float).eps)
    support = by_cluster[by_cluster["price_ss"] > threshold].copy()
    scores = support["score"].to_numpy(float)
    observed = float(abs(scores.sum()))
    n_clusters = len(scores)
    if n_clusters == 0:
        raise ValueError("cluster sign-flip test has no residual-price support clusters")
    if n_clusters <= 18:
        masks = np.arange(1 << n_clusters, dtype=np.uint64)[:, None]
        bits = ((masks >> np.arange(n_clusters, dtype=np.uint64)) & 1).astype(float)
        signs = 2.0 * bits - 1.0
        null_statistics = np.abs(signs @ scores)
        method = "exact"
    else:
        rng = np.random.default_rng(seed)
        signs = rng.choice([-1.0, 1.0], size=(monte_carlo_draws, n_clusters))
        null_statistics = np.abs(signs @ scores)
        method = "monte_carlo"
    p_value = float(np.mean(null_statistics >= observed - 1e-15))
    return {
        "null_coefficient": null_coefficient,
        "method": method,
        "residual_price_support_clusters": n_clusters,
        "sign_patterns_or_draws": int(len(null_statistics)),
        "absolute_observed_cluster_score": observed,
        "two_sided_p_value": p_value,
        "null_score_ci95": [
            float(np.quantile(null_statistics, 0.025)),
            float(np.quantile(null_statistics, 0.975)),
        ],
    }


def leave_one_residual_support_cluster_out(
    frame: pd.DataFrame,
    *,
    outcome: str,
    price: str,
    market_time: str,
    entity: str,
    cluster: str,
) -> pd.DataFrame:
    """Refit after dropping each cluster that carries residualized price variation."""
    columns = list(dict.fromkeys([outcome, price, market_time, entity, cluster]))
    panel = frame[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()
    residual, _, _ = _absorb_two_way(panel[[outcome, price]], panel[market_time], panel[entity])
    panel["_x"] = residual[price].to_numpy()
    cluster_ss = panel.groupby(cluster)["_x"].apply(lambda values: float(values @ values))
    threshold = max(float(cluster_ss.sum()) * 1e-12, np.finfo(float).eps)
    support_clusters = cluster_ss[cluster_ss > threshold].index
    rows = []
    for dropped in support_clusters:
        fit = fit_two_way_fe(
            frame[frame[cluster].ne(dropped)],
            outcome=outcome,
            price=price,
            market_time=market_time,
            entity=entity,
            cluster=cluster,
        )
        rows.append({"dropped_cluster": dropped, **fit})
    return pd.DataFrame(rows)


def within_between_decomposition(
    frame: pd.DataFrame,
    *,
    outcome: str,
    price: str,
    group: str,
    entity: str,
    cluster: str | None = None,
    controls: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Mundlak-style price decomposition with market-time fixed effects."""
    cluster_column = cluster or entity
    columns = list(dict.fromkeys([outcome, price, group, entity, cluster_column, *controls]))
    data = frame[columns].replace([np.inf, -np.inf], np.nan).dropna().copy()
    if len(data) < 20 or data[group].nunique() < 2 or data[entity].nunique() < 2:
        raise ValueError("within-between decomposition has insufficient support")

    regressors = []
    for column in [price, *controls]:
        mean = f"{column}_entity_mean"
        within = f"{column}_entity_within"
        data[mean] = data.groupby(entity)[column].transform("mean")
        data[within] = data[column] - data[mean]
        regressors.extend([mean, within])
    transformed = []
    for column in [outcome, *regressors]:
        name = f"{column}_g"
        data[name] = data[column] - data.groupby(group)[column].transform("mean")
        transformed.append(name)
    weights = 1.0 / data.groupby(group)[group].transform("size")
    model = sm.WLS(
        data[f"{outcome}_g"],
        data[[f"{column}_g" for column in regressors]],
        weights=weights,
    ).fit(cov_type="cluster", cov_kwds={"groups": data[cluster_column]})
    between_name = f"{price}_entity_mean_g"
    within_name = f"{price}_entity_within_g"
    between = float(model.params[between_name])
    within = float(model.params[within_name])
    between_se = float(model.bse[between_name])
    within_se = float(model.bse[within_name])
    restriction = np.zeros((1, len(model.params)))
    restriction[0, list(model.params.index).index(between_name)] = 1.0
    restriction[0, list(model.params.index).index(within_name)] = -1.0
    difference = model.t_test(restriction)
    entity_variation = data.groupby(entity)[price].nunique().gt(1)
    total_variance = float(data[price].var(ddof=0))
    within_variance = float(data[f"{price}_entity_within"].var(ddof=0))
    return {
        "between_elasticity": between,
        "between_standard_error": between_se,
        "between_ci95": [between - 1.96 * between_se, between + 1.96 * between_se],
        "within_elasticity": within,
        "within_standard_error": within_se,
        "within_ci95": [within - 1.96 * within_se, within + 1.96 * within_se],
        "between_minus_within": float(np.asarray(difference.effect).item()),
        "difference_standard_error": float(np.asarray(difference.sd).item()),
        "difference_p_value": float(np.asarray(difference.pvalue).item()),
        "n_observations": int(model.nobs),
        "n_groups": int(data[group].nunique()),
        "n_entities": int(data[entity].nunique()),
        "n_clusters": int(data[cluster_column].nunique()),
        "varying_entities": int(entity_variation.sum()),
        "varying_entity_share": float(entity_variation.mean()),
        "within_price_variance_share": (
            within_variance / total_variance if total_variance > 0 else None
        ),
    }


def _effective_panel() -> pd.DataFrame:
    panel = load_shares().copy()
    panel["log_share"] = np.log(panel["share"])
    panel["log_price"] = np.log(panel["effective_output_price"])
    panel["cache"] = pd.to_numeric(panel["cache_hit_rate"], errors="coerce").fillna(0.0)
    panel["entity"] = (
        panel["provider_slug"].astype(str)
        + "|"
        + panel["model_permaslug"].astype(str)
        + "|"
        + panel["variant"].astype(str)
    )
    return panel


def _listed_panel(*, price_field: str, open_weight_only: bool) -> pd.DataFrame:
    if price_field not in {"price_prompt", "price_completion"}:
        raise ValueError(f"unsupported listed-price field: {price_field}")
    quotes = data.q(
        f"""
        select cast(dt as varchar) as dt, model_id, provider_name,
               median({price_field}) as price
        from read_parquet('{data.table_glob("endpoints_snapshots")}', union_by_name=true)
        where {price_field} > 0 and model_id not like '%:%'
        group by 1, 2, 3
        """
    ).df()
    shares = demand_shares()
    panel = shares.merge(quotes, on=["dt", "model_id", "provider_name"], how="inner")
    if open_weight_only:
        open_weight = data.q(
            f"""
            select id as model_id,
                   max(case when hugging_face_id is not null
                                  and trim(hugging_face_id) != '' then 1 else 0 end)
                     as is_open_weight
            from read_parquet('{data.table_glob("models_snapshots")}', union_by_name=true)
            where id not like '%:%'
            group by 1
            """
        ).df()
        panel = panel.merge(open_weight, on="model_id", how="left")
        panel = panel[panel["is_open_weight"].eq(1)].copy()
    panel["tokens"] = pd.to_numeric(panel["tokens"], errors="coerce")
    panel["price"] = pd.to_numeric(panel["price"], errors="coerce")
    panel = panel[(panel["tokens"] > 0) & (panel["price"] > 0)].copy()
    panel["share"] = panel["tokens"] / panel.groupby(["dt", "model_id"])["tokens"].transform("sum")
    panel = panel[(panel["share"] > 0) & (panel["share"] < 1)].copy()
    panel["log_share"] = np.log(panel["share"])
    panel["log_tokens"] = np.log(panel["tokens"])
    panel["log_price"] = np.log(panel["price"])
    panel["group"] = panel["dt"].astype(str) + "|" + panel["model_id"].astype(str)
    panel["entity"] = panel["provider_name"].astype(str) + "|" + panel["model_id"].astype(str)
    return panel


def _event_specs(listed: pd.DataFrame, threshold: float) -> tuple[pd.DataFrame, dict[str, Any]]:
    panel = listed.sort_values(["entity", "dt"], kind="mergesort").copy()
    panel["day"] = pd.to_datetime(panel["dt"], utc=True, errors="coerce")
    panel["previous_day"] = panel.groupby("entity")["day"].shift()
    panel["next_day"] = panel.groupby("entity")["day"].shift(-1)
    panel["dlog_price"] = panel.groupby("entity")["log_price"].diff()
    panel["dlog_share"] = panel.groupby("entity")["log_share"].diff()
    panel["pre_dlog_share"] = panel.groupby("entity")["dlog_share"].shift()
    panel["post_dlog_share"] = panel.groupby("entity")["dlog_share"].shift(-1)
    panel["current_gap"] = (panel["day"] - panel["previous_day"]).dt.days
    panel["post_gap"] = (panel["next_day"] - panel["day"]).dt.days
    panel.loc[panel["current_gap"].ne(1), ["dlog_price", "dlog_share"]] = np.nan
    panel.loc[panel.groupby("entity")["current_gap"].shift().ne(1), "pre_dlog_share"] = np.nan
    panel.loc[panel["post_gap"].ne(1), "post_dlog_share"] = np.nan
    mover = panel["dlog_price"].abs().ge(np.log1p(threshold))
    eligible_group = mover.groupby(panel["group"]).transform("any")
    event_panel = panel[eligible_group].copy()
    rows = []
    for name, outcome in [
        ("listed_price_pretrend_tminus1", "pre_dlog_share"),
        ("listed_price_first_difference_t0", "dlog_share"),
        ("listed_price_post_tplus1", "post_dlog_share"),
    ]:
        fit = _fit_group_fe(
            event_panel,
            outcome=outcome,
            price="dlog_price",
            group="group",
            cluster="provider_name",
        )
        if fit is not None:
            rows.append({"specification": name, **fit})
    support = {
        "listed_price_change_threshold": threshold,
        "mover_events": int(mover.sum()),
        "event_groups": int(event_panel["group"].nunique()),
        "event_panel_rows": int(len(event_panel)),
    }
    return pd.DataFrame(rows), support


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    gates = load_gates()["revenue_stationarity"]
    margin = float(gates["equivalence_margin"])
    alpha = float(gates["alpha"])
    effective = _effective_panel()
    listed = _listed_panel(price_field="price_prompt", open_weight_only=True)
    listed_completion_all = _listed_panel(
        price_field="price_completion", open_weight_only=False
    )

    pooled = _fit_group_fe(
        effective,
        outcome="log_share",
        price="log_price",
        group="group",
        cluster="group",
        controls=("cache",),
    )
    if pooled is None:
        raise ValueError("effective-price cross-section is not estimable")
    effective_decomposition = within_between_decomposition(
        effective,
        outcome="log_share",
        price="log_price",
        group="group",
        entity="entity",
        controls=("cache",),
    )
    listed_decomposition = within_between_decomposition(
        listed,
        outcome="log_share",
        price="log_price",
        group="group",
        entity="entity",
        cluster="provider_name",
    )
    listed_completion_decomposition = within_between_decomposition(
        listed_completion_all,
        outcome="log_share",
        price="log_price",
        group="group",
        entity="entity",
        cluster="provider_name",
    )
    listed_date_fe = fit_one_way_fe(
        listed,
        outcome="log_tokens",
        price="log_price",
        effect="dt",
        cluster="provider_name",
    )
    listed_date_model_fe = fit_two_way_fe(
        listed,
        outcome="log_tokens",
        price="log_price",
        market_time="dt",
        entity="model_id",
        cluster="provider_name",
    )
    listed_two_way_fe = fit_two_way_fe(
        listed,
        outcome="log_tokens",
        price="log_price",
        market_time="group",
        entity="entity",
        cluster="provider_name",
    )
    published_benchmark_sign_flip = cluster_sign_flip_score_test(
        listed,
        outcome="log_tokens",
        price="log_price",
        market_time="group",
        entity="entity",
        cluster="provider_name",
        null_coefficient=-1.02,
    )
    listed_two_way_lopo = leave_one_residual_support_cluster_out(
        listed,
        outcome="log_tokens",
        price="log_price",
        market_time="group",
        entity="entity",
        cluster="provider_name",
    )
    save(listed_two_way_lopo, out_dir, "h91_listed_prompt_two_way_lopo")

    daily_rows = []
    for day, group in effective.groupby("dt", sort=True):
        fit = _fit_group_fe(
            group,
            outcome="log_share",
            price="log_price",
            group="group",
            cluster="group",
            controls=("cache",),
        )
        if fit is not None:
            daily_rows.append({"dt": day, **fit})
    daily = pd.DataFrame(daily_rows)
    save(daily, out_dir, "h91_daily_cross_section")

    event_specs, event_support = _event_specs(listed, float(gates["listed_price_change_threshold"]))
    save(event_specs, out_dir, "h91_listed_price_event_specs")

    specs = [
        {"specification": "effective_price_pooled_cross_section", **pooled},
        {
            "specification": "effective_price_between_entity",
            "elasticity": effective_decomposition["between_elasticity"],
            "standard_error": effective_decomposition["between_standard_error"],
            "ci95_low": effective_decomposition["between_ci95"][0],
            "ci95_high": effective_decomposition["between_ci95"][1],
            "n_observations": effective_decomposition["n_observations"],
            "n_groups": effective_decomposition["n_groups"],
            "n_clusters": effective_decomposition["n_entities"],
        },
        {
            "specification": "effective_price_within_entity",
            "elasticity": effective_decomposition["within_elasticity"],
            "standard_error": effective_decomposition["within_standard_error"],
            "ci95_low": effective_decomposition["within_ci95"][0],
            "ci95_high": effective_decomposition["within_ci95"][1],
            "n_observations": effective_decomposition["n_observations"],
            "n_groups": effective_decomposition["n_groups"],
            "n_clusters": effective_decomposition["n_entities"],
        },
        {
            "specification": "listed_prompt_open_weight_between_entity",
            "elasticity": listed_decomposition["between_elasticity"],
            "standard_error": listed_decomposition["between_standard_error"],
            "ci95_low": listed_decomposition["between_ci95"][0],
            "ci95_high": listed_decomposition["between_ci95"][1],
            "n_observations": listed_decomposition["n_observations"],
            "n_groups": listed_decomposition["n_groups"],
            "n_clusters": listed_decomposition["n_clusters"],
        },
        {
            "specification": "listed_prompt_open_weight_within_entity",
            "elasticity": listed_decomposition["within_elasticity"],
            "standard_error": listed_decomposition["within_standard_error"],
            "ci95_low": listed_decomposition["within_ci95"][0],
            "ci95_high": listed_decomposition["within_ci95"][1],
            "n_observations": listed_decomposition["n_observations"],
            "n_groups": listed_decomposition["n_groups"],
            "n_clusters": listed_decomposition["n_clusters"],
        },
        {
            "specification": "listed_prompt_open_weight_date_fe",
            **listed_date_fe,
        },
        {
            "specification": "listed_prompt_open_weight_date_and_model_fe",
            **listed_date_model_fe,
        },
        {
            "specification": "listed_prompt_open_weight_two_way_fe",
            **listed_two_way_fe,
        },
        *event_specs.to_dict("records"),
    ]
    for row in specs:
        row.update(
            revenue_foc_test(
                float(row["elasticity"]),
                float(row["standard_error"]),
                equivalence_margin=margin,
                alpha=alpha,
            )
        )
    spec_panel = pd.DataFrame(specs)
    save(spec_panel, out_dir, "h91_revenue_foc_specs")

    cross = spec_panel[spec_panel["specification"].eq("effective_price_pooled_cross_section")].iloc[
        0
    ]
    within = spec_panel[spec_panel["specification"].eq("effective_price_within_entity")].iloc[0]
    event = spec_panel[spec_panel["specification"].eq("listed_price_first_difference_t0")]
    panel_days = int(effective["dt"].nunique())
    dynamic_gates = {
        "panel_days": panel_days,
        "minimum_panel_days": int(gates["min_panel_days"]),
        "listed_price_change_events": event_support["mover_events"],
        "minimum_listed_price_change_events": int(gates["min_listed_price_change_events"]),
        "listed_varying_entity_share": listed_decomposition["varying_entity_share"],
        "minimum_varying_entity_share": float(gates["min_varying_entity_share"]),
        "effective_within_price_variance_share": effective_decomposition[
            "within_price_variance_share"
        ],
        "listed_within_price_variance_share": listed_decomposition["within_price_variance_share"],
        "minimum_within_price_variance_share": float(gates["min_within_price_variance_share"]),
        "within_effective_equivalent_to_revenue_foc": bool(within["equivalent_to_revenue_foc"]),
        "event_equivalent_to_revenue_foc": bool(
            len(event) and event.iloc[0]["equivalent_to_revenue_foc"]
        ),
    }
    dynamic_ready = bool(
        panel_days >= int(gates["min_panel_days"])
        and event_support["mover_events"] >= int(gates["min_listed_price_change_events"])
        and listed_decomposition["varying_entity_share"] >= float(gates["min_varying_entity_share"])
        and effective_decomposition["within_price_variance_share"]
        >= float(gates["min_within_price_variance_share"])
        and listed_decomposition["within_price_variance_share"]
        >= float(gates["min_within_price_variance_share"])
        and dynamic_gates["within_effective_equivalent_to_revenue_foc"]
        and dynamic_gates["event_equivalent_to_revenue_foc"]
    )
    cross_equivalent = bool(cross["equivalent_to_revenue_foc"])
    gap_detected = bool(effective_decomposition["difference_p_value"] < alpha)
    published_beta = -1.02
    published_se = 0.13
    current_beta = float(listed_two_way_fe["elasticity"])
    current_se = float(listed_two_way_fe["standard_error"])
    benchmark_difference = current_beta - published_beta
    benchmark_difference_se = float(np.hypot(current_se, published_se))
    benchmark_z = benchmark_difference / benchmark_difference_se
    oa5_rows = []
    for specification, current, published, published_standard_error in [
        ("date_fe", listed_date_fe, -0.48, 0.15),
        ("date_and_model_fe", listed_date_model_fe, -1.07, 0.23),
        ("date_model_and_provider_model_fe", listed_two_way_fe, -1.02, 0.13),
    ]:
        difference = float(current["elasticity"]) - published
        difference_se = float(np.hypot(float(current["standard_error"]), published_standard_error))
        oa5_rows.append(
            {
                "specification": specification,
                "current_elasticity": float(current["elasticity"]),
                "current_standard_error": float(current["standard_error"]),
                "published_elasticity": published,
                "published_standard_error": published_standard_error,
                "current_minus_published": difference,
                "difference_standard_error": difference_se,
                "difference_p_value": float(2.0 * norm.sf(abs(difference / difference_se))),
                "current_observations": int(current["n_observations"]),
                "published_observations": 48_362,
            }
        )
    oa5_crosswalk = pd.DataFrame(oa5_rows)
    save(oa5_crosswalk, out_dir, "h91_oa5_replication_crosswalk")
    current_foc_test = revenue_foc_test(
        current_beta,
        current_se,
        equivalence_margin=margin,
        alpha=alpha,
    )
    summary = {
        "evidence_status": (
            "dynamic_revenue_stationarity_ready"
            if dynamic_ready
            else (
                "current_provider_model_fe_rejects_revenue_stationarity_but_not_causal"
                if current_foc_test["p_equal_revenue_foc"] < alpha
                else "cross_sectional_unit_elasticity_not_dynamically_identified"
            )
        ),
        "cross_sectional_revenue_foc": cross.to_dict(),
        "daily_cross_section": {
            "days": int(len(daily)),
            "elasticity_range": (
                [float(daily["elasticity"].min()), float(daily["elasticity"].max())]
                if len(daily)
                else []
            ),
            "days_point_estimate_within_equivalence_band": (
                int(((daily["elasticity"] + 1.0).abs() <= margin).sum()) if len(daily) else 0
            ),
        },
        "effective_price_within_between": effective_decomposition,
        "listed_price_within_between": listed_decomposition,
        "listed_price_definition": "daily median prompt price, open-weight models only",
        "listed_prompt_open_weight_date_fe": listed_date_fe,
        "listed_prompt_open_weight_date_and_model_fe": listed_date_model_fe,
        "listed_prompt_open_weight_two_way_fe": listed_two_way_fe,
        "listed_prompt_open_weight_two_way_revenue_foc": current_foc_test,
        "listed_prompt_two_way_lopo": {
            "residual_price_support_clusters": int(len(listed_two_way_lopo)),
            "elasticity_range": [
                float(listed_two_way_lopo["elasticity"].min()),
                float(listed_two_way_lopo["elasticity"].max()),
            ],
            "all_point_estimates_less_elastic_than_published": bool(
                (listed_two_way_lopo["elasticity"] > published_beta).all()
            ),
        },
        "listed_completion_all_models_sensitivity": listed_completion_decomposition,
        "published_2025_no_controls_benchmark": {
            "source": "Demirer, Fradkin, Tadelis, and Peng (2025), Table OA-5 column 3",
            "sample": "March-December 2025 open-source provider-model-days",
            "elasticity": published_beta,
            "standard_error": published_se,
            "n_observations": 48_362,
            "three_column_crosswalk": oa5_rows,
            "current_minus_benchmark": benchmark_difference,
            "difference_standard_error": benchmark_difference_se,
            "z_statistic": benchmark_z,
            "p_value": float(2.0 * norm.sf(abs(benchmark_z))),
            "current_sample_cluster_sign_flip_against_fixed_published_coefficient": (
                published_benchmark_sign_flip
            ),
            "claim_boundary": (
                "The comparison treats the published and current estimates as independent. "
                "The data construction, calendar window, and available controls are not "
                "identical, so this is a replication benchmark rather than proof of a "
                "structural break."
            ),
        },
        "listed_price_event_support": event_support,
        "dynamic_promotion_gates": dynamic_gates,
        "dynamic_promotion_ready": dynamic_ready,
        "unit_elasticity_mirage_screen": (
            "pooled_unit_elasticity_rejected_by_exact_provider_model_fe"
            if cross_equivalent
            and float(listed_two_way_fe["p_value"]) > alpha
            and current_foc_test["p_equal_revenue_foc"] < alpha
            else (
                "cross_sectional_equivalence_with_significant_within_between_gap"
                if cross_equivalent and gap_detected
                else "not_resolved"
            )
        ),
        "interpretation": (
            "The pooled coefficient near -1 is exactly equivalent to a price-neutral public "
            "revenue-proxy share under the same fixed effects; it does not identify a residual-"
            "demand derivative. In the closest exact published specification, the current "
            "provider-model fixed-effect coefficient is near zero and rejects the gross-revenue "
            "FOC. This is a temporal replication discrepancy, not a causal demand estimate; the "
            "dynamic promotion gates remain closed."
        ),
        "claim_boundary": (
            "H91 uses public aggregate provider token shares, transacted effective prices, and "
            "daily listed quotes. Prices are endogenous, provider quality and private discounts "
            "are incomplete, and only a small subset of provider/model entities changes listed "
            "price. Equivalence of a cross-sectional coefficient to -1 is not evidence that a "
            "provider maximizes revenue. Profit maximization additionally requires marginal cost."
        ),
    }
    save_json(summary, out_dir, "h91_summary")
    return summary
