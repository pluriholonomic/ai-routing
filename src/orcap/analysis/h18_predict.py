"""H18 — Interpretable prediction of repricing events (layer 1: wayback panel).

See docs/predictive-model-plan.md. Unit = consecutive snapshot pair per model;
target = listed completion price changed over the window. Temporal split,
exposure-stripped headline AUC, logistic coefficients + tree importances,
plus a conditional direction (cut vs raise) model.
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import data
from .common import DEFAULT_OUT, save, save_json

log = logging.getLogger(__name__)

TRAIN_CUTOFF = "2026-02-01"

EXPOSURE_FEATURES = ["log_gap_days"]
FEATURES = [
    "log_age_days",
    "is_young_30d",
    "n_prior_changes",
    "log_days_since_change",
    "never_changed",
    "n_snapshots_seen",
    "log_price",
    "price_pctile_market",
    "price_pctile_author",
    "author_n_models",
    "log_days_since_author_launch",
    "market_launches_30d",
    "log_weekly_tokens",
    "tokens_missing",
    "month_index",
    "author_prior_change_rate",
]


def add_history_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Author-level historical repricing propensity, strictly from pairs that
    completed (t1) before this pair's start (t0) — leak-free by construction."""
    df = df.reset_index(drop=True).copy()
    df["author"] = df["model_id"].str.split("/").str[0]
    global_prior = 0.027
    out = np.full(len(df), global_prior)
    t0_ns = df["t0"].astype("int64").to_numpy()
    for _author, g in df.groupby("author"):
        g = g.sort_values("t1")
        t1_ns = g["t1"].astype("int64").to_numpy()
        cum = np.cumsum(g["changed"].to_numpy().astype(float))
        for row_pos in g.index:
            k = int(np.searchsorted(t1_ns, t0_ns[row_pos], side="right"))
            if k >= 5:  # need some history before trusting the rate
                out[row_pos] = cum[k - 1] / k
    df["author_prior_change_rate"] = out
    return df


def build_dataset() -> pd.DataFrame:
    panel = data.q(
        f"""
        select id as model_id, run_ts, price_completion,
               max(created) over (partition by id) as created_epoch
        from {data.wayback_models()}
        where price_completion > 0 and id not like '%:free'
        """
    ).df()
    panel["ts"] = pd.to_datetime(panel["run_ts"], format="%Y%m%dT%H%M%SZ", utc=True)
    # early-2023 snapshots predate the `created` field; fall back to first-seen
    epochs = pd.to_numeric(panel["created_epoch"], errors="coerce").to_numpy(
        dtype="float64", na_value=np.nan
    )
    panel["created"] = pd.to_datetime(epochs, unit="s", utc=True)
    first_seen = panel.groupby("model_id")["ts"].transform("min")
    panel["created"] = panel["created"].fillna(first_seen)
    panel["author"] = panel["model_id"].str.split("/").str[0]
    panel = panel.drop_duplicates(["model_id", "ts"]).sort_values(["model_id", "ts"])

    # market-level percentile of price at each snapshot
    panel["price_pctile_market"] = panel.groupby("run_ts")["price_completion"].rank(pct=True)
    panel["price_pctile_author"] = panel.groupby(["run_ts", "author"])["price_completion"].rank(
        pct=True
    )

    # author roster + market launches, computed per snapshot timestamp
    firsts = panel.groupby("model_id")["created"].min().reset_index()
    firsts_by_author = panel.groupby("model_id").agg(
        created=("created", "min"), author=("author", "first")
    )

    weekly = data.q(
        f"""select week, model_id, total_tokens
        from read_parquet('{data.table_glob("rankings_weekly")}')"""
    ).df()
    weekly["week"] = pd.to_datetime(weekly["week"], utc=True)
    weekly = weekly.groupby(["week", "model_id"], as_index=False)["total_tokens"].max()

    rows = []
    for model_id, g in panel.groupby("model_id"):
        g = g.reset_index(drop=True)
        author = g["author"].iat[0]
        created = g["created"].iat[0]
        change_times: list[pd.Timestamp] = []
        for i in range(len(g) - 1):
            t0, t1 = g["ts"].iat[i], g["ts"].iat[i + 1]
            p0, p1 = g["price_completion"].iat[i], g["price_completion"].iat[i + 1]
            age = max(0.04, (t0 - created).total_seconds() / 86400)
            author_models = firsts_by_author[
                (firsts_by_author["author"] == author) & (firsts_by_author["created"] <= t0)
            ]
            last_launch = author_models["created"].max()
            launches_30d = int((firsts["created"].between(t0 - pd.Timedelta("30D"), t0)).sum())
            since_change = (
                (t0 - change_times[-1]).total_seconds() / 86400 if change_times else np.nan
            )
            wk = weekly[(weekly["model_id"] == model_id) & (weekly["week"] <= t0)]["total_tokens"]
            tokens = float(wk.iloc[-1]) if len(wk) else np.nan
            rows.append(
                {
                    "model_id": model_id,
                    "t0": t0,
                    "t1": t1,
                    "changed": p0 != p1,
                    "dlog": float(np.log(p1 / p0)),
                    "log_gap_days": float(np.log(max(0.04, (t1 - t0).total_seconds() / 86400))),
                    "log_age_days": float(np.log(age)),
                    "is_young_30d": float(age < 30),
                    "n_prior_changes": float(len(change_times)),
                    "log_days_since_change": float(np.log1p(since_change))
                    if not np.isnan(since_change)
                    else 0.0,
                    "never_changed": float(len(change_times) == 0),
                    "n_snapshots_seen": float(i + 1),
                    "log_price": float(np.log(p0)),
                    "price_pctile_market": float(g["price_pctile_market"].iat[i]),
                    "price_pctile_author": float(g["price_pctile_author"].iat[i]),
                    "author_n_models": float(len(author_models)),
                    "log_days_since_author_launch": float(
                        np.log1p(max(0.0, (t0 - last_launch).total_seconds() / 86400))
                    ),
                    "market_launches_30d": float(launches_30d),
                    "log_weekly_tokens": float(np.log1p(tokens)) if not np.isnan(tokens) else 0.0,
                    "tokens_missing": float(np.isnan(tokens)),
                    "month_index": float((t0.year - 2023) * 12 + t0.month),
                }
            )
            if p0 != p1:
                change_times.append(t1)
    return pd.DataFrame(rows)


def fit_eval(df: pd.DataFrame, use_exposure: bool) -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    feats = FEATURES + (EXPOSURE_FEATURES if use_exposure else [])
    cutoff = pd.Timestamp(TRAIN_CUTOFF, tz="UTC")
    train, test = df[df["t1"] <= cutoff], df[df["t1"] > cutoff]
    Xtr, ytr = train[feats].to_numpy(), train["changed"].to_numpy()
    Xte, yte = test[feats].to_numpy(), test["changed"].to_numpy()

    logit = make_pipeline(
        StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")
    )
    logit.fit(Xtr, ytr)
    p_logit = logit.predict_proba(Xte)[:, 1]

    tree = HistGradientBoostingClassifier(
        max_depth=3, max_iter=300, learning_rate=0.06, random_state=7
    )
    tree.fit(Xtr, ytr)
    p_tree = tree.predict_proba(Xte)[:, 1]

    coefs = dict(
        zip(
            feats, [float(c) for c in logit.named_steps["logisticregression"].coef_[0]], strict=True
        )
    )
    perm = permutation_importance(tree, Xte, yte, n_repeats=5, random_state=7, scoring="roc_auc")
    importances = dict(zip(feats, [float(v) for v in perm.importances_mean], strict=True))

    return {
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "test_base_rate": float(yte.mean()),
        "auc_logit": float(roc_auc_score(yte, p_logit)),
        "auc_tree": float(roc_auc_score(yte, p_tree)),
        "pr_auc_logit": float(average_precision_score(yte, p_logit)),
        "pr_auc_tree": float(average_precision_score(yte, p_tree)),
        "logit_coefs_std": dict(sorted(coefs.items(), key=lambda kv: -abs(kv[1]))),
        "tree_perm_importance": dict(sorted(importances.items(), key=lambda kv: -kv[1])[:8]),
    }


def fit_direction(df: pd.DataFrame) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    ch = df[df["changed"]].copy()
    ch["is_cut"] = (ch["dlog"] < 0).astype(int)
    cutoff = pd.Timestamp(TRAIN_CUTOFF, tz="UTC")
    train, test = ch[ch["t1"] <= cutoff], ch[ch["t1"] > cutoff]
    if len(test) < 30 or train["is_cut"].nunique() < 2:
        return {"note": "insufficient direction sample", "n_test": int(len(test))}
    m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
    m.fit(train[FEATURES], train["is_cut"])
    p = m.predict_proba(test[FEATURES])[:, 1]
    coefs = dict(
        zip(FEATURES, [float(c) for c in m.named_steps["logisticregression"].coef_[0]], strict=True)
    )
    return {
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "test_cut_share": float(test["is_cut"].mean()),
        "auc_direction": float(roc_auc_score(test["is_cut"], p)),
        "coefs_std": dict(sorted(coefs.items(), key=lambda kv: -abs(kv[1]))[:8]),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    df = build_dataset()
    df = add_history_rates(df)
    save(df, out_dir, "h18_dataset")
    results = {
        "dataset": {
            "n_pairs": int(len(df)),
            "n_positives": int(df["changed"].sum()),
            "base_rate": float(df["changed"].mean()),
        },
        "with_exposure": fit_eval(df, use_exposure=True),
        "no_exposure_headline": fit_eval(df, use_exposure=False),
        "direction_given_change": fit_direction(df),
    }
    save_json(results, out_dir, "h18_summary")
    log.info("H18: %s", results)
    return results
