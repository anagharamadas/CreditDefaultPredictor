"""Contract tests: violations are caught, and the real interim data passes.

The synthetic tests always run. The full-data test runs only when the interim parquet
exists locally (it is derived data, absent in CI until the pipeline builds it there).
"""

from pathlib import Path

import pandas as pd
import pandera.errors
import pytest

from credit_default.contract import validate_accepted
from credit_default.ingest import INTERIM_ACCEPTED


def _valid_row() -> dict:
    from credit_default.contract import BUREAU_RANGES

    row = {
        "id": "123", "loan_status": "Fully Paid", "term": " 36 months",
        "issue_d": pd.Timestamp("2015-12-01"), "loan_amnt": 3600.0,
        "purpose": "debt_consolidation", "application_type": "Individual",
        "emp_length": "10+ years", "home_ownership": "MORTGAGE",
        "annual_inc": 55000.0, "verification_status": "Not Verified",
        "disbursement_method": "Cash",
        "zip_code": "190xx", "addr_state": "PA", "dti": 5.91,
        "delinq_2yrs": 0.0, "fico_range_low": 675.0, "fico_range_high": 679.0,
        "inq_last_6mths": 1.0, "mths_since_last_delinq": 30.0,
        "mths_since_last_record": None, "open_acc": 7.0, "pub_rec": 0.0,
        "revol_bal": 2765.0, "revol_util": 29.7, "total_acc": 13.0,
        "mort_acc": 1.0, "pub_rec_bankruptcies": 0.0,
        "earliest_cr_line": pd.Timestamp("2003-08-01"),
    }
    row |= {name: 1.0 for name in BUREAU_RANGES}  # all in-range for every bureau field
    return row


CATEGORY_COLS = ("loan_status", "term", "purpose", "application_type", "emp_length",
                 "home_ownership", "verification_status", "disbursement_method",
                 "addr_state")
STRING_OR_DATE = ("id", "zip_code", "issue_d", "earliest_cr_line")


def _frame(**overrides) -> pd.DataFrame:
    df = pd.DataFrame([_valid_row() | overrides])
    for col in df.columns:
        if col in CATEGORY_COLS:
            df[col] = df[col].astype("category")
        elif col not in STRING_OR_DATE:
            df[col] = df[col].astype("float64")
    return df


def test_valid_frame_passes():
    validate_accepted(_frame())


@pytest.mark.parametrize(
    "overrides",
    [
        {"loan_amnt": 999_999.0},                      # out of range
        {"fico_range_low": 700.0, "fico_range_high": 650.0},  # cross-column violation
        {"zip_code": "19104"},                         # unmasked zip
        {"issue_d": pd.Timestamp("2022-01-01")},       # outside dataset window
        {"earliest_cr_line": pd.Timestamp("2016-01-01")},  # postdates issue_d
        {"loan_status": "Refinanced"},                 # unknown category
    ],
)
def test_violations_are_caught(overrides):
    with pytest.raises(pandera.errors.SchemaErrors):
        validate_accepted(_frame(**overrides))


def test_unexpected_extra_column_rejected():
    df = _frame()
    df["total_pymnt"] = 4066.9  # leakage column smuggled in
    with pytest.raises(pandera.errors.SchemaErrors):
        validate_accepted(df)


@pytest.mark.realdata
@pytest.mark.skipif(not Path(INTERIM_ACCEPTED).exists(), reason="interim parquet not built")
def test_real_interim_data_passes_contract():
    df = pd.read_parquet(INTERIM_ACCEPTED)
    validate_accepted(df)
    assert len(df) == 2_260_668
