"""The feature pipeline (tickets #27 skeleton, #30 completed transforms).

Design rules this module owes the charter:

- **One code path.** This pipeline object is fit at training time, serialised with
  the model (P7), and executed unchanged inside the serving API (P8). There is no
  second implementation to drift (RISK_REGISTER R8); the parity fixture test (#28)
  holds it to that.
- **Fit on training vintages only — enforced, not promised.** The first pipeline
  step is a gate whose fit() RAISES if any row's issue_d falls outside the
  configured training window. Transform passes anything (validation, holdout,
  replay, live requests); learning outside the window is structurally impossible.
- **Ledger-derived membership.** Column groups are computed from
  `ledger.feature_columns()` and tests assert they PARTITION it exactly: every
  FEATURE column is transformed here or named in EXCLUDED_FROM_MATRIX with a reason.
- **Determinism, no hidden state.** Groups are sorted; encoders emit a fixed
  feature order; nothing here draws randomness (nothing to seed — recorded fact,
  tested by double-build equality).

Transform decisions FINALISED in #30 (were deferred from the skeleton):

- Numeric: median impute + missing-INDICATOR columns (a meaningful null like
  "never delinquent" stays visible to the model instead of masquerading as the
  median) -> standardise. All statistics learned at fit, i.e. on the train window.
- dti: clipped to [0, 100] in the derive step — measured raw range is -1..999 with
  sentinel-like extremes (docs/SCHEMA.md); beyond 100 carries no credible ratio
  information. Recorded in the catalogue.
- zip_code: frequency-encoded (share of training loans in that 3-digit zip) by a
  custom transformer. One numeric column instead of 956 one-hots; unknown zips at
  serve time encode as 0. Target encoding rejected: leak-prone under this label.
- Scaling: StandardScaler on the numeric branch (logistic regression in the P5
  menu needs it; trees are indifferent). One-hot columns are left unscaled.
"""

from __future__ import annotations

import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from credit_default.ingest import CATEGORICAL_COLS, DATE_COLS, STRING_COLS
from credit_default.ledger import feature_columns
from credit_default.splits import TRAIN_END, TRAIN_START

# --- membership, derived from the ledger -------------------------------------------

#: FEATURE columns deliberately not entering the v1 matrix, with reasons.
EXCLUDED_FROM_MATRIX: dict[str, str] = {
    "term": "constant ' 36 months' in v1 scope (Charter §3.3) — zero variance by construction",
}

#: date columns consumed by derive_features, not encoded directly
DATE_DERIVED = ["earliest_cr_line"]

#: geography encoded by frequency, not one-hot (see module docstring)
FREQUENCY_ENCODED = ["zip_code"]

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

#: engineered columns added by derive_features
ENGINEERED = ["credit_history_months"]

DTI_CLIP = (0.0, 100.0)


class TrainWindowGate(BaseEstimator, TransformerMixin):
    """Structural enforcement of 'learned parameters fit inside training vintages'.

    fit() raises if any row was issued outside [train_start, train_end]; transform()
    passes every frame untouched. Downstream imputers/scalers/encoders can therefore
    only ever learn from the training window — by construction, not convention.
    """

    def __init__(self, train_start=TRAIN_START, train_end=TRAIN_END):
        self.train_start = train_start
        self.train_end = train_end

    def fit(self, X: pd.DataFrame, y=None):
        issued = X["issue_d"]
        bad = (issued < self.train_start) | (issued > self.train_end + pd.offsets.MonthEnd(0))
        if bool(bad.any()):
            months = sorted(issued[bad].dt.strftime("%Y-%m").unique())
            raise ValueError(
                f"fit() received {int(bad.sum())} rows issued outside the training "
                f"window {self.train_start:%Y-%m}..{self.train_end:%Y-%m} "
                f"(offending months: {months[:6]}{'…' if len(months) > 6 else ''}). "
                "Learned parameters must come from training vintages only "
                "(Charter §4.2); pass the train split, or transform() instead."
            )
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        return X

    def get_feature_names_out(self, input_features=None):
        return input_features


class FrequencyEncoder(BaseEstimator, TransformerMixin):
    """Encode a single categorical column as its training-split frequency.

    fit() learns value -> share-of-training-rows; transform() maps, with unseen
    values (and nulls) becoming 0.0. Deterministic, one output column.
    """

    def fit(self, X: pd.DataFrame, y=None):
        col = X.iloc[:, 0]
        self.freq_ = col.value_counts(normalize=True, dropna=True).to_dict()
        self.column_name_ = f"{X.columns[0]}_freq"
        return self

    def transform(self, X: pd.DataFrame):
        col = X.iloc[:, 0]
        return col.map(self.freq_).fillna(0.0).astype("float64").to_frame(self.column_name_)

    def get_feature_names_out(self, input_features=None):
        return [self.column_name_]


def derive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Application-time derivations + recorded raw-value treatments.

    - credit_history_months: age of the credit file at application (both dates are
      on the application). issue_d itself never becomes a feature (METADATA:
      calendar time would not transfer to serving).
    - dti clipped to DTI_CLIP: sentinel-like extremes carry no ratio information.
    """
    out = df.copy()
    months = (
        (out["issue_d"].dt.year - out["earliest_cr_line"].dt.year) * 12
        + (out["issue_d"].dt.month - out["earliest_cr_line"].dt.month)
    )
    out["credit_history_months"] = months.astype("float64")
    out["dti"] = out["dti"].clip(*DTI_CLIP)
    return out


def build_pipeline(*, enforce_train_window: bool = True) -> Pipeline:
    """The one transform path. fit() on the training split only; transform() everywhere.

    enforce_train_window=False exists for unit tests of the transforms themselves;
    production callers never pass it.
    """
    encode = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scale", StandardScaler()),
                    ]
                ),
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
            ("zip", FrequencyEncoder(), FREQUENCY_ENCODED),
        ],
        remainder="drop",  # anything not named above never reaches the matrix
        verbose_feature_names_out=True,
    )
    steps = [
        ("derive", FunctionTransformer(derive_features, feature_names_out=None)),
        ("encode", encode),
    ]
    if enforce_train_window:
        steps.insert(0, ("gate", TrainWindowGate()))
    return Pipeline(steps)


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
    indicators = sum(1 for n in names if "missingindicator" in n)
    print(f"matrix: {x.shape[0]:,} rows x {x.shape[1]} features")
    print(f"numeric {len(NUMERIC_FEATURES)} + engineered {len(ENGINEERED)} "
          f"+ {indicators} missing-indicators + one-hot from "
          f"{len(CATEGORICAL_FEATURES)} categoricals + zip frequency")
    print("first/last feature names:", names[0], "…", names[-1])
