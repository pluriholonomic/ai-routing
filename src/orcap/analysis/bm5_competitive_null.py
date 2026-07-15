"""BM5 — predictive horse race before any collusion interpretation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .common import DEFAULT_OUT, save, save_json
from .pm1_hazard_baseline import build_panel, design


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _predictive_test(panel: pd.DataFrame, rung: int) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    days = sorted(panel["dt"].unique())
    cut = max(1, int(len(days) * 0.7))
    train_mask = panel["dt"].isin(days[:cut]).to_numpy()
    test_mask = ~train_mask
    x, _ = design(panel, rung)
    y = panel["event"].astype(int).to_numpy()
    if train_mask.sum() < 50 or test_mask.sum() < 20 or len(np.unique(y[test_mask])) < 2:
        return {
            "error": "insufficient temporal holdout or outcome variation",
            "n_train": int(train_mask.sum()),
            "n_test": int(test_mask.sum()),
        }
    fit = LogisticRegression(C=1.0, max_iter=2000).fit(x[train_mask], y[train_mask])
    probability = fit.predict_proba(x[test_mask])[:, 1]
    return {
        "n_train": int(train_mask.sum()),
        "n_test": int(test_mask.sum()),
        "events_test": int(y[test_mask].sum()),
        "log_loss": float(log_loss(y[test_mask], probability)),
        "brier": float(brier_score_loss(y[test_mask], probability)),
        "auc": float(roc_auc_score(y[test_mask], probability)),
    }


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    panel = build_panel()
    state = _predictive_test(panel, 3)
    strategic = _predictive_test(panel, 5)
    bm3 = _read_json(out_dir / "bm3_summary.json")
    bm4 = _read_json(out_dir / "bm4_summary.json")
    bm2 = _read_json(out_dir / "bm2_summary.json")
    pm6 = _read_json(out_dir / "pm6_summary.json")
    bm_joint_ready = all(
        item.get("evidence_status") == "provisional_descriptive" for item in (bm2, bm3, bm4)
    )
    models = [
        {
            "model": "state-dependent menu-cost null",
            "evidence": "temporal L3 repricing-hazard score",
            "status": "estimated" if "log_loss" in state else "power_gated",
            "holdout_log_loss": state.get("log_loss"),
        },
        {
            "model": "Brown-MacKay asynchronous competitive null",
            "evidence": "quality-adjusted cadence premium plus temporal reaction-rule score",
            "status": (
                "provisional_descriptive"
                if bm_joint_ready
                else "power_gated"
            ),
            "holdout_log_loss": strategic.get("log_loss"),
        },
        {
            "model": "Edgeworth restoration / capacity cycling",
            "evidence": "cut-punishment and reversion taxonomy",
            "status": pm6.get("evidence_status", "not_estimated"),
            "holdout_log_loss": None,
        },
        {
            "model": "Green-Porter / algorithmic collusion",
            "evidence": "requires margins or costs, persistent causal IRFs, and regret tests",
            "status": "not_identified",
            "holdout_log_loss": None,
        },
    ]
    comparison = pd.DataFrame(models)
    save(comparison, out_dir, "bm5_model_comparison")
    improvement = None
    if "log_loss" in state and "log_loss" in strategic:
        improvement = state["log_loss"] - strategic["log_loss"]
    summary = {
        "evidence_status": (
            "provisional_descriptive"
            if improvement is not None and bm_joint_ready
            else "power_gated"
        ),
        "n_pair_days": int(len(panel)),
        "n_days": int(panel["dt"].nunique()),
        "state_dependent_L3": state,
        "strategic_L5": strategic,
        "strategic_log_loss_improvement": improvement,
        "preferred_interpretation_rule": (
            "Prefer Brown-MacKay only if strategic features improve temporal holdout performance "
            "and the quality-adjusted cadence and fast-on-slow reaction predictions both survive."
        ),
        "collusion_verdict": "not_identified",
        "claim_boundary": (
            "This screens competitive structural twins before collusion. It cannot identify "
            "profits, common pricing vendors, private signals, or tacit coordination."
        ),
    }
    save_json(summary, out_dir, "bm5_summary")
    return summary
