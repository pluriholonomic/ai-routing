import pandas as pd

from orcap.analysis.missingness_bounds import bounded_mean, difference_bounds


def test_bounded_mean_uses_row_specific_upper_support_for_missing_values():
    result = bounded_mean(
        pd.Series([1.0, None, 3.0]),
        lower=0.0,
        upper=pd.Series([5.0, 4.0, 5.0]),
    )

    assert result["observed"] == 2
    assert result["missing"] == 1
    assert result["mean_lower_bound"] == 4 / 3
    assert result["mean_upper_bound"] == 8 / 3
    assert result["upper_support_complete_for_missing"] is True


def test_bounded_mean_refuses_unidentified_or_violated_upper_bound():
    unidentified = bounded_mean(pd.Series([1.0, None]), upper=None)
    violated = bounded_mean(pd.Series([6.0, None]), upper=pd.Series([5.0, 5.0]))

    assert unidentified["mean_lower_bound"] == 0.5
    assert unidentified["mean_upper_bound"] is None
    assert violated["observed_upper_support_violations"] == 1
    assert violated["mean_upper_bound"] is None


def test_difference_bounds_combines_arm_extremes():
    positive = {"mean_lower_bound": 2.0, "mean_upper_bound": 5.0}
    negative = {"mean_lower_bound": 1.0, "mean_upper_bound": 3.0}

    assert difference_bounds(positive, negative) == (-1.0, 4.0)
