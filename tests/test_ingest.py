"""Unit tests for the ingest module, on a synthetic fixture — no raw data needed."""

import pandas as pd
import pytest

from credit_default.ingest import ALLOWLIST, CLEAN_ROWS, RAW_ROWS, read_accepted


def _fixture_csv(tmp_path, n_good=3, n_footer=1):
    """Minimal CSV with the allowlist columns plus decoys that must not survive."""
    row = {
        "id": "123", "loan_status": "Fully Paid", "term": " 36 months",
        "loan_amnt": "3600", "purpose": "debt_consolidation",
        "application_type": "Individual", "emp_length": "10+ years",
        "home_ownership": "MORTGAGE", "annual_inc": "55000",
        "verification_status": "Not Verified", "zip_code": "190xx",
        "addr_state": "PA", "dti": "5.91", "delinq_2yrs": "0",
        "fico_range_low": "675", "fico_range_high": "679", "inq_last_6mths": "1",
        "mths_since_last_delinq": "30", "mths_since_last_record": "",
        "open_acc": "7", "pub_rec": "0", "revol_bal": "2765",
        "revol_util": "29.7", "total_acc": "13", "mort_acc": "1",
        "pub_rec_bankruptcies": "0", "issue_d": "Dec-2015",
        "earliest_cr_line": "Aug-2003",
        # decoy columns that must NOT be ingested
        "int_rate": "13.99", "grade": "C", "total_pymnt": "4066.9",
    }
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


def test_leakage_decoys_never_ingested(tmp_path):
    df = read_accepted(_fixture_csv(tmp_path), strict=False)
    for banned in ("int_rate", "grade", "total_pymnt"):
        assert banned not in df.columns
    assert set(df.columns) == set(ALLOWLIST)


def test_strict_mode_rejects_wrong_rowcount(tmp_path):
    with pytest.raises(ValueError, match="wrong file"):
        read_accepted(_fixture_csv(tmp_path), strict=True)


def test_measured_constants_consistent():
    assert RAW_ROWS - CLEAN_ROWS == 33
