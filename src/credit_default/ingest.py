"""Typed ingest of the raw accepted-loans CSV.

Reads only the candidate application-time columns (allowlist, not blocklist — a column
absent here never enters the pipeline; final keep/ban decisions belong to the P2 leakage
ledger). Every dtype is explicit: pandas' dtype inference on this file is unreliable
(mixed-type columns, footer junk), see RISK_REGISTER R14.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_ACCEPTED = Path("data/raw/kaggle/accepted_2007_to_2018Q4.csv")
INTERIM_ACCEPTED = Path("data/interim/accepted.parquet")

# Measured facts about the raw file (data/README.md manifest); asserted on every ingest.
RAW_ROWS = 2_260_701
FOOTER_ROWS = 33  # trailing rows with null id/term/loan_status
CLEAN_ROWS = RAW_ROWS - FOOTER_ROWS

# Candidate columns. METADATA/TARGET ingredients first, then application-time feature
# candidates. Deliberately absent: grade/sub_grade/int_rate (excluded by Charter §1),
# all post-origination columns (P2 will ban them formally), free-text desc/emp_title/title
# (BACKLOG.md), joint-applicant fields (timing unresolved — P2 decides; re-add if kept).
DTYPES: dict[str, str] = {
    # metadata / target ingredients
    "id": "string",
    "loan_status": "category",
    "term": "category",
    # loan application
    "loan_amnt": "float64",
    "purpose": "category",
    "application_type": "category",
    # borrower profile
    "emp_length": "category",
    "home_ownership": "category",
    "annual_inc": "float64",
    "verification_status": "category",
    "zip_code": "string",
    "addr_state": "category",
    # bureau-derived, populated at application
    "dti": "float64",
    "delinq_2yrs": "float64",
    "fico_range_low": "float64",
    "fico_range_high": "float64",
    "inq_last_6mths": "float64",
    "mths_since_last_delinq": "float64",
    "mths_since_last_record": "float64",
    "open_acc": "float64",
    "pub_rec": "float64",
    "revol_bal": "float64",
    "revol_util": "float64",
    "total_acc": "float64",
    "mort_acc": "float64",
    "pub_rec_bankruptcies": "float64",
}
DATE_COLS = ["issue_d", "earliest_cr_line"]  # Mon-YYYY strings, parsed after read
ALLOWLIST = list(DTYPES) + DATE_COLS


def read_accepted(path: Path | str = RAW_ACCEPTED, *, strict: bool = True) -> pd.DataFrame:
    """Read the raw accepted-loans CSV into a typed frame, footer junk dropped.

    strict=True asserts the measured row counts of the canonical file; pass False for
    samples/fixtures.
    """
    df = pd.read_csv(path, usecols=ALLOWLIST, dtype=DTYPES, low_memory=False)
    if strict and len(df) != RAW_ROWS:
        raise ValueError(f"expected {RAW_ROWS} raw rows, got {len(df)} — wrong file?")

    footer = df["loan_status"].isna()
    if strict and int(footer.sum()) != FOOTER_ROWS:
        raise ValueError(f"expected {FOOTER_ROWS} footer rows, got {int(footer.sum())}")
    df = df.loc[~footer].copy()

    for col in DATE_COLS:
        df[col] = pd.to_datetime(df[col], format="%b-%Y", errors="raise")

    if strict and len(df) != CLEAN_ROWS:
        raise ValueError(f"expected {CLEAN_ROWS} clean rows, got {len(df)}")
    return df


def build_interim(
    raw: Path | str = RAW_ACCEPTED, out: Path | str = INTERIM_ACCEPTED
) -> Path:
    """Raw CSV -> typed parquet. The parquet is derived data: reproducible, gitignored."""
    out = Path(out)
    df = read_accepted(raw)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out


if __name__ == "__main__":
    path = build_interim()
    print(f"wrote {path} ({path.stat().st_size / 1e6:.0f} MB)")
