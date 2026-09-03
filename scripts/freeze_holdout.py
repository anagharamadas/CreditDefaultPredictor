"""Freeze the holdout manifest from the interim data. Run once, at P3.

Run:  PYTHONPATH=src python scripts/freeze_holdout.py
"""

import pandas as pd

from credit_default.holdout import freeze, verify
from credit_default.ingest import INTERIM_ACCEPTED


def main() -> None:
    df = pd.read_parquet(INTERIM_ACCEPTED, columns=["id", "issue_d", "term", "loan_status"])
    meta = freeze(df)
    print(f"frozen: {meta['n_loans']:,} loans, sha256 {meta['sha256'][:16]}…")
    verify(df)
    print("verify: OK (hash + recomputation match)")


if __name__ == "__main__":
    main()
