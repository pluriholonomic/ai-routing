"""H19 — Provider typology: cluster inference providers by behavioral "type".

Motivated by H18: the dominant repricing predictor is persistent seller
heterogeneity (mover/stayer). Here we build a provider × feature matrix and
cluster it, looking for the dealer-taxonomy analog (streaming MMs vs posted
quoters vs shopfronts).

Feature blocks (latest-day cross-section + live history where it exists):
  pricing behavior   repricing events/endpoint, price pctile in contested
                     models, share-cheapest
  quote firmness     reject rate, fortuna mean, deranked share
  execution quality  p50 latency, throughput, tool-call error rate
  catalog strategy   n_models, low-precision quant share, time-to-list days
  OR-dependence      BYOK endpoint share, OR token volume (log),
                     serves-own-models flag

Method: standardize -> PCA (interpretable axes) -> GaussianMixture with
BIC-selected k in 2..6 -> typed table. n is small (~60-70 providers), so
clusters are coarse by design.

  h19_provider_features   the matrix
  h19_provider_types      provider -> cluster + top traits
  h19_summary             axes loadings, k, cluster profiles
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)


def _norm(s: str | None) -> str:
    return "".join(c for c in (s or "").lower() if c.isalnum())


import re  # noqa: E402

_SUFFIXES = re.compile(
    r"\s*(\(.*?\)|Turbo|Highspeed|High-Speed|Fast|Dedicated|ZDR|Int\.|OpenSource)\s*$",
    re.IGNORECASE,
)

# provider family -> model-author slugs it first-party serves
_OWN_ALIASES = {
    "openai": {"openai"},
    "openaiadapter": {"openai"},
    "anthropic": {"anthropic"},
    "google ai studio": {"google"},
    "google vertex": {"google"},
    "xai": {"x-ai"},
    "z.ai": {"z-ai"},
    "moonshot ai": {"moonshotai"},
    "minimax": {"minimax"},
    "deepseek": {"deepseek"},
    "mistral": {"mistralai"},
    "cohere": {"cohere"},
    "ai21": {"ai21"},
    "perplexity": {"perplexity"},
    "alibaba cloud": {"qwen", "alibaba"},
    "alibaba": {"qwen", "alibaba"},
    "baidu qianfan": {"baidu"},
    "stepfun": {"stepfun"},
    "xiaomi": {"xiaomi"},
    "seed": {"bytedance", "seed"},
    "inflection": {"inflection"},
    "inception": {"inceptionai", "inception"},
    "reka ai": {"reka"},
    "upstage": {"upstage"},
    "arcee ai": {"arcee-ai"},
    "poolside": {"poolside"},
    "morph": {"morph"},
    "sakana": {"sakana"},
    "tencent": {"tencent"},
}


def provider_family(name: str | None) -> str:
    s = name or ""
    prev = None
    while prev != s:
        prev = s
        s = _SUFFIXES.sub("", s).strip()
    return s


def serves_own(provider_family_name: str, model_author: str) -> bool:
    fam = provider_family_name.lower().strip()
    if fam in _OWN_ALIASES:
        return model_author in _OWN_ALIASES[fam]
    a, p = _norm(model_author), _norm(fam)
    return bool(a and p) and (a in p or p in a)


def build_features() -> pd.DataFrame:
    # --- endpoint_stats: firmness, byok, catalog, time-to-list, capacity
    es_rows = data.q(
        f"""
        select provider_display_name as provider, model_permaslug, record_json
        from read_parquet('{data.table_glob("endpoint_stats_daily")}')
        where dt = (select max(dt) from
                    read_parquet('{data.table_glob("endpoint_stats_daily")}'))
          and variant = 'standard'
        """
    ).df()
    recs = []
    for r in es_rows.itertuples(index=False):
        d = json.loads(r.record_json)
        sh = d.get("status_heuristics_1d") or {}
        tot = sum(v or 0 for v in sh.values())
        f = d.get("fortuna") or {}
        model = d.get("model") or {}
        created_ep = pd.to_datetime(d.get("created_at"), utc=True, errors="coerce")
        created_model = pd.to_datetime(model.get("created_at"), utc=True, errors="coerce")
        ttl = (
            (created_ep - created_model).total_seconds() / 86400
            if pd.notna(created_ep) and pd.notna(created_model)
            else np.nan
        )
        recs.append(
            {
                "provider": r.provider,
                "model_permaslug": r.model_permaslug,
                "model_author": (r.model_permaslug or "").split("/")[0],
                "reject_rate": ((sh.get("rateLimited") or 0) + (sh.get("derankableError") or 0))
                / tot
                if tot >= 100
                else np.nan,
                "fortuna_mean": f["beta_alpha"] / (f["beta_alpha"] + f["beta_beta"])
                if f.get("beta_alpha") and f.get("beta_beta")
                else np.nan,
                "is_deranked": bool(d.get("is_deranked")),
                "is_byok": bool(d.get("is_byok") or d.get("is_byok_only")),
                "quant": (d.get("quantization") or "unknown"),
                "time_to_list_days": ttl if ttl is not None and ttl >= 0 else np.nan,
            }
        )
    es = pd.DataFrame(recs)
    es["provider"] = es["provider"].map(provider_family)
    es["own_model"] = [
        serves_own(p, a) for a, p in zip(es["model_author"], es["provider"], strict=True)
    ]

    # --- prices: percentile within contested models, share cheapest
    ep = data.q(
        f"""
        select provider_name as provider, model_id, min(price_completion) p
        from {data.latest_endpoints()}
        where price_completion > 0 and model_id not like '%:free'
        group by 1, 2
        """
    ).df()
    ep["provider"] = ep["provider"].map(provider_family)
    ep = ep.groupby(["provider", "model_id"], as_index=False)["p"].min()
    ep["n_prov"] = ep.groupby("model_id")["provider"].transform("nunique")
    contested = ep[ep["n_prov"] >= 2].copy()
    contested["pctile"] = contested.groupby("model_id")["p"].rank(pct=True)
    contested["cheapest"] = contested.groupby("model_id")["p"].transform("min") == contested["p"]

    # --- perf quality
    perf = data.q(
        f"""
        with es2 as (
          select distinct endpoint_uuid, provider_display_name as provider_raw
          from read_parquet('{data.table_glob("endpoint_stats_daily")}')
        )
        select es2.provider_raw,
               median(value) filter (where metric='latency-comparison') lat,
               median(value) filter (where metric='throughput-comparison') tps,
               avg(value) filter (where metric='tool-call-error-rate') tool_err
        from read_parquet('{data.table_glob("perf_comparisons_daily")}') p
        join es2 using (endpoint_uuid)
        group by 1
        """
    ).df()
    perf["provider"] = perf["provider_raw"].map(provider_family)
    perf = perf.groupby("provider", as_index=False).agg(
        lat=("lat", "median"), tps=("tps", "median"), tool_err=("tool_err", "mean")
    )

    # --- OR volume
    vol = data.q(
        f"""
        select provider_name as provider, sum(total_tokens) tokens
        from {data.effective_pricing()}
        where dt = (select max(dt) from {data.effective_pricing()})
        group by 1
        """
    ).df()
    vol["provider"] = vol["provider"].map(provider_family)
    vol = vol.groupby("provider", as_index=False)["tokens"].sum()

    # --- live repricing intensity
    chg = data.q(
        f"""
        select provider_name as provider, count(*) n_price_events
        from read_parquet('{data.table_glob("pricing_changes", layer="derived")}')
        where field like 'price%' group by 1
        """
    ).df()
    chg["provider"] = chg["provider"].map(provider_family)
    chg = chg.groupby("provider", as_index=False)["n_price_events"].sum()

    g = es.groupby("provider").agg(
        n_models=("model_permaslug", "nunique"),
        reject_rate=("reject_rate", "median"),
        fortuna_mean=("fortuna_mean", "median"),
        deranked_share=("is_deranked", "mean"),
        byok_share=("is_byok", "mean"),
        own_model_share=("own_model", "mean"),
        lowprec_share=("quant", lambda s: float(s.isin(["fp4", "fp8", "int4", "int8"]).mean())),
        time_to_list_days=("time_to_list_days", "median"),
    )
    g = g.join(
        contested.groupby("provider").agg(
            price_pctile=("pctile", "mean"), share_cheapest=("cheapest", "mean")
        )
    )
    g = g.join(perf.set_index("provider"))
    g = g.join(vol.set_index("provider"))
    g = g.join(chg.set_index("provider"))
    g["n_price_events"] = g["n_price_events"].fillna(0)
    g["log_or_tokens"] = np.log1p(g["tokens"].fillna(0))
    g["log_latency"] = np.log(g["lat"].where(g["lat"] > 0))
    g["log_tps"] = np.log(g["tps"].where(g["tps"] > 0))
    g["log_time_to_list"] = np.log1p(g["time_to_list_days"])
    g["reprice_per_model"] = g["n_price_events"] / g["n_models"].clip(lower=1)
    return g.reset_index()


CLUSTER_FEATURES = [
    "n_models",
    "reject_rate",
    "fortuna_mean",
    "deranked_share",
    "byok_share",
    "own_model_share",
    "lowprec_share",
    "log_time_to_list",
    "price_pctile",
    "share_cheapest",
    "log_latency",
    "log_tps",
    "tool_err",
    "log_or_tokens",
    "reprice_per_model",
]


def cluster(g: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    from sklearn.decomposition import PCA
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    X = g[CLUSTER_FEATURES].apply(pd.to_numeric, errors="coerce")
    X = X.replace([np.inf, -np.inf], np.nan)
    # Sparse live panels can leave an entire feature column unobserved. Its
    # median is then NaN, so ordinary median imputation still passes NaNs into
    # StandardScaler/PCA. Zero is the neutral standardized placeholder for an
    # all-missing feature and makes the fit depend only on observed columns.
    med = X.median(numeric_only=True).fillna(0.0)
    X = X.fillna(med).fillna(0.0)
    Xs = StandardScaler().fit_transform(X)

    pca = PCA(n_components=4, random_state=7)
    Z = pca.fit_transform(Xs)
    loadings = {
        f"axis_{i + 1}": dict(
            sorted(
                zip(CLUSTER_FEATURES, [float(v) for v in pca.components_[i]], strict=True),
                key=lambda kv: -abs(kv[1]),
            )[:5]
        )
        for i in range(4)
    }

    best_k, best_bic, best_labels = None, np.inf, None
    for k in range(2, 7):
        gm = GaussianMixture(n_components=k, n_init=8, random_state=7)
        labels = gm.fit_predict(Z)
        bic = gm.bic(Z)
        if bic < best_bic:
            best_k, best_bic, best_labels = k, bic, labels
    g = g.copy()
    g["cluster"] = best_labels

    profiles = (
        g.groupby("cluster")[CLUSTER_FEATURES].median().round(3).reset_index().to_dict("records")
    )
    members = {
        int(c): sorted(g.loc[g["cluster"] == c, "provider"].tolist())
        for c in sorted(g["cluster"].unique())
    }
    summary = {
        "n_providers": int(len(g)),
        "k": int(best_k),
        "pca_explained_var": [
            float(v)
            for v in np.cumsum(
                PCA(n_components=4, random_state=7).fit(Xs).explained_variance_ratio_
            )
        ],
        "axes_top_loadings": loadings,
        "cluster_profiles": profiles,
        "cluster_members": members,
    }
    return g, summary


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    g = build_features()
    save(g, out_dir, "h19_provider_features")
    typed, summary = cluster(g)
    save(typed, out_dir, "h19_provider_types")
    save_json(summary, out_dir, "h19_summary")
    log.info("H19: k=%s over %s providers", summary["k"], summary["n_providers"])
    return summary
