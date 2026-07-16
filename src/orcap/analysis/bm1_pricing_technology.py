"""BM1 — census of observable provider pricing technologies."""

from __future__ import annotations

from pathlib import Path

from .bm_common import (
    completion_events,
    load_gates,
    provider_cadence,
    quote_exposure_by_provider,
)
from .common import DEFAULT_OUT, save, save_json
from .h68_competition import daily_quotes
from .vintage import clip_date_range, date_support


def run(
    out_dir: Path = DEFAULT_OUT,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    events=None,
    quotes=None,
) -> dict:
    events = (
        completion_events(start_date=start_date, end_date=end_date)
        if events is None
        else clip_date_range(events, start_date=start_date, end_date=end_date)
    )
    quotes = (
        clip_date_range(daily_quotes(), start_date=start_date, end_date=end_date)
        if quotes is None
        else clip_date_range(quotes, start_date=start_date, end_date=end_date)
    )
    quote_providers = set(quotes["provider_name"].dropna())
    exposure_days = int(quotes["dt"].nunique()) if not quotes.empty else 0
    cadence = provider_cadence(
        events,
        quote_providers,
        exposure_days=quote_exposure_by_provider(quotes),
    )
    save(cadence, out_dir, "bm1_provider_cadence")
    span = float(exposure_days)
    gate = load_gates()["brown_mackay"]
    counts = cadence["cadence_class"].value_counts().to_dict() if not cadence.empty else {}
    summary = {
        "evidence_status": (
            "provisional_descriptive" if span >= gate["min_panel_days"] else "power_gated"
        ),
        "panel_span_days": round(span, 2),
        "n_observed_quote_days": exposure_days,
        "required_panel_days": gate["min_panel_days"],
        "n_price_changes": int(len(events)),
        "n_quote_providers": int(len(quote_providers)),
        "n_repricing_providers": int(events["provider_name"].nunique()),
        "cadence_counts": {str(key): int(value) for key, value in counts.items()},
        "analysis_vintage": date_support(quotes),
        "claim_boundary": (
            "Cadence is inferred from public quote changes, not a provider's internal repricing "
            "technology. Rates use observed quote days, not the span between the first and last "
            "price change. The live window left-censors slow providers and cannot identify "
            "adoption."
        ),
    }
    save_json(summary, out_dir, "bm1_summary")
    return summary
