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

# Bureau-block bounds: (0, cap) where cap = measured max (docs/SCHEMA.md) widened with
# headroom for legitimate unseen values. All nullable — bureau fields carry meaningful
# nulls ("no such event") and regime-dependent availability (the 2015+ block).
BUREAU_RANGES: dict[str, tuple[float, float]] = {
    "collections_12_mths_ex_med": (0, 50),        # measured max 20
    "mths_since_last_major_derog": (0, 400),      # 226
    "acc_now_delinq": (0, 50),                    # 14
    "tot_coll_amt": (0, 2e7),                     # 9.15e6
    "tot_cur_bal": (0, 2e7),                      # 9.97e6
    "open_acc_6m": (0, 50),                       # 18
    "open_act_il": (0, 150),                      # 57
    "open_il_12m": (0, 60),                       # 25
    "open_il_24m": (0, 120),                      # 51
    "mths_since_rcnt_il": (0, 999),               # 511
    "total_bal_il": (0, 5e6),                     # 1.84e6
    "il_util": (0, 1000),                         # 1000 (over-limit is real)
    "open_rv_12m": (0, 80),                       # 28
    "open_rv_24m": (0, 150),                      # 60
    "max_bal_bc": (0, 5e6),                       # 1.17e6
    "all_util": (0, 1000),                        # 239
    "total_rev_hi_lim": (0, 2e7),                 # 1e7
    "inq_fi": (0, 150),                           # 48
    "total_cu_tl": (0, 300),                      # 111
    "inq_last_12m": (0, 200),                     # 67
    "acc_open_past_24mths": (0, 150),             # 64
    "avg_cur_bal": (0, 5e6),                      # 958k
    "bc_open_to_buy": (0, 5e6),                   # 711k
    "bc_util": (0, 1000),                         # 339.6
    "chargeoff_within_12_mths": (0, 50),          # 10
    "delinq_amnt": (0, 5e6),                      # 250k
    "mo_sin_old_il_acct": (0, 999),               # 999 (looks like a coded ceiling)
    "mo_sin_old_rev_tl_op": (0, 999),             # 999
    "mo_sin_rcnt_rev_tl_op": (0, 999),            # 547
    "mo_sin_rcnt_tl": (0, 999),                   # 382
    "mths_since_recent_bc": (0, 999),             # 661
    "mths_since_recent_bc_dlq": (0, 400),         # 202
    "mths_since_recent_inq": (0, 60),             # 25
    "mths_since_recent_revol_delinq": (0, 400),   # 202
    "num_accts_ever_120_pd": (0, 150),            # 58
    "num_actv_bc_tl": (0, 150),                   # 50
    "num_actv_rev_tl": (0, 150),                  # 72
    "num_bc_sats": (0, 150),                      # 71
    "num_bc_tl": (0, 200),                        # 86
    "num_il_tl": (0, 300),                        # 159
    "num_op_rev_tl": (0, 200),                    # 91
    "num_rev_accts": (0, 300),                    # 151
    "num_rev_tl_bal_gt_0": (0, 150),              # 65
    "num_sats": (0, 250),                         # 101
    "num_tl_120dpd_2m": (0, 30),                  # 7
    "num_tl_30dpd": (0, 30),                      # 4
    "num_tl_90g_dpd_24m": (0, 150),               # 58
    "num_tl_op_past_12m": (0, 80),                # 32
    "pct_tl_nvr_dlq": (0, 100),                   # a percentage
    "percent_bc_gt_75": (0, 100),                 # a percentage
    "tax_liens": (0, 200),                        # 85
    "tot_hi_cred_lim": (0, 2e7),                  # 1e7
    "total_bal_ex_mort": (0, 1e7),                # 3.41e6
    "total_bc_limit": (0, 5e6),                   # 1.57e6
    "total_il_high_credit_limit": (0, 5e6),       # 2.12e6
}

DISBURSEMENT_METHODS = ["Cash", "DirectPay"]

_BUREAU_COLUMNS = {
    name: Column(float, Check.in_range(lo, hi), nullable=True)
    for name, (lo, hi) in BUREAU_RANGES.items()
}

ACCEPTED_SCHEMA = pa.DataFrameSchema(
    columns={
        **_BUREAU_COLUMNS,
        "disbursement_method": Column(
            pa.Category, Check.isin(DISBURSEMENT_METHODS), nullable=False
        ),
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
