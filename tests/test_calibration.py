"""Calibration arithmetic: reliability bins, ECE, and the window discipline."""

import numpy as np
import pandas as pd
import pytest

from credit_default.calibration import (
    CALIBRATION_SPLIT,
    CalibratedModel,
    expected_calibration_error,
    reliability_table,
)
from credit_default.splits import TRAIN_END, TRAIN_START


def test_reliability_table_on_perfectly_calibrated_scores():
    rng = np.random.default_rng(7)
    p = rng.uniform(0, 1, 20_000)
    y = (rng.uniform(0, 1, 20_000) < p).astype(float)  # outcomes drawn AT the stated prob
    table = reliability_table(y, p, n_bins=10)
    assert len(table) == 10
    assert table["loans"].sum() == 20_000
    assert table["gap"].abs().max() < 0.03  # every bin's predicted ≈ observed
    assert expected_calibration_error(y, p) < 0.01


def test_reliability_table_exposes_systematic_overconfidence():
    y = np.array([0, 0, 0, 0, 0, 0, 0, 0, 1, 1], dtype=float)  # 20% true rate
    p = np.full(10, 0.60)  # model claims 60% everywhere
    table = reliability_table(y, p, n_bins=2)
    assert (table["gap"] > 0).all()  # overconfident in every bin
    # 2 bins split the ties 5/5: gaps 0.6 and 0.2; count-weighted ECE = 0.40
    assert expected_calibration_error(y, p, n_bins=2) == pytest.approx(0.40)


def test_calibration_slice_sits_inside_the_train_window():
    assert TRAIN_START < CALIBRATION_SPLIT < TRAIN_END  # both components learn pre-2016 only


def test_calibrated_model_applies_the_isotonic_map():
    class FakeBase:
        def predict_proba(self, x):
            raw = np.linspace(0.1, 0.9, len(x))
            return np.column_stack([1 - raw, raw])

    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit([0.1, 0.5, 0.9], [0.0, 0.2, 0.6])  # squash overconfident scores
    model = CalibratedModel(FakeBase(), iso)
    out = model.predict_proba(pd.DataFrame(index=range(3)))
    assert out.shape == (3, 2)
    assert np.allclose(out.sum(axis=1), 1.0)
    assert out[-1, 1] <= 0.6  # the map bounded the top score
