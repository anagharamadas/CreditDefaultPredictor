"""Ledger integrity: complete coverage, valid categories, and consistency with ingest."""

import re
from pathlib import Path

from credit_default.ingest import ALLOWLIST
from credit_default.ledger import (
    BANNED_POST,
    BANNED_UNDERWRITING,
    CATEGORIES,
    LEDGER,
    feature_columns,
)

SCHEMA_MD = Path(__file__).resolve().parents[1] / "docs" / "SCHEMA.md"


def schema_columns() -> list[str]:
    """The 151 measured column names, parsed from the generated profile."""
    cols = []
    for line in SCHEMA_MD.read_text().splitlines():
        m = re.match(r"\| \d+ \| `([^`]+)` \|", line)
        if m:
            cols.append(m.group(1))
    assert len(cols) == 151, f"expected 151 profiled columns, parsed {len(cols)}"
    return cols


def test_every_raw_column_classified_exactly_once():
    assert sorted(LEDGER) == sorted(schema_columns())


def test_all_categories_valid():
    assert {cat for cat, _ in LEDGER.values()} <= set(CATEGORIES)


def test_every_entry_has_a_justification():
    assert all(just.strip() for _, just in LEDGER.values())


def test_ingest_allowlist_contains_no_banned_column():
    banned = {c for c, (cat, _) in LEDGER.items() if cat in (BANNED_POST, BANNED_UNDERWRITING)}
    assert not banned & set(ALLOWLIST)


def test_known_leaks_are_banned():
    for col in ("recoveries", "total_pymnt", "last_fico_range_high", "hardship_flag",
                "debt_settlement_flag", "int_rate", "grade", "installment"):
        cat = LEDGER[col][0]
        assert cat in (BANNED_POST, BANNED_UNDERWRITING), f"{col} must be banned, got {cat}"


def test_zero_undecided_at_p2_exit():
    from credit_default.ledger import undecided_columns

    assert undecided_columns() == []


def test_feature_columns_are_never_banned_or_target():
    feats = set(feature_columns())
    for col in feats:
        assert LEDGER[col][0] == "FEATURE"
    assert "loan_status" not in feats and "issue_d" not in feats
