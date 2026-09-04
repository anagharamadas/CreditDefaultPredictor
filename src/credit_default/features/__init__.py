"""Feature pipeline — the single transform path shared by training and serving."""

from credit_default.features.pipeline import (  # noqa: F401
    CATEGORICAL_FEATURES,
    DATE_DERIVED,
    EXCLUDED_FROM_MATRIX,
    FREQUENCY_ENCODED,
    NUMERIC_FEATURES,
    FrequencyEncoder,
    TrainWindowGate,
    build_pipeline,
    derive_features,
)
