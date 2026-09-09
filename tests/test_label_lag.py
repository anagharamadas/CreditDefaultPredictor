"""Label-lag monitoring: horizon filtering, coverage, and the bias it corrects."""

import numpy as np
import pandas as pd
import pytest

from credit_default.label_lag import (
    compare_views,
    known_at_horizon,
    performance_by_month,
)


def _timing(rows):
    """rows: (loan_id, issue_month, label, months_to_resolution)."""
    return pd.DataFrame(rows, columns=["loan_id", "issue_month", "label", "months_to_resolution"])


def test_horizon_filters_by_time_to_resolution():
    timing = _timing([
        ("1", "2017-01", 1, 6.0),
        ("2", "2017-01", 0, 30.0),
        ("3", "2017-01", None, np.nan),   # never resolved: censored
    ])
    assert set(known_at_horizon(timing, 12)["loan_id"]) == {"1"}
    assert set(known_at_horizon(timing, 36)["loan_id"]) == {"1", "2"}
    assert set(known_at_horizon(timing, None)["loan_id"]) == {"1", "2"}  # naive: all resolved


def test_censored_loans_are_never_evaluable():
    """A loan with no outcome must not be counted as anything — not as a repayment,
    which is the mistake this whole project is built to avoid."""
    timing = _timing([("1", "2017-01", None, np.nan)])
    assert known_at_horizon(timing, None).empty
    assert known_at_horizon(timing, 12).empty


def test_coverage_is_reported_against_everything_scored():
    predictions = pd.DataFrame({
        "loan_id": ["1", "2", "3", "4"],
        "issue_month": ["2017-01"] * 4,
        "p_default": [0.9, 0.1, 0.8, 0.2],
    })
    timing = _timing([
        ("1", "2017-01", 1, 6.0),
        ("2", "2017-01", 0, 6.0),
        ("3", "2017-01", 1, 30.0),
        ("4", "2017-01", None, np.nan),
    ])
    at_12 = performance_by_month(predictions, timing, 12)
    assert at_12.loc[0, "scored"] == 4
    assert at_12.loc[0, "evaluable"] == 2
    assert at_12.loc[0, "coverage"] == 0.5   # never quoted without this


def test_fixed_horizon_removes_the_bias_that_the_naive_view_shows():
    """The point of the module, constructed deliberately.

    Two vintages with IDENTICAL true behaviour: 50% default, defaults resolving in
    6 months and repayments in 30. The older vintage has had 36 months of observation;
    the younger only 12. The naive view sees all of the older one but only the fast
    defaults of the younger, so it reports a default rate twice as high for a vintage
    that is not actually worse. The fixed horizon judges both on 12 months and agrees.
    """
    rows, predictions = [], []
    for month, observed_months in (("2016-01", 36), ("2017-01", 12)):
        for i in range(100):
            defaulted = i % 2 == 0
            resolution = 6.0 if defaulted else 30.0
            # a loan only appears resolved if its resolution fits the observation window
            visible = resolution <= observed_months
            rows.append((
                f"{month}-{i}", month,
                (1 if defaulted else 0) if visible else None,
                resolution if visible else np.nan,
            ))
            predictions.append((f"{month}-{i}", month, 0.9 if defaulted else 0.1))

    timing = _timing(rows)
    preds = pd.DataFrame(predictions, columns=["loan_id", "issue_month", "p_default"])

    naive = performance_by_month(preds, timing, None).set_index("issue_month")
    assert naive.loc["2016-01", "default_rate"] == pytest.approx(0.5)
    assert naive.loc["2017-01", "default_rate"] == pytest.approx(1.0)   # ← the illusion

    fixed = performance_by_month(preds, timing, 12).set_index("issue_month")
    assert fixed.loc["2016-01", "default_rate"] == pytest.approx(1.0)
    assert fixed.loc["2017-01", "default_rate"] == pytest.approx(1.0)   # ← comparable
    assert fixed.loc["2016-01", "coverage"] == fixed.loc["2017-01", "coverage"]


def test_compare_views_labels_each_row_with_its_horizon():
    predictions = pd.DataFrame({
        "loan_id": ["1", "2"], "issue_month": ["2017-01"] * 2, "p_default": [0.9, 0.1]
    })
    timing = _timing([("1", "2017-01", 1, 6.0), ("2", "2017-01", 0, 30.0)])
    both = compare_views(predictions, timing, horizon_months=12)
    assert set(both["horizon_months"]) == {"as-observed", 12}


def test_calibration_gap_sign_convention():
    """Negative gap = the model predicts less risk than materialised, which is the
    direction #39 measured on this data."""
    predictions = pd.DataFrame({
        "loan_id": ["1", "2"], "issue_month": ["2017-01"] * 2, "p_default": [0.1, 0.1]
    })
    timing = _timing([("1", "2017-01", 1, 6.0), ("2", "2017-01", 0, 6.0)])
    table = performance_by_month(predictions, timing, 12)
    assert table.loc[0, "calibration_gap"] == pytest.approx(0.1 - 0.5)


@pytest.mark.realdata
def test_real_timing_shows_defaults_resolving_faster():
    """The mechanism behind the bias, on the actual data: if defaults resolved at the
    same speed as repayments, an early look would not be enriched and none of this
    machinery would be needed."""
    from credit_default.label_lag import load_outcome_timing

    timing = load_outcome_timing()
    resolved = timing[timing["label"].notna()]
    default_median = resolved.loc[resolved["label"] == 1, "months_to_resolution"].median()
    repaid_median = resolved.loc[resolved["label"] == 0, "months_to_resolution"].median()
    assert default_median < repaid_median
