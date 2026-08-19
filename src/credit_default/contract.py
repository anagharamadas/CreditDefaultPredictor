"""Executable data contract for the ingested accepted-loans frame.

Every check below encodes a fact MEASURED from the real file (docs/SCHEMA.md), not
copied from documentation. Bounds are the measured range plus explicit headroom where a
legitimately new value could appear (e.g. FICO uses the scale bounds 300-850, not the
observed 610-845); category sets are closed because a new category appearing IS a
contract violation we want to hear about.

Validated at ingest (P1) and — via the same definitions — against serving payloads (P8).
Human-readable version: docs/DATA_CONTRACT.md.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Check, Column

# Measured category sets (closed vocabularies; see docs/SCHEMA.md)
LOAN_STATUSES = [
    "Charged Off", "Current", "Default", "Fully Paid",
    "Does not meet the credit policy. Status:Charged Off",
    "Does not meet the credit policy. Status:Fully Paid",
    "In Grace Period", "Late (16-30 days)", "Late (31-120 days)",
]
TERMS = [" 36 months", " 60 months"]
PURPOSES = [
    "car", "credit_card", "debt_consolidation", "educational", "home_improvement",
    "house", "major_purchase", "medical", "moving", "other", "renewable_energy",
    "small_business", "vacation", "wedding",
]
EMP_LENGTHS = [
    "< 1 year", "1 year", "2 years", "3 years", "4 years", "5 years",
    "6 years", "7 years", "8 years", "9 years", "10+ years",
]
HOME_OWNERSHIP = ["ANY", "MORTGAGE", "NONE", "OTHER", "OWN", "RENT"]
VERIFICATION = ["Not Verified", "Source Verified", "Verified"]
APPLICATION_TYPES = ["Individual", "Joint App"]
US_STATES_DC = [
    "AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "IA",
    "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS",
    "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY",
]

ACCEPTED_SCHEMA = pa.DataFrameSchema(
    columns={
        # --- metadata / target ingredients ---
        "id": Column(str, Check.str_matches(r"^\d+$"), nullable=False, unique=True),
        "loan_status": Column(pa.Category, Check.isin(LOAN_STATUSES), nullable=False),
        "term": Column(pa.Category, Check.isin(TERMS), nullable=False),
        "issue_d": Column(
            "datetime64[ns]",
            Check.in_range(pd.Timestamp("2007-06-01"), pd.Timestamp("2018-12-01")),
            nullable=False,
        ),
        # --- loan application ---
        # measured 500-40,000; headroom to LendingClub's historical product cap
        "loan_amnt": Column(float, Check.in_range(500, 50_000), nullable=False),
        "purpose": Column(pa.Category, Check.isin(PURPOSES), nullable=False),
        "application_type": Column(pa.Category, Check.isin(APPLICATION_TYPES), nullable=False),
        # --- borrower profile ---
        "emp_length": Column(pa.Category, Check.isin(EMP_LENGTHS), nullable=True),  # 6.5% null
        "home_ownership": Column(pa.Category, Check.isin(HOME_OWNERSHIP), nullable=False),
        # self-reported; measured max 1.1e8 — no upper bound is defensible, cap at 1e9 sanity.
        # 4 nulls measured, all in 2007 credit-policy legacy rows (P2 excludes that population)
        "annual_inc": Column(float, Check.in_range(0, 1e9), nullable=True),
        "verification_status": Column(pa.Category, Check.isin(VERIFICATION), nullable=False),
        # 1 null measured (a 2017 loan)
        "zip_code": Column(str, Check.str_matches(r"^\d{3}xx$"), nullable=True),
        "addr_state": Column(pa.Category, Check.isin(US_STATES_DC), nullable=False),
        # --- bureau-derived at application ---
        # measured -1..999 incl. sentinel-like values; documented in DATA_CONTRACT.md
        "dti": Column(float, Check.in_range(-2, 1000), nullable=True),
        "delinq_2yrs": Column(float, Check.in_range(0, 100), nullable=True),
        "fico_range_low": Column(float, Check.in_range(300, 850), nullable=False),
        "fico_range_high": Column(float, Check.in_range(300, 850), nullable=False),
        "inq_last_6mths": Column(float, Check.in_range(0, 50), nullable=True),
        # ~51% / ~84% null: null means "no delinquency/record on file" — meaningful, kept
        "mths_since_last_delinq": Column(float, Check.in_range(0, 300), nullable=True),
        "mths_since_last_record": Column(float, Check.in_range(0, 300), nullable=True),
        "open_acc": Column(float, Check.in_range(0, 200), nullable=True),
        "pub_rec": Column(float, Check.in_range(0, 100), nullable=True),
        "revol_bal": Column(float, Check.ge(0), nullable=True),
        # utilisation is a percent; measured max 892.3 (>100% is real: over-limit)
        "revol_util": Column(float, Check.in_range(0, 1000), nullable=True),
        "total_acc": Column(float, Check.in_range(1, 300), nullable=True),
        "mort_acc": Column(float, Check.in_range(0, 100), nullable=True),
        "pub_rec_bankruptcies": Column(float, Check.in_range(0, 30), nullable=True),
        # 29 nulls measured, all 2007 credit-policy legacy rows (P2 excludes that population)
        "earliest_cr_line": Column(
            "datetime64[ns]",
            Check.in_range(pd.Timestamp("1900-01-01"), pd.Timestamp("2018-12-01")),
            nullable=True,
        ),
    },
    checks=[
        # cross-column invariants
        pa.Check(
            lambda df: df["fico_range_high"] >= df["fico_range_low"],
            name="fico_high_ge_low",
            error="fico_range_high must be >= fico_range_low",
        ),
        pa.Check(
            lambda df: df["earliest_cr_line"].isna() | (df["earliest_cr_line"] <= df["issue_d"]),
            name="credit_history_precedes_issue",
            error="earliest_cr_line must be on or before issue_d",
        ),
    ],
    strict=True,  # a column not named here is a contract violation, both directions
    coerce=False,  # ingest owns dtypes; the contract verifies, it does not repair
)


def validate_accepted(df: pd.DataFrame, *, lazy: bool = True) -> pd.DataFrame:
    """Validate an ingested frame; raises pandera.errors.SchemaError(s) on violation.

    lazy=True collects every violation before raising, so a failure report names all
    broken expectations at once rather than the first.
    """
    return ACCEPTED_SCHEMA.validate(df, lazy=lazy)


if __name__ == "__main__":
    from credit_default.ingest import INTERIM_ACCEPTED

    frame = pd.read_parquet(INTERIM_ACCEPTED)
    validate_accepted(frame)
    print(f"contract OK: {len(frame):,} rows x {len(frame.columns)} columns pass all checks")
