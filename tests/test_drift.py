"""Drift statistics, checked against cases whose answers are known independently."""

import numpy as np
import pandas as pd
import pytest

from credit_default.drift import (
    calibrate_thresholds,
    drift_table,
    ks_statistic,
    psi,
    psi_categorical,
    quantile_edges,
)


def test_identical_distributions_have_zero_drift():
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(size=20_000))
    assert psi(x, x) == pytest.approx(0.0, abs=1e-9)
    assert ks_statistic(x, x) == pytest.approx(0.0, abs=1e-9)


def test_psi_matches_a_hand_computed_case():
    """Two bins, reference 50/50, current 90/10. By hand:
    (0.9-0.5)*ln(0.9/0.5) + (0.1-0.5)*ln(0.1/0.5) = 0.4*0.5878 + (-0.4)*(-1.6094)."""
    reference = pd.Series([0.0] * 50 + [1.0] * 50)
    current = pd.Series([0.0] * 90 + [1.0] * 10)
    expected = 0.4 * np.log(0.9 / 0.5) + (-0.4) * np.log(0.1 / 0.5)
    assert psi(reference, current, bins=2) == pytest.approx(expected, rel=1e-6)


def test_psi_grows_with_the_size_of_the_shift():
    rng = np.random.default_rng(1)
    reference = pd.Series(rng.normal(size=20_000))
    small = pd.Series(rng.normal(loc=0.2, size=20_000))
    large = pd.Series(rng.normal(loc=1.0, size=20_000))
    assert psi(reference, small) < psi(reference, large)
    assert psi(reference, large) > 0.25  # a full standard deviation is a large move


def test_ks_equals_the_known_cdf_gap():
    """Uniform[0,1] vs Uniform[0.5,1.5] have a maximum CDF gap of 0.5."""
    rng = np.random.default_rng(2)
    reference = pd.Series(rng.uniform(0, 1, 200_000))
    current = pd.Series(rng.uniform(0.5, 1.5, 200_000))
    assert ks_statistic(reference, current) == pytest.approx(0.5, abs=0.01)


def test_ks_is_bounded_but_psi_is_not():
    reference = pd.Series(np.zeros(1000))
    current = pd.Series(np.ones(1000))
    assert ks_statistic(reference, current) == pytest.approx(1.0)
    assert psi(reference, current) > 1.0  # unbounded: this is why both are reported


def test_constant_reference_does_not_silently_report_no_drift():
    """A constant feature that moves entirely is total drift. Quantile binning would
    put everything in one bin and report 0; the low-cardinality path catches it."""
    moved = psi(pd.Series([5.0] * 1000), pd.Series([9.0] * 1000))
    assert np.isfinite(moved) and moved > 1.0
    assert psi(pd.Series([5.0] * 1000), pd.Series([5.0] * 1000)) == pytest.approx(0.0, abs=1e-9)


def test_low_cardinality_numerics_use_value_bins():
    """Bureau counts like pub_rec have a handful of distinct values; per-value bins
    are both well-defined and more faithful than collapsed quantile edges."""
    reference = pd.Series([0] * 700 + [1] * 200 + [2] * 100)
    unchanged = psi(reference, reference)
    shifted = psi(reference, pd.Series([0] * 400 + [1] * 300 + [2] * 300))
    assert unchanged == pytest.approx(0.0, abs=1e-9)
    assert shifted > 0.1


def test_categorical_psi_detects_a_new_category():
    reference = pd.Series(["a"] * 500 + ["b"] * 500)
    current = pd.Series(["a"] * 500 + ["b"] * 400 + ["c"] * 100)
    assert psi_categorical(reference, current) > 0.1
    assert psi_categorical(reference, reference) == pytest.approx(0.0, abs=1e-9)


def test_zero_bins_do_not_make_psi_infinite():
    """A category present in one period and absent in the other must contribute a
    large finite number, not inf — an alarm has to be comparable to a threshold."""
    reference = pd.Series(["a"] * 900 + ["rare"] * 100)
    current = pd.Series(["a"] * 1000)
    value = psi_categorical(reference, current)
    assert np.isfinite(value) and value > 0.5


def test_quantile_edges_handle_a_constant_feature():
    edges = quantile_edges(pd.Series([5.0] * 100))
    assert len(edges) == 2 and np.isinf(edges).all()
    assert psi(pd.Series([5.0] * 100), pd.Series([5.0] * 100)) == pytest.approx(0.0)


def test_empty_input_returns_nan_rather_than_raising():
    assert np.isnan(psi(pd.Series([], dtype=float), pd.Series([1.0])))
    assert np.isnan(ks_statistic(pd.Series([1.0]), pd.Series([], dtype=float)))


def test_drift_table_shape_and_ordering():
    rng = np.random.default_rng(3)
    reference = pd.DataFrame(
        {"num": rng.normal(size=5000), "cat": rng.choice(["x", "y"], 5000)}
    )
    current = pd.DataFrame(
        {"num": rng.normal(loc=1.0, size=5000), "cat": rng.choice(["x", "y"], 5000)}
    )
    table = drift_table(reference, current, ["num"], ["cat"])
    assert set(table["feature"]) == {"num", "cat"}
    assert table["psi"].is_monotonic_decreasing        # worst drift first
    assert np.isnan(table.loc[table["feature"] == "cat", "ks"]).all()


def _quiet_setup(seed=4, noisy=False):
    rng = np.random.default_rng(seed)
    reference = pd.DataFrame({
        "steady": rng.normal(size=20_000),
        # a feature whose value is usually missing: its non-null sample is small, so
        # it jumps around far more from month to month even when nothing is wrong
        "jumpy": np.where(rng.uniform(size=20_000) < 0.85, np.nan, rng.normal(size=20_000)),
        "cat": rng.choice(["x", "y"], 20_000),
    })
    quiet = {}
    for i in range(4):
        n = 3000
        quiet[f"m{i}"] = pd.DataFrame({
            "steady": rng.normal(size=n),
            "jumpy": np.where(rng.uniform(size=n) < 0.85, np.nan, rng.normal(size=n)),
            "cat": rng.choice(["x", "y"], n),
        })
    return reference, quiet


def test_thresholds_are_derived_from_the_quiet_period():
    """The alert must sit above anything the stable period produced — that is the
    justification EVAL_PROTOCOL demands instead of a borrowed 0.1/0.25 convention."""
    reference, quiet = _quiet_setup()
    thresholds = calibrate_thresholds(reference, quiet, ["steady", "jumpy"], ["cat"], safety_factor=2.0)
    assert set(thresholds["feature"]) == {"steady", "jumpy", "cat"}
    for _, row in thresholds.iterrows():
        assert row["psi_alert"] == pytest.approx(row["quiet_max_psi"] * 2, abs=1e-4)
    assert (thresholds["psi_alert"] > 0).all()   # sampling noise alone is non-zero
    assert "larger than that feature ever moved" in thresholds.attrs["basis"]


def test_each_feature_gets_its_own_noise_floor():
    """A single global threshold would be set by the noisiest feature and would then
    be far too deaf to notice a real move in a quiet one."""
    reference, quiet = _quiet_setup()
    thresholds = calibrate_thresholds(
        reference, quiet, ["steady", "jumpy"], ["cat"]
    ).set_index("feature")
    assert thresholds.loc["jumpy", "psi_alert"] > thresholds.loc["steady", "psi_alert"] * 3


def test_alarms_compare_each_feature_to_its_own_threshold():
    from credit_default.drift import evaluate_against_thresholds

    thresholds = pd.DataFrame({
        "feature": ["steady", "jumpy"],
        "psi_alert": [0.02, 0.40],
        "ks_alert": [0.05, 0.30],
        "quiet_max_psi": [0.01, 0.20],
    })
    measured = pd.DataFrame({
        "feature": ["steady", "jumpy"],
        "kind": ["numeric", "numeric"],
        "psi": [0.10, 0.10],      # identical raw drift...
        "ks": [0.02, 0.02],
    })
    result = evaluate_against_thresholds(measured, thresholds).set_index("feature")
    assert result.loc["steady", "psi_alarm"]        # ...alarms for the quiet feature
    assert not result.loc["jumpy", "psi_alarm"]     # ...but is normal for the jumpy one
    assert result.loc["steady", "psi_ratio"] > result.loc["jumpy", "psi_ratio"]


def test_calibration_requires_a_quiet_period():
    with pytest.raises(ValueError, match="at least one quiet-period"):
        calibrate_thresholds(pd.DataFrame({"a": [1.0]}), {}, ["a"], [])
