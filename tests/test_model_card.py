"""The model card must carry its load-bearing facts — cheap consistency pins."""

from pathlib import Path

from credit_default.registry import ADR_0004_RUN_ID, MODEL_NAME

CARD = Path(__file__).resolve().parents[1] / "docs" / "MODEL_CARD.md"


def test_card_names_the_registered_model_and_source_run():
    text = CARD.read_text()
    assert MODEL_NAME in text
    assert ADR_0004_RUN_ID in text  # the card describes a specific, reproducible run


def test_card_carries_the_non_negotiable_sections():
    text = " ".join(CARD.read_text().split())  # wrap-immune: prose reflows
    for required in (
        "Prohibited uses",
        "coverage",                    # metrics never quoted without it
        "[ASSUMED]",                   # the cost ratio's status is visible
        "not legal advice",            # the R7 framing survives into the card
        "60-month",                    # the v1 scope exclusion is stated
        "human-in-the-loop",
    ):
        assert required in text, f"model card is missing: {required!r}"
