"""CBH-7 (was H76) — The elasticity wedge: routing vs end-user price sensitivity.

Compute Brokerage invariant (i): the intermediary's price elasticity (H4
routing elasticity) exceeds end-user elasticity by an order of magnitude —
the wedge IS the origination rent (PFOF logic: consumers are insensitive,
the broker is sensitive on their behalf, and broker loyalty is what gets
monetized).

End-user benchmark: the OpenRouter 100T-token study (arXiv:2601.10088)
reports a 10% price cut moving usage +0.5–0.7% (elasticity ~ -0.05..-0.07);
Demirer-Fradkin-Tadelis-Peng (NBER w34608) report short-run elasticity
slightly above 1 in magnitude at the model level (which mixes routing and
usage margins). We take the pure end-user range as the comparison.

  h76_summary.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .common import DEFAULT_OUT, save_json
from . import h4_routing

log = logging.getLogger(__name__)

END_USER_ELASTICITY = (-0.05, -0.07)  # arXiv:2601.10088
KILL_THRESHOLD = 3.0  # wedge below this = invariant (i) failing


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    h4_path = Path(out_dir) / "h4_summary.json"
    if h4_path.exists():
        h4 = json.loads(h4_path.read_text())
    else:
        h4 = h4_routing.run(out_dir)
    routing = float(h4["share_price_elasticity"])
    se = float(h4.get("se", 0.0))
    mid_user = sum(END_USER_ELASTICITY) / 2
    wedge = abs(routing) / abs(mid_user)
    wedge_lo = (abs(routing) - 1.96 * se) / abs(END_USER_ELASTICITY[0])
    wedge_hi = (abs(routing) + 1.96 * se) / abs(END_USER_ELASTICITY[1])
    summary = {
        "evidence_status": "provisional_descriptive",
        "routing_elasticity": routing,
        "routing_se": se,
        "end_user_elasticity_range": list(END_USER_ELASTICITY),
        "end_user_source": "arXiv:2601.10088 (OpenRouter 100T-token study)",
        "wedge_point": round(wedge, 1),
        "wedge_range": [round(wedge_lo, 1), round(wedge_hi, 1)],
        "kill_threshold": KILL_THRESHOLD,
        "invariant_i_status": "consistent" if wedge > KILL_THRESHOLD else "inconsistent",
        "read": (
            "wedge >> 1: the router reallocates across providers far more readily than "
            "end demand responds to price — the defining broker-market signature"
        ),
        "claim_boundary": (
            "Routing elasticity is a within-(day, model, variant) share-price "
            "association, not causal; end-user benchmark is an external estimate on "
            "overlapping data. The wedge compares margins of adjustment, not welfare."
        ),
    }
    save_json(summary, out_dir, "cbh7_summary")
    return summary
