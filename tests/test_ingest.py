"""Unit tests for the ingest module, on a synthetic fixture — no raw data needed."""

import pandas as pd
import pytest

from credit_default.ingest import (
    ALLOWLIST,
    CLEAN_ROWS,
    DATE_COLS,
    RAW_ROWS,
    read_accepted,
)

# Valid sample values for the non-numeric columns; every other allowlist column is a
# numeric bureau field and gets a small number.
SAMPLE_VALUES = {
    "id": "123",
    "loan_status": "Fully Paid",
    "term": " 36 months",
    "purpose": "debt_consolidation",
    "application_type": "Individual",
    "emp_length": "10+ years",
    "home_ownership": "MORTGAGE",
    "verification_status": "Not Verified",
    "disbursement_method": "Cash",
    "zip_code": "190xx",
    "addr_state": "PA",
    "issue_d": "Dec-2015",
    "earliest_cr_line": "Aug-2003",
    "loan_amnt": "3600",
    "fico_range_low": "675",
    "fico_range_high": "679",
}


def _fixture_csv(tmp_path, n_good=3, n_footer=1):
    """Minimal CSV covering the full allowlist plus decoys that must not survive."""
    row = {col: SAMPLE_VALUES.get(col, "1") for col in ALLOWLIST}
    # decoy columns that must NOT be ingested
    row |= {"int_rate": "13.99", "grade": "C", "total_pymnt": "4066.9"}
    rows = [dict(row, id=str(i)) for i in range(n_good)]
    rows += [{k: "" for k in row} | {"id": "Total amount funded: 999"}] * n_footer
    path = tmp_path / "mini.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_footer_rows_dropped_and_types_applied(tmp_path):
    df = read_accepted(_fixture_csv(tmp_path), strict=False)
    assert len(df) == 3
    assert df["loan_amnt"].dtype == "float64"
    assert df["term"].dtype == "category"
    assert df["issue_d"].dtype == "datetime64[ns]"
    assert df["issue_d"].iloc[0] == pd.Timestamp("2015-12-01")
    assert df["tot_cur_bal"].dtype == "float64"  # bureau block typed too


def test_leakage_decoys_never_ingested(tmp_path):
    df = read_accepted(_fixture_csv(tmp_path), strict=False)
    for banned in ("int_rate", "grade", "total_pymnt"):
        assert banned not in df.columns
    assert set(df.columns) == set(ALLOWLIST)


def test_allowlist_is_ledger_derived():
    from credit_default.ledger import feature_columns

    assert set(ALLOWLIST) == set(feature_columns()) | {"id", "issue_d", "loan_status"}
    assert len(ALLOWLIST) == 84  # 81 FEATURE + 3 essentials
    assert set(DATE_COLS) <= set(ALLOWLIST)


def test_strict_mode_rejects_wrong_rowcount(tmp_path):
    with pytest.raises(ValueError, match="wrong file"):
        read_accepted(_fixture_csv(tmp_path), strict=True)


def test_measured_constants_consistent():
    assert RAW_ROWS - CLEAN_ROWS == 33
