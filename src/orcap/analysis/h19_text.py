"""H19b — Text features for provider typology.

What a provider *says it is* (own silicon, GPU marketplace, enterprise
platform, agent cloud) complements what it *does* (H19 behavioral features).

Pipeline:
  1. Homepage URL per provider from OpenRouter's all-providers directory
     (embedded in the favicon URL) + pricingStrategy/byokEnabled fields.
  2. Fetch homepage text (cached to data/external/provider_pages.parquet and
     pushed to HF so nightly CI doesn't hammer 75 sites).
  3. TF-IDF (1-2 grams) -> TruncatedSVD 10-dim "embedding" + interpretable
     keyword flags (own_silicon, marketplace, enterprise, serverless, ...).
  4. Merge with h19_provider_features and recluster; compare with
     behavior-only clustering (ARI) and report combined types.

TF-IDF+SVD over ~75 short marketing pages performs comparably to neural
embeddings at this scale and keeps the loadings inspectable.
"""

import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import numpy as np
import pandas as pd

from ..config import DATA_DIR
from .common import DEFAULT_OUT, save, save_json
from .h19_provider_types import CLUSTER_FEATURES, provider_family

log = logging.getLogger(__name__)

PAGES_CACHE = DATA_DIR / "external" / "provider_pages.parquet"

KEYWORDS = {
    "own_silicon": r"\b(our (chip|silicon|hardware)|lpu|rdu|wafer[- ]scale|custom (chip|silicon|accelerator)|asic)\b",  # noqa: E501
    "gpu_marketplace": r"\b(marketplace|rent (a )?gpu|spot (instance|pricing)|bid|decentralized|depin|peer[- ]to[- ]peer)\b",  # noqa: E501
    "enterprise": r"\b(enterprise|soc ?2|hipaa|compliance|sla|dedicated (capacity|instances))\b",
    "serverless": r"\b(serverless|autoscal\w+|scale to zero)\b",
    "open_source_focus": r"\b(open[- ]?source|open[- ]?weight)\b",
    "price_led": r"\b(cheapest|lowest (cost|price)|affordable|cost[- ]effective|per[- ]token pricing)\b",  # noqa: E501
    "agents_focus": r"\b(agents?|agentic)\b",
    "gpu_cloud": r"\b(gpu cloud|bare[- ]metal|clusters?|h100|b200|nvidia)\b",
    "research_lab": r"\b(frontier|research lab|foundation model|we train|our model)\b",
}


def _provider_homepage_frame(body: dict | None) -> pd.DataFrame:
    """Normalize the provider directory, including an empty/unavailable response."""
    columns = ["slug", "provider", "homepage", "pricing_strategy", "byok_enabled"]
    rows = []
    for p in (body or {}).get("data", []):
        icon = ((p.get("icon") or {}).get("url")) or ""
        q = parse_qs(urlparse(icon).query)
        home = (q.get("url") or [None])[0]
        rows.append(
            {
                "slug": p.get("slug"),
                "provider": provider_family(p.get("displayName") or p.get("name")),
                "homepage": home,
                "pricing_strategy": p.get("pricingStrategy"),
                "byok_enabled": bool(p.get("byokEnabled")),
            }
        )
    df = pd.DataFrame(rows, columns=columns).drop_duplicates("provider")
    return df[df["homepage"].notna()]


def provider_homepages() -> pd.DataFrame:
    import asyncio

    from ..http import Fetcher, make_client

    async def _get():
        async with make_client() as client:
            f = Fetcher(client, rps=2)
            return await f.get_json("https://openrouter.ai/api/frontend/all-providers")

    body = asyncio.run(_get())
    return _provider_homepage_frame(body)


_TAGS = re.compile(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_META = re.compile(
    r'<meta[^>]+(?:name="description"|property="og:description"|property="og:title")'
    r'[^>]+content="([^"]*)"',
    re.IGNORECASE,
)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)
_JUNK = re.compile(r"\b(www|png|svg|webp|jpg|http\S*|js|css|cookie(s)?|javascript|amp|quot)\b")


def _html_to_text(h: str) -> str:
    import html as htmllib

    # meta descriptions and titles survive even in JS-shell pages; weight them 3x
    meta = " ".join(_META.findall(h)) or ""
    title = " ".join(_TITLE.findall(h))
    body = _TAG.sub(" ", _TAGS.sub(" ", h))
    doc = f"{title} {(meta + ' ') * 3} {body[:12000]}"
    doc = htmllib.unescape(doc)
    doc = _JUNK.sub(" ", doc.lower())
    return _WS.sub(" ", doc).strip()


def fetch_pages(homes: pd.DataFrame, force: bool = False) -> pd.DataFrame:
    if PAGES_CACHE.exists() and not force:
        return pd.read_parquet(PAGES_CACHE)
    rows = []
    with httpx.Client(
        timeout=20,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (orcap research; contact: tarun@gauntlet.xyz)"},
    ) as client:
        for r in homes.itertuples(index=False):
            text = ""
            for path in ("", "about"):
                try:
                    url = r.homepage.rstrip("/") + ("/" + path if path else "")
                    resp = client.get(url)
                    if resp.status_code == 200:
                        text += " " + _html_to_text(resp.text)[:20000]
                except Exception as exc:
                    log.debug("%s %s: %s", r.provider, path, exc)
            rows.append({"provider": r.provider, "homepage": r.homepage, "text": text.strip()})
            log.info("fetched %s (%d chars)", r.provider, len(text))
    df = pd.DataFrame(rows)
    PAGES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PAGES_CACHE, index=False)
    return df


def text_features(pages: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer

    pages = pages[pages["text"].str.len() > 80].copy()
    low = pages["text"].str.lower()
    for name, pat in KEYWORDS.items():
        pages[f"kw_{name}"] = low.str.contains(pat, regex=True).astype(float)

    vec = TfidfVectorizer(
        stop_words="english", ngram_range=(1, 2), min_df=2, max_features=3000, sublinear_tf=True
    )
    X = vec.fit_transform(pages["text"])
    k = min(10, X.shape[0] - 1, X.shape[1] - 1)
    svd = TruncatedSVD(n_components=k, random_state=7)
    Z = svd.fit_transform(X)
    Z = Z / (np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9)
    for i in range(k):
        pages[f"txt_{i}"] = Z[:, i]

    terms = np.array(vec.get_feature_names_out())
    axis_terms = {
        f"txt_{i}": [str(t) for t in terms[np.argsort(-np.abs(svd.components_[i]))[:8]]]
        for i in range(min(k, 5))
    }
    return pages.drop(columns=["text"]), axis_terms


def combined_cluster(behav: pd.DataFrame, text: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    from sklearn.metrics import adjusted_rand_score, silhouette_score
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    m = behav.merge(text, on="provider", how="inner")
    kw_cols = [c for c in m.columns if c.startswith("kw_")]
    txt_cols = [c for c in m.columns if c.startswith("txt_")]

    def _matrix(cols):
        X = m[cols].apply(pd.to_numeric, errors="coerce")
        X = X.replace([np.inf, -np.inf], np.nan)
        # A live feature can be unobserved for every matched provider. Median
        # imputation alone leaves such a column NaN, which StandardScaler and
        # GaussianMixture reject. Keep it as a neutral constant instead.
        med = X.median(numeric_only=True).fillna(0.0)
        X = X.fillna(med).fillna(0.0)
        return StandardScaler().fit_transform(X)

    Xb = _matrix(CLUSTER_FEATURES)
    Xc = np.hstack([Xb, _matrix(kw_cols + txt_cols) * 0.7])

    k = 5
    lab_b = GaussianMixture(k, n_init=10, random_state=7).fit_predict(Xb)
    lab_c = GaussianMixture(k, n_init=10, random_state=7).fit_predict(Xc)
    m["cluster_behavior"] = lab_b
    m["cluster_combined"] = lab_c

    members = {
        int(c): sorted(m.loc[m["cluster_combined"] == c, "provider"]) for c in sorted(set(lab_c))
    }
    kw_profile = m.groupby("cluster_combined")[kw_cols].mean().round(2).reset_index()
    summary = {
        "n_providers": int(len(m)),
        "ari_behavior_vs_combined": float(adjusted_rand_score(lab_b, lab_c)),
        "silhouette_behavior": float(silhouette_score(Xb, lab_b)),
        "silhouette_combined": float(silhouette_score(Xc, lab_c)),
        "keyword_rates_by_cluster": kw_profile.to_dict("records"),
        "cluster_members_combined": members,
    }
    return m, summary


def run(out_dir: Path = DEFAULT_OUT, force_fetch: bool = False) -> dict:
    homes = provider_homepages()
    pages = fetch_pages(homes, force=force_fetch)
    tf, axis_terms = text_features(pages)
    tf = tf.merge(
        homes[["provider", "pricing_strategy", "byok_enabled"]], on="provider", how="left"
    )
    save(tf, out_dir, "h19b_text_features")

    behav_path = Path(out_dir) / "h19_provider_features.parquet"
    if not behav_path.exists():
        from .h19_provider_types import build_features

        behav = build_features()
    else:
        behav = pd.read_parquet(behav_path)
    typed, summary = combined_cluster(behav, tf)
    summary["text_axis_terms"] = axis_terms
    save(typed, out_dir, "h19b_combined_types")
    save_json(summary, out_dir, "h19b_summary")
    log.info(
        "H19b: %s providers, ARI %.2f", summary["n_providers"], summary["ari_behavior_vs_combined"]
    )
    return summary
