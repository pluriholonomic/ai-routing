import pandas as pd
import pytest

from orcap.analysis.h48_capacity_mechanism import allocation_calibration


def test_h48_calibrates_theoretical_elasticity_from_public_allocation_share():
    panel = allocation_calibration(
        pd.DataFrame(
            [
                {
                    "run_ts": "20260710T000000Z",
                    "model_id": "model-a",
                    "scenario": "short",
                    "provider_name": "provider-a",
                    "simulated_route_share": 0.8,
                    "expected_quote_usd": 0.01,
                }
            ]
        )
    )
    assert panel.iloc[0]["mechanism_eta"] == 2.0
    assert panel.iloc[0]["predicted_own_price_share_elasticity"] == pytest.approx(-0.4)
