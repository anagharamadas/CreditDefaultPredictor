"""Feature pipeline — the single transform path shared by training and serving."""

from credit_default.features.pipeline import (  # noqa: F401
    CATEGORICAL_FEATURES,
    DATE_DERIVED,
    EXCLUDED_FROM_MATRIX,
    NUMERIC_FEATURES,
    build_pipeline,
    derive_date_features,
)
