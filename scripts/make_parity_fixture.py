"""Generate the committed parity fixture: tests/fixtures/parity_sample.csv.

Synthetic on purpose — raw data is never committed (data/README.md), so the fixture
fabricates realistic rows instead: every categorical value gets used, every nullable
column gets real gaps, numerics span their contract ranges. Seeded and deterministic;
regenerating produces the identical file. The parity test pins the file's sha256, so
a regeneration that changes anything must update the pinned hash consciously.

Run:  PYTHONPATH=src python scripts/make_parity_fixture.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from credit_default.contract import (
    APPLICATION_TYPES,
    BUREAU_RANGES,
    DISBURSEMENT_METHODS,
    EMP_LENGTHS,
    HOME_OWNERSHIP,
    LOAN_STATUSES,
    PURPOSES,
    TERMS,
    US_STATES_DC,
    VERIFICATION,
)
from credit_default.ingest import ALLOWLIST, CATEGORICAL_COLS, DATE_COLS

OUT = Path("tests/fixtures/parity_sample.csv")
N = 64
SEED = 20260904

CATEGORY_SETS = {
    "loan_status": LOAN_STATUSES,
    "term": TERMS,
    "purpose": PURPOSES,
    "emp_length": EMP_LENGTHS,
    "home_ownership": HOME_OWNERSHIP,
    "verification_status": VERIFICATION,
    "application_type": APPLICATION_TYPES,
    "disbursement_method": DISBURSEMENT_METHODS,
    "addr_state": US_STATES_DC,
}

# Core numerics not in BUREAU_RANGES: plausible in-contract ranges.
CORE_RANGES = {
    "loan_amnt": (1000, 40000),
    "annual_inc": (20000, 250000),
    "dti": (0, 45),
    "delinq_2yrs": (0, 5),
    "fico_range_low": (620, 840),
    "fico_range_high": (624, 844),  # overwritten below to keep the contract invariant
    "inq_last_6mths": (0, 6),
    "mths_since_last_delinq": (0, 120),
    "mths_since_last_record": (0, 120),
    "open_acc": (1, 30),
    "pub_rec": (0, 3),
    "revol_bal": (0, 80000),
    "revol_util": (0, 120),
    "total_acc": (2, 60),
    "mort_acc": (0, 6),
    "pub_rec_bankruptcies": (0, 2),
}

# ~25% missing in the meaningful-null / regime-dependent columns.
NULLABLE_HEAVY = set(BUREAU_RANGES) | {
    "mths_since_last_delinq", "mths_since_last_record", "dti", "revol_util",
    "mort_acc", "pub_rec_bankruptcies", "emp_length",
}


def main() -> None:
    rng = np.random.default_rng(SEED)
    cols: dict[str, list] = {}
    for col in ALLOWLIST:
        if col == "id":
            cols[col] = [str(1_000_000 + i) for i in range(N)]
        elif col == "zip_code":
            cols[col] = [f"{rng.integers(100, 999):03d}xx" for _ in range(N)]
        elif col in DATE_COLS:
            continue  # handled together below
        elif col in CATEGORICAL_COLS:
            values = CATEGORY_SETS[col]
            # cycle so every category appears at least once, then shuffle-ish via rng
            cols[col] = [values[(i + int(rng.integers(0, len(values)))) % len(values)]
                         for i in range(N)]
        else:
            lo, hi = CORE_RANGES.get(col) or BUREAU_RANGES[col]
            vals = np.round(rng.uniform(lo, hi, N), 2)
            cols[col] = vals.tolist()

    # dates: issue inside the TRAIN window (the pipeline's gate refuses to fit on
    # anything else — the fixture models a lawful fit + serve-transform scenario);
    # earliest_cr_line 2-30 years before issue
    issue_year = rng.integers(2013, 2016, N)
    issue_month = rng.integers(1, 13, N)
    issue = [pd.Timestamp(int(y), int(m), 1) for y, m in zip(issue_year, issue_month)]
    history_months = rng.integers(24, 360, N)
    earliest = [i - pd.DateOffset(months=int(h)) for i, h in zip(issue, history_months)]
    cols["issue_d"] = [d.strftime("%b-%Y") for d in issue]
    cols["earliest_cr_line"] = [d.strftime("%b-%Y") for d in earliest]

    df = pd.DataFrame(cols)[ALLOWLIST]

    # plant missing values (never in required fields)
    for col in sorted(NULLABLE_HEAVY):
        mask = rng.uniform(size=N) < 0.25
        df.loc[mask, col] = pd.NA

    # make fico_range_high consistent with low (contract invariant)
    df["fico_range_high"] = (pd.to_numeric(df["fico_range_low"]) + 4).clip(upper=850)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(f"wrote {OUT} ({N} rows); sha256 {digest}")


if __name__ == "__main__":
    main()
