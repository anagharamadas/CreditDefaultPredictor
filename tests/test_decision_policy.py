"""Decision policy: derived thresholds only, arithmetic pinned on a toy book."""

import numpy as np
import pytest

from credit_default.decision_policy import drift_shift_row, policy_row, policy_table


def _toy_book():
    # 10 loans: scores line up so θ=1/6 declines exactly the last four.
    y = np.array([0, 0, 0, 0, 0, 0, 1, 0, 1, 1], dtype=float)
    p = np.array([0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.14, 0.20, 0.30, 0.40])
    return y, p


def test_policy_row_arithmetic_at_baseline():
    y, p = _toy_book()
    row = policy_row(y, p, 5.0)
    assert row["theta"] == pytest.approx(0.1667, abs=1e-4)
    assert row["decline_rate"] == 0.3                      # 3 of 10 at/above θ
    assert row["funded_default_rate"] == pytest.approx(1 / 7)   # one FN among 7 funded
    assert row["declined_default_rate"] == pytest.approx(2 / 3)
    # cost: 1 FN * 5 + 1 FP * 1 over 10 loans
    assert row["expected_cost_per_loan"] == pytest.approx(0.6)
    assert row["cost_fund_everyone"] == pytest.approx(5 * 0.3)
    assert row["saving_vs_fund_all"] == pytest.approx(1 - 0.6 / 1.5)


def test_policy_table_covers_the_adr_band_and_thetas_are_derived():
    y, p = _toy_book()
    table = policy_table(y, p)
    assert table["fn_to_fp"].tolist() == [3.0, 4.0, 5.0, 6.0, 8.0]
    assert table["theta"].tolist() == [0.25, 0.2, 0.1667, 0.1429, 0.1111]
    # decline rate must be monotone in the ratio: costlier FNs -> decline more
    assert table["decline_rate"].is_monotonic_increasing


def test_drift_shift_row_moves_the_operating_point_toward_more_declines():
    y, p = _toy_book()
    base = policy_row(y, p, 5.0)
    shifted = drift_shift_row(y, p, 5.0)
    assert shifted["decline_rate"] >= base["decline_rate"]
    assert "under-prediction" in shifted["note"]


def test_no_tuning_metric_exists_in_the_module():
    from pathlib import Path

    from credit_default import decision_policy as module

    source = Path(module.__file__).read_text().lower()
    for forbidden in ("f1", "accuracy", "youden", "fbeta"):
        assert forbidden not in source
