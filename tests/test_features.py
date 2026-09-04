"""Pipeline skeleton: ledger partition, determinism, unknown-category safety."""

import numpy as np
import pandas as pd

from credit_default.features import (
    CATEGORICAL_FEATURES,
    DATE_DERIVED,
    EXCLUDED_FROM_MATRIX,
    NUMERIC_FEATURES,
    build_pipeline,
    derive_date_features,
)
from credit_default.features.pipeline import feature_names
from credit_default.ledger import feature_columns


def _sample(n: int = 8) -> pd.DataFrame:
    """Tiny synthetic frame covering every pipeline input column."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame({c: rng.uniform(0, 10, n) for c in NUMERIC_FEATURES})
    df["issue_d"] = pd.Timestamp("2015-06-01")
    df["earliest_cr_line"] = pd.Timestamp("2005-03-01")
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
        | set(EXCLUDED_FROM_MATRIX)
    )
    assert covered == set(feature_columns())  # nothing forgotten, nothing extra
    assert not set(NUMERIC_FEATURES) & set(CATEGORICAL_FEATURES)
    assert all(reason.strip() for reason in EXCLUDED_FROM_MATRIX.values())


def test_derive_date_features_arithmetic():
    out = derive_date_features(_sample(2))
    assert out["credit_history_months"].iloc[0] == 123.0  # 2005-03 -> 2015-06


def test_fit_transform_is_deterministic():
    df = _sample()
    a = build_pipeline().fit_transform(df)
    b = build_pipeline().fit_transform(df)
    assert np.array_equal(a, b)
    assert feature_names(build_pipeline().fit(df)) == feature_names(build_pipeline().fit(df))


def test_imputer_fills_and_no_nans_leave_the_pipeline():
    x = build_pipeline().fit_transform(_sample())
    assert not np.isnan(x).any()


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
