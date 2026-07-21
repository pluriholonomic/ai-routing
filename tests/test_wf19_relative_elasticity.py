from __future__ import annotations

import pandas as pd
import pytest

from orcap.analysis import wf19_relative_elasticity as rel


def _labels() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model_id": "z-ai/glm-5.2",
                "provider_name": "Active",
                "provider_type": "active_undercutter",
            },
            {
                "model_id": "z-ai/glm-5.2",
                "provider_name": "Anchor",
                "provider_type": "anchor_adopter",
            },
            {
                "model_id": "z-ai/glm-5.2",
                "provider_name": "Static",
                "provider_type": "static_discounter",
            },
        ]
    )


def _quotes(active_price: float = 0.5) -> pd.DataFrame:
    rows = []
    for index, provider, price in (
        (0, "Active", active_price),
        (1, "Anchor", 1.0),
        (2, "Z.AI", 1.0),
        (3, "Static", 0.8),
    ):
        rows.append(
            {
                "run_ts": "20260721T000000Z",
                "dt": "2026-07-21",
                "model_id": "z-ai/glm-5.2",
                "provider_name": provider,
                "expected_quote_usd": price,
                "row": index,
            }
        )
    return pd.DataFrame(rows)


def test_model_eligibility_requires_both_frozen_types():
    assert rel.eligible_models(_labels()) == ("z-ai/glm-5.2",)
    no_anchor = _labels()[lambda frame: frame.provider_type != "anchor_adopter"]
    assert rel.eligible_models(no_anchor) == ()


def test_benchmark_reset_conserves_share_and_separates_anchor_author_other():
    panel = rel.build_relative_elasticity_panel(_quotes(), _labels(), exponents=(2.0,))
    assert len(panel) == 1
    row = panel.iloc[0]
    assert row.benchmark_source == "model_author"
    assert row.current_undercutters == 1
    assert row.equivalent_active_quote_usd == pytest.approx(0.5)
    assert row.counterfactual_equivalent_active_quote_usd == pytest.approx(1.0)
    assert row.equivalent_active_discount_fraction == pytest.approx(0.5)
    assert row.active_excess_shadow_share > 0
    assert row.anchor_shadow_share_loss > 0
    assert row.author_shadow_share_loss > 0
    assert row.other_shadow_share_loss > 0
    assert row.active_excess_shadow_share == pytest.approx(
        row.anchor_shadow_share_loss + row.author_shadow_share_loss + row.other_shadow_share_loss
    )
    assert row.share_conservation_error == pytest.approx(0.0, abs=1e-12)
    assert row.group_arc_price_elasticity < 0


def test_no_current_benchmark_undercut_has_zero_excess_and_undefined_arc():
    panel = rel.build_relative_elasticity_panel(
        _quotes(active_price=1.1), _labels(), exponents=(2.0,)
    )
    row = panel.iloc[0]
    assert row.current_undercutters == 0
    assert row.active_excess_shadow_share == pytest.approx(0.0)
    assert pd.isna(row.group_arc_price_elasticity)


def test_summary_and_figures_preserve_claim_boundary(tmp_path):
    panels = []
    for index, price in enumerate((0.9, 0.7, 0.5)):
        quotes = _quotes(active_price=price)
        quotes["run_ts"] = f"20260721T0{index}0000Z"
        panels.append(quotes)
    panel = rel.build_relative_elasticity_panel(pd.concat(panels), _labels())
    summary = rel.summarize_relative_elasticity(panel)
    assert summary["models"] == 1
    assert summary["maximum_absolute_share_conservation_error"] < 1e-12
    assert "not realized market share" in summary["boundary"]
    rel.render_cross_model_figures(tmp_path, panel)
    for stem in ("wf19_cross_model_timeseries", "wf19_cross_model_elasticity"):
        assert (tmp_path / f"{stem}.png").is_file()
        assert (tmp_path / f"{stem}.pdf").is_file()
