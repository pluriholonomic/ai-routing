"""BM1 — census of observable provider pricing technologies."""

from __future__ import annotations

from pathlib import Path

from .bm_common import completion_events, load_gates, panel_span_days, provider_cadence
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes


def run(out_dir: Path = DEFAULT_OUT) -> dict:
    events = completion_events()
    quote_providers = set(daily_quotes()["provider_name"].dropna())
    cadence = provider_cadence(events, quote_providers)
    save(cadence, out_dir, "bm1_provider_cadence")
    span = panel_span_days(events)
    gate = load_gates()["brown_mackay"]
    counts = cadence["cadence_class"].value_counts().to_dict() if not cadence.empty else {}
    summary = {
        "evidence_status": (
            "provisional_descriptive" if span >= gate["min_panel_days"] else "power_gated"
        ),
        "panel_span_days": round(span, 2),
        "required_panel_days": gate["min_panel_days"],
        "n_price_changes": int(len(events)),
        "n_quote_providers": int(len(quote_providers)),
        "n_repricing_providers": int(events["provider_name"].nunique()),
        "cadence_counts": {str(key): int(value) for key, value in counts.items()},
        "claim_boundary": (
            "Cadence is inferred from public quote changes, not a provider's internal repricing "
            "technology. The live window left-censors slow providers and cannot identify adoption."
        ),
    }
    save_json(summary, out_dir, "bm1_summary")
    return summary
