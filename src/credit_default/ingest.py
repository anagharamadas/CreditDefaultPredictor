"""Typed ingest of the raw accepted-loans CSV.

The column allowlist is DERIVED from the leakage ledger: everything classified
FEATURE, plus the three non-feature essentials (id, issue_d, loan_status). A column
the ledger didn't approve cannot be ingested — the audit and the reader cannot
disagree. Every dtype is explicit: pandas' dtype inference on this file is
unreliable (mixed-type columns, footer junk), see RISK_REGISTER R14.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from credit_default.ledger import feature_columns

RAW_ACCEPTED = Path("data/raw/kaggle/accepted_2007_to_2018Q4.csv")
INTERIM_ACCEPTED = Path("data/interim/accepted.parquet")

# Measured facts about the raw file (data/README.md manifest); asserted on every ingest.
RAW_ROWS = 2_260_701
FOOTER_ROWS = 33  # trailing rows with null id/term/loan_status
CLEAN_ROWS = RAW_ROWS - FOOTER_ROWS

# Non-feature columns the pipeline still needs: join key, split key, target source.
NON_FEATURE_REQUIRED = ("id", "issue_d", "loan_status")

# Dtype policy. Everything not listed here is a numeric bureau field -> float64.
CATEGORICAL_COLS = {
    "loan_status", "term", "purpose", "application_type", "emp_length",
    "home_ownership", "verification_status", "disbursement_method", "addr_state",
}
STRING_COLS = {"id", "zip_code"}
DATE_COLS = ["issue_d", "earliest_cr_line"]  # Mon-YYYY strings, parsed after read

ALLOWLIST = sorted(set(feature_columns()) | set(NON_FEATURE_REQUIRED))

DTYPES: dict[str, str] = {
    col: (
        "category"
        if col in CATEGORICAL_COLS
        else "string" if col in STRING_COLS else "float64"
    )
    for col in ALLOWLIST
    if col not in DATE_COLS
}


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
    print(f"wrote {path} ({path.stat().st_size / 1e6:.0f} MB, {len(ALLOWLIST)} columns)")
