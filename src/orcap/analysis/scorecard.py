"""Compute Brokerage Hypothesis scorecard.

Grades each pre-registered prediction (docs/compute-brokerage-hypothesis.md)
from the latest analysis summaries. Statuses: untested | accumulating |
consistent | inconsistent | killed | confirmed-dated. Grading uses only the
pre-registered criteria; anything else is 'accumulating'.

  hypothesis_scorecard.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .common import DEFAULT_OUT, save_json

log = logging.getLogger(__name__)


def _load(out_dir: Path, name: str) -> dict:
    p = Path(out_dir) / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    h70 = _load(out_dir, "cbh1_summary")
    h71 = _load(out_dir, "cbh2_summary")
    h72 = _load(out_dir, "cbh3_summary")
    h74 = _load(out_dir, "cbh5_summary")
    h76 = _load(out_dir, "cbh7_summary")
    h13 = _load(out_dir, "h13_summary")
    pm1 = _load(out_dir, "pm1_summary")
    pm2 = _load(out_dir, "pm2_summary")
    pm5 = _load(out_dir, "pm5_summary")
    pm6 = _load(out_dir, "pm6_summary")
    pm9 = _load(out_dir, "pm9_summary")
    wf2 = _load(out_dir, "wf2_summary")
    wf3 = _load(out_dir, "wf3_summary")
    wf4 = _load(out_dir, "wf4_summary")
    wf5 = _load(out_dir, "wf5_summary")
    wf6 = _load(out_dir, "wf6_summary")
    wf9 = _load(out_dir, "wf9_summary")

    rows = []

    def add(pred: str, status: str, evidence: str, source: str) -> None:
        rows.append({"prediction": pred, "status": status, "evidence": evidence, "source": source})

    # invariant (i): elasticity wedge
    if h76:
        add(
            "invariant-i elasticity wedge",
            h76.get("invariant_i_status", "accumulating"),
            f"wedge {h76.get('wedge_point')}x (range {h76.get('wedge_range')})",
            "cbh7",
        )
    # invariant (ii): quantity clears, price administers
    if h72:
        pm, rm = (
            h72.get("share_endpoints_price_ever_moved"),
            h72.get("share_endpoints_rate_limit_ever_moved"),
        )
        status = (
            "consistent"
            if pm is not None and rm is not None and pm < 0.2 < rm
            else "accumulating"
        )
        add(
            "invariant-ii quantity clears / price administers",
            status,
            f"price ever-moved {pm:.0%} vs rate-limit {rm:.0%} over {h72.get('n_days')}d"
            if pm is not None
            else "no panel",
            "cbh3",
        )
    # Q1/Q2 two-speed dealer market
    if h74 and h74.get("slow_over_fast_premium_pct") is not None:
        prem = h74["slow_over_fast_premium_pct"]
        lo, hi = h74.get("beta_ci95", [None, None])
        status = "consistent" if 10 <= prem <= 30 and lo is not None and hi < 0 else "accumulating"
        add(
            "Q1 slow-over-fast price premium 10-30%",
            status,
            f"premium {prem:.1f}% (Brown-MacKay band 10-30)",
            "cbh5",
        )
    if h70:
        add(
            "Q2 algorithmic saturation vs margins (Assad)",
            "accumulating",
            f"{h70.get('n_algorithmic_v0')}/{h70.get('n_providers_scored')} active repricers; "
            f"rank beta {h70.get('rank_beta_algo_share_on_markup')} "
            "(v0 census, no all-algo markets yet)",
            "cbh1",
        )
    # Q3 dispersion floor
    if h71:
        hi_gap = h71.get("gap_at_n10plus_median_pct")
        status = "consistent" if hi_gap is not None and hi_gap >= 3.0 else "accumulating"
        add(
            "Q3 dispersion floor >=3% at high N",
            status,
            f"median gap at N>=10: {hi_gap:.1f}%; exact-tie share "
            f"{h71.get('share_exact_tie_at_min'):.0%}"
            if hi_gap is not None
            else "insufficient",
            "cbh2",
        )
    # Q collusion-signature watch: superseded by pm6's sign/persistence
    # reclassification below (cbh4's typing conflated experimentation with
    # punishment); cbh4 remains as the raw event feed.
    # R2 hidden spread stays 0
    if h13:
        share_zero = h13.get("share_exact_zero_basis")
        status = "consistent" if share_zero is not None and share_zero > 0.95 else "accumulating"
        add(
            "R2 hidden router spread == 0",
            status,
            f"exact-zero basis share {share_zero}" if share_zero is not None else "gated",
            "h13",
        )
    # pricing-model ladder (pm-series)
    if pm1.get("ladder"):
        lad = pm1["ladder"]
        l4p = lad.get("L4", {}).get("lr_p_vs_previous")
        gap = lad.get("L3", {}).get("key_coefs", {}).get("abs_gap")
        add(
            "PM ladder: state-dependent + strategic, no congestion, not Calvo",
            "consistent" if gap and gap > 0 and l4p and float(l4p) > 0.05 else "accumulating",
            f"|gap| coef {gap}; congestion rung p={l4p}; "
            f"L2 vs Calvo p={lad.get('L2', {}).get('lr_p_vs_previous')}",
            "pm1",
        )
    if pm2.get("kurtosis_within_provider_standardized"):
        k = pm2["kurtosis_within_provider_standardized"]
        add(
            "PM sufficient statistic: CalvoPlus mixture (1 < Kur < 6)",
            "consistent" if 1.5 < k < 5.5 else "inconsistent",
            f"within-standardized kurtosis {k} (menu-cost 1, Calvo 6)",
            "pm2",
        )
    if pm5.get("focality"):
        f = pm5["focality"]
        identity = f.get("author_identity_audit", {})
        atom = identity.get("all_market_author_price_atom", {})
        anchor = identity.get("author_anchor_randomization_benchmark", {})
        excess = atom.get("exact_minus_placebo")
        anchor_excess = (anchor.get("author_minus_random_anchor") or {}).get("mean")
        anchor_p = anchor.get("poisson_binomial_upper_tail_p")
        if excess is not None and anchor_excess is not None:
            add(
                "Exact price atoms are author-specific",
                "inconsistent" if anchor_p is not None and anchor_p > 0.05 else "accumulating",
                f"adjacent-grid excess {excess:.0%}, but author-minus-random-anchor "
                f"{anchor_excess:.1%} (exact upper-tail p={anchor_p:.3f}); "
                f"identity status {f.get('author_identity_status')}",
                "pm5",
            )
        else:
            add(
                "Exact price atoms are author-specific",
                "accumulating",
                "price-multiplicity-preserving author-anchor audit missing",
                "pm5",
            )
        landing = (pm5.get("reference_price_landing") or {}).get("primary") or {}
        provider_control = (pm5.get("reference_price_landing") or {}).get(
            "same_provider_across_model_control"
        ) or {}
        landing_excess = landing.get("exact_minus_global_menu")
        historical_excess = landing.get("exact_minus_historical_menu")
        historical_text = (
            f"{historical_excess:.1%}" if historical_excess is not None else "unavailable"
        )
        landing_ci = (landing.get("model_cluster_global_menu") or {}).get(
            "cluster_bootstrap_ci95"
        )
        if landing_excess is not None:
            supported = bool(landing_ci and landing_ci[0] > 0)
            novel = provider_control.get("own_menu_novel_reference_landing") or {}
            novel_ci = (novel.get("model_cluster_global_menu") or {}).get(
                "cluster_bootstrap_ci95"
            )
            add(
                "Lagged rival-price landing exceeds a matched common-menu null",
                "accumulating" if supported else "inconsistent",
                f"exact share {landing.get('exact_lagged_rival_match_share'):.1%}; "
                f"matched-menu excess {landing_excess:.1%}; model-cluster CI {landing_ci}; "
                f"past-only same-model excess {historical_text}; "
                f"own-menu-novel excess {novel.get('exact_minus_global_menu')}; "
                f"novel CI {novel_ci}; "
                f"n={landing.get('n_events')}",
                "pm5",
            )
        association = provider_control.get("model_cluster_association") or {}
        if association.get("difference") is not None:
            add(
                "Same-provider cross-model menu support explains lagged landings",
                (
                    "accumulating"
                    if association.get("difference", 0) > 0
                    and (association.get("cluster_bootstrap_ci95") or [None])[0]
                    is not None
                    and association["cluster_bootstrap_ci95"][0] > 0
                    else "inconsistent"
                ),
                f"own-menu exact share {provider_control.get('own_menu_exact_share'):.1%}; "
                f"landing-minus-nonlanding association {association.get('difference'):.1%}; "
                f"model-cluster CI {association.get('cluster_bootstrap_ci95')}; "
                f"comparable n={provider_control.get('n_comparable_events')}",
                "pm5",
            )
    if pm6.get("by_initiator_sign"):
        cut = pm6["by_initiator_sign"].get("cut", {})
        add(
            "Q reaction dynamics (reclassified)",
            "accumulating",
            f"true punish-and-revert {cut.get('punish_and_revert', 0):.0%} vs "
            f"initiator-withdrawn {cut.get('cut_withdrawn', 0):.0%} of cut events; "
            f"raises followed "
            f"{pm6['by_initiator_sign'].get('raise', {}).get('followed_leadership', 0):.0%}",
            "pm6",
        )
    if pm9.get("share_author_moves_matched_within_96h") is not None:
        add(
            "Author-anchor: active following vs launch-and-forget",
            "accumulating",
            f"{pm9['share_author_moves_matched_within_96h']:.0%} of author repricings "
            f"matched exactly within 96h (n={pm9['n_author_moves_evaluated']})",
            "pm9",
        )
    # welfare-framework (wf-series) tests
    if wf6.get("phi_dlogreq30m_on_rlshare") is not None:
        phi = wf6["phi_dlogreq30m_on_rlshare"]
        lo = wf6.get("phi_ci95", [None])[0]
        add(
            "C7 retry externality (unpriced retries amplify demand)",
            "consistent" if lo is not None and lo > 0 else "accumulating",
            f"phi={phi} {wf6.get('phi_ci95')} — rate-limit spikes RAISE requests 30m later",
            "wf6",
        )
    if wf2.get("mean_selection_share_by_cell"):
        add(
            "C2/JRW: router steering memory (rewards past undercutting?)",
            "accumulating",
            "cheapest w/ recent cut selected "
            f"{wf2['mean_selection_share_by_cell'].get('(True, True)')}"
            f" vs w/o {wf2['mean_selection_share_by_cell'].get('(True, False)')} — "
            "past cuts penalized, not rewarded (collusion-neutral static steering or worse)",
            "wf2",
        )
    if wf3.get("median_regret_pct_movers") is not None:
        add(
            "Conduct: calibrated regret of price movers",
            "accumulating",
            f"median regret {wf3['median_regret_pct_movers']}% (p90 "
            f"{wf3['p90_regret_pct_movers']}%) vs best own constant price — "
            "not textbook best response; attribution open (share-model misspec / "
            "experimentation / threats)",
            "wf3",
        )
    if wf4.get("median_rival_dlogp_6m") is not None:
        add(
            "B-M technology stage: adoption raises rival prices",
            "accumulating",
            f"median rival dlogp {wf4['median_rival_dlogp_6m']} over 6m across "
            f"{wf4['n_adoption_events']} adoption events — no elevation detected; "
            "rigidity dominates",
            "wf4",
        )
    if wf5.get("rank_beta_cadence_gap") is not None:
        add(
            "Dispersion horse race: commitment vs loyal flow",
            "accumulating",
            f"cadence beta {wf5['rank_beta_cadence_gap']} {wf5['cadence_ci95']}, "
            f"hhi beta {wf5['rank_beta_demand_hhi']} {wf5['hhi_ci95']} — both ~0, "
            "gap floor unexplained at current power",
            "wf5",
        )
    if wf9.get("median_core_utilization") is not None:
        add(
            "Umbrella cross-section: core-slack vs fringe-hot",
            "accumulating",
            f"core util {wf9['median_core_utilization']} vs fringe "
            f"{wf9['median_fringe_utilization']}; fringe hotter in "
            f"{wf9['share_models_fringe_hotter']:.0%} of {wf9['n_models']} models "
            "(weakly toward the collusion cell; tiny n)",
            "wf9",
        )
    # dated trackers not yet measurable
    for pred in (
        "O1 harness markup >=15% through 2027",
        "O2 explicit PFOF within 18mo",
        "R1 router take <3% or >=15pt share migration by end-2027",
        "R3 auction mechanism within 24mo",
        "R4 2-4 routers >=85% within 24mo",
        "P1 provisioned-capacity share rises (PJM path)",
        "P2 time-varying pricing within 24mo",
        "P3 futures basis <5% + two-sided OI",
        "I1 divergence rises with discount",
        "X2 >=3 cross-layer acquisitions within 24mo",
    ):
        add(pred, "untested", "tracker not yet instrumented or window open", "phase-3")

    result = {"predictions": rows}
    save_json(result, out_dir, "hypothesis_scorecard")
    return result
