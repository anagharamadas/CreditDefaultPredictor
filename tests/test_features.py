"""Pipeline: ledger partition, determinism, train-window gate, encoders, safety."""

import numpy as np
import pandas as pd
import pytest

from credit_default.features import (
    CATEGORICAL_FEATURES,
    DATE_DERIVED,
    EXCLUDED_FROM_MATRIX,
    FREQUENCY_ENCODED,
    NUMERIC_FEATURES,
    FrequencyEncoder,
    build_pipeline,
    derive_features,
)
from credit_default.features.pipeline import feature_names
from credit_default.ledger import feature_columns


def _sample(n: int = 8, issue: str = "2015-06-01") -> pd.DataFrame:
    """Tiny synthetic frame covering every pipeline input column."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame({c: rng.uniform(0, 10, n) for c in NUMERIC_FEATURES})
    df["issue_d"] = pd.Timestamp(issue)
    df["earliest_cr_line"] = pd.Timestamp("2005-03-01")
    df["zip_code"] = pd.Series(["190xx", "331xx"] * (n // 2 + 1))[:n].astype("string")
    cat_values = {
        "purpose": "credit_card", "application_type": "Individual",
        "emp_length": "10+ years", "home_ownership": "RENT",
        "verification_status": "Verified", "disbursement_method": "Cash",
        "addr_state": "CA",
    }
    for col in CATEGORICAL_FEATURES:
        df[col] = pd.Categorical([cat_values[col]] * n)
    df.loc[0, NUMERIC_FEATURES[0]] = np.nan  # imputation has work to do
    return df


def test_groups_partition_the_ledger_features_exactly():
    covered = (
        set(NUMERIC_FEATURES)
        | set(CATEGORICAL_FEATURES)
        | set(DATE_DERIVED)
        | set(FREQUENCY_ENCODED)
        | set(EXCLUDED_FROM_MATRIX)
    )
    assert covered == set(feature_columns())  # nothing forgotten, nothing extra
    assert not set(NUMERIC_FEATURES) & set(CATEGORICAL_FEATURES)
    assert all(reason.strip() for reason in EXCLUDED_FROM_MATRIX.values())


def test_derive_features_arithmetic_and_dti_clip():
    df = _sample(3)
    df.loc[0, "dti"] = 999.0   # sentinel high
    df.loc[1, "dti"] = -1.0    # sentinel low
    out = derive_features(df)
    assert out["credit_history_months"].iloc[0] == 123.0  # 2005-03 -> 2015-06
    assert out["dti"].iloc[0] == 100.0 and out["dti"].iloc[1] == 0.0


def test_fit_on_training_window_only_is_enforced():
    with pytest.raises(ValueError, match="outside the training window"):
        build_pipeline().fit(_sample(issue="2016-03-01"))  # validation vintage
    with pytest.raises(ValueError, match="outside the training window"):
        build_pipeline().fit(_sample(issue="2012-11-01"))  # before the window


def test_transform_accepts_any_vintage_after_a_lawful_fit():
    pipe = build_pipeline().fit(_sample())
    x = pipe.transform(_sample(2, issue="2018-07-01"))  # replay vintage: fine
    assert x.shape[0] == 2


def test_frequency_encoder_learns_train_shares_and_zeroes_unknowns():
    enc = FrequencyEncoder().fit(pd.DataFrame({"zip_code": ["1", "1", "1", "2"]}))
    out = enc.transform(pd.DataFrame({"zip_code": ["1", "2", "9", None]}))
    assert out["zip_code_freq"].tolist() == [0.75, 0.25, 0.0, 0.0]


def test_missing_indicators_present_and_no_nans_leave_the_pipeline():
    pipe = build_pipeline()
    x = pipe.fit_transform(_sample())
    assert not np.isnan(x).any()
    assert any("missingindicator" in n for n in feature_names(pipe))


def test_fit_transform_is_deterministic():
    df = _sample()
    a = build_pipeline().fit_transform(df)
    b = build_pipeline().fit_transform(df)
    assert np.array_equal(a, b)
    assert feature_names(build_pipeline().fit(df)) == feature_names(build_pipeline().fit(df))


def test_unknown_category_at_transform_time_does_not_crash():
    df = _sample()
    pipe = build_pipeline().fit(df)
    serve = _sample(2)
    serve["purpose"] = pd.Categorical(["small_business", "small_business"])  # unseen in fit
    x = pipe.transform(serve)
    assert x.shape[0] == 2  # encoded as all-zeros for purpose, not an exception


def test_banned_or_metadata_columns_never_reach_the_matrix():
    df = _sample()
    df["total_pymnt"] = 999.0  # smuggled leakage column
    df["id"] = "42"
    pipe = build_pipeline().fit(df)
    assert not any("total_pymnt" in n or n.endswith("__id") for n in feature_names(pipe))
