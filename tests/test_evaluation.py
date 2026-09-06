"""Evaluation harness: the holdout door stays guarded at this layer too."""

import pytest

from credit_default.evaluation import split_features
from credit_default.splits import HOLDOUT


def test_holdout_split_requires_the_spelled_out_acknowledgment():
    # Checked BEFORE any data is touched — no parquet needed for the refusal.
    with pytest.raises(PermissionError, match="final P6 report"):
        split_features(HOLDOUT)
