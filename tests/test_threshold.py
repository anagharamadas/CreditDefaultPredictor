"""Threshold derivation is arithmetic from ADR-0003 — pinned, not tunable."""

import pandas as pd
import pytest

from credit_default.threshold import (
    COST_FN,
    COST_FP,
    derive_threshold,
    expected_cost_per_loan,
    sensitivity_table,
)


def test_baseline_threshold_is_one_sixth():
    assert derive_threshold() == pytest.approx(1 / 6)
    assert COST_FN == 5.0 and COST_FP == 1.0  # ADR-0003; changing this needs a new ADR


def test_threshold_moves_with_the_ratio():
    # costlier FN -> lower threshold (decline more readily)
    assert derive_threshold(8, 1) < derive_threshold(5, 1) < derive_threshold(3, 1)
    assert derive_threshold(8, 1) == pytest.approx(1 / 9)
    assert derive_threshold(3, 1) == pytest.approx(1 / 4)


def test_invalid_costs_raise():
    with pytest.raises(ValueError):
        derive_threshold(0, 1)
    with pytest.raises(ValueError):
        derive_threshold(5, -1)


def test_sensitivity_table_covers_adr_band():
    t = sensitivity_table()
    assert t["fn_to_fp"].tolist() == [3.0, 4.0, 5.0, 6.0, 8.0]
    assert t.loc[t["is_baseline"], "threshold"].iloc[0] == pytest.approx(0.1667, abs=1e-4)


def test_expected_cost_arithmetic():
    y = pd.Series([1, 1, 0, 0])
    p = pd.Series([0.05, 0.90, 0.90, 0.05])
    # θ=1/6: loan0 funded+defaults (FN, cost 5); loan1 declined+defaults (correct);
    # loan2 declined+would repay (FP, cost 1); loan3 funded+repays (correct).
    assert expected_cost_per_loan(y, p) == pytest.approx((5.0 + 1.0) / 4)


def test_perfect_predictions_cost_nothing():
    y = pd.Series([1, 0, 1, 0])
    p = pd.Series([0.99, 0.01, 0.95, 0.02])
    assert expected_cost_per_loan(y, p) == 0.0
