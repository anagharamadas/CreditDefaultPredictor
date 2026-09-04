"""The catalogue cannot drift from the code: committed doc == renderer output."""

from pathlib import Path

from credit_default.features.catalogue import CATEGORY_SETS, render_markdown
from credit_default.features.pipeline import CATEGORICAL_FEATURES, NUMERIC_FEATURES

DOC = Path(__file__).resolve().parents[1] / "docs" / "FEATURE_CATALOGUE.md"


def test_committed_catalogue_matches_the_code():
    assert DOC.read_text() == render_markdown(), (
        "docs/FEATURE_CATALOGUE.md is stale — rerun scripts/render_feature_catalogue.py "
        "and commit the result together with the code change that moved it"
    )


def test_every_categorical_feature_has_a_category_set():
    assert set(CATEGORY_SETS) == set(CATEGORICAL_FEATURES)


def test_catalogue_mentions_every_matrix_feature():
    text = render_markdown()
    for col in NUMERIC_FEATURES + CATEGORICAL_FEATURES + ["credit_history_months"]:
        assert f"`{col}`" in text, col
