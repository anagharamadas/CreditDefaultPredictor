"""The feature pipeline skeleton (ticket #27): raw frame -> model matrix.

Design rules this module owes the charter:

- **One code path.** This pipeline object is fit at training time, serialised with
  the model (P7), and executed unchanged inside the serving API (P8). There is no
  second implementation to drift (RISK_REGISTER R8); the parity fixture test (#28)
  holds it to that.
- **Ledger-derived membership.** Column groups below are computed from
  `ledger.feature_columns()` and checked by tests to *partition* it exactly:
  every FEATURE column is either transformed here or named in EXCLUDED_FROM_MATRIX
  with a reason. A banned column cannot appear; an approved column cannot be
  silently forgotten.
- **Learned parameters fit on train only.** fit() is called exactly once, on the
  training split (enforced in P5's flow; asserted by the no-refit convention here).
- **Determinism.** Column groups are sorted; encoders produce a fixed feature order;
  there is no randomness anywhere in the transform.

Transform choices in the SKELETON (revisited and finalised in ticket #30):
numeric -> median impute; categorical -> constant-impute + one-hot (unknown
categories at serve time encode as all-zeros rather than crashing); dates ->
credit_history_months. Scaling is deliberately deferred to #30 where the P5 model
menu decides it.
"""

from __future__ import annotations

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

from credit_default.ingest import CATEGORICAL_COLS, DATE_COLS, STRING_COLS
from credit_default.ledger import feature_columns

# --- membership, derived from the ledger -------------------------------------------

#: FEATURE columns deliberately not entering the v1 matrix. The ledger still says
#: FEATURE (they are legitimate); exclusion here is a pipeline scope decision with a
#: stated reason, revisited in #30.
EXCLUDED_FROM_MATRIX: dict[str, str] = {
    "term": "constant ' 36 months' in v1 scope (Charter §3.3) — zero variance by construction",
    "zip_code": "956-value masked geography; needs frequency/target encoding designed in #30 — addr_state carries geography until then",
}

#: date columns consumed by derive_date_features, not encoded directly
DATE_DERIVED = ["earliest_cr_line"]

CATEGORICAL_FEATURES = sorted(
    c for c in feature_columns()
    if c in CATEGORICAL_COLS and c not in EXCLUDED_FROM_MATRIX
)
NUMERIC_FEATURES = sorted(
    c for c in feature_columns()
    if c not in CATEGORICAL_COLS
    and c not in STRING_COLS
    and c not in DATE_COLS
    and c not in EXCLUDED_FROM_MATRIX
)

#: engineered columns added by derive_date_features
ENGINEERED = ["credit_history_months"]


def derive_date_features(df: pd.DataFrame) -> pd.DataFrame:
    """Turn date columns into application-time numerics; drop what the model can't eat.

    credit_history_months: age of the credit file at application — knowable at the
    decision because both dates are on the application. issue_d itself never becomes
    a feature (METADATA: calendar time wouldn't transfer to serving).
    """
    out = df.copy()
    months = (
        (out["issue_d"].dt.year - out["earliest_cr_line"].dt.year) * 12
        + (out["issue_d"].dt.month - out["earliest_cr_line"].dt.month)
    )
    out["credit_history_months"] = months.astype("float64")
    return out


def build_pipeline() -> Pipeline:
    """The one transform path. fit() on the training split only; transform() everywhere."""
    encode = ColumnTransformer(
        transformers=[
            (
                "num",
                SimpleImputer(strategy="median"),
                NUMERIC_FEATURES + ENGINEERED,
            ),
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",  # anything not named above never reaches the matrix
        verbose_feature_names_out=True,
    )
    return Pipeline(
        [
            ("derive", FunctionTransformer(derive_date_features, feature_names_out=None)),
            ("encode", encode),
        ]
    )


def feature_names(fitted: Pipeline) -> list[str]:
    """Deterministic output column names of a fitted pipeline."""
    return list(fitted.named_steps["encode"].get_feature_names_out())


if __name__ == "__main__":
    from credit_default.ingest import INTERIM_ACCEPTED
    from credit_default.splits import TRAIN, assign_split, split_frame

    df = assign_split(pd.read_parquet(INTERIM_ACCEPTED))
    train = split_frame(df, TRAIN).head(50_000)  # smoke sample
    pipe = build_pipeline()
    x = pipe.fit_transform(train)
    names = feature_names(pipe)
    print(f"matrix: {x.shape[0]:,} rows x {x.shape[1]} features")
    print(f"numeric {len(NUMERIC_FEATURES)} + engineered {len(ENGINEERED)} "
          f"+ one-hot from {len(CATEGORICAL_FEATURES)} categoricals")
    print("first/last feature names:", names[0], "…", names[-1])
