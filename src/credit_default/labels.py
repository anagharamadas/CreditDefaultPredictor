"""Target derivation: loan_status -> binary default label, per Charter §3.2.

Every one of the nine observed loan_status values is mapped EXPLICITLY — an
unknown status raises rather than defaulting to anything. Exclusions carry a
reason so the excluded population is measurable, never silently dropped.

Decisions encoded (Charter §3.2, to be confirmed at P2 exit):
- Charged Off -> 1, Fully Paid -> 0.
- "Default" (40 loans): mapped to 1 [ASSUMED — a 121+-day delinquency state that
  almost always charges off; assumption recorded in the charter and revisitable].
- "Does not meet the credit policy" variants: EXCLUDED — pre-2010 legacy population
  admitted under abandoned underwriting rules; not the population being modelled.
- Transitory states (Current, In Grace Period, Late 16-30, Late 31-120): EXCLUDED —
  no terminal outcome exists; mapping them to "repaid" is the censoring bug this
  project is built to avoid (Charter §3.3, RISK_REGISTER R1).
"""

from __future__ import annotations

import pandas as pd

# status -> (label, exclusion_reason). Exactly one of the two is non-None.
STATUS_RULE: dict[str, tuple[int | None, str | None]] = {
    "Fully Paid": (0, None),
    "Charged Off": (1, None),
    "Default": (1, None),  # [ASSUMED] see module docstring
    "Current": (None, "transitory"),
    "In Grace Period": (None, "transitory"),
    "Late (16-30 days)": (None, "transitory"),
    "Late (31-120 days)": (None, "transitory"),
    "Does not meet the credit policy. Status:Fully Paid": (None, "credit_policy_legacy"),
    "Does not meet the credit policy. Status:Charged Off": (None, "credit_policy_legacy"),
}

LABEL_COL = "default"
EXCLUSION_COL = "exclusion_reason"


def add_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Append `default` (Int8; <NA> where excluded) and `exclusion_reason` (category).

    Raises on any loan_status not covered by STATUS_RULE: new statuses must be
    classified deliberately, never absorbed.
    """
    statuses = df["loan_status"].astype("string")
    unknown = set(statuses.dropna().unique()) - set(STATUS_RULE)
    if unknown:
        raise ValueError(f"unmapped loan_status values: {sorted(unknown)}")

    labels = statuses.map({s: lab for s, (lab, _) in STATUS_RULE.items()}).astype("Int8")
    reasons = statuses.map({s: r for s, (_, r) in STATUS_RULE.items()}).astype("category")

    out = df.copy()
    out[LABEL_COL] = labels
    out[EXCLUSION_COL] = reasons
    return out


def labelled_only(df: pd.DataFrame) -> pd.DataFrame:
    """The modelling population: rows with a terminal, in-policy outcome."""
    if LABEL_COL not in df.columns:
        df = add_labels(df)
    return df.loc[df[LABEL_COL].notna()].copy()


def exclusion_report(df: pd.DataFrame) -> pd.Series:
    """Counts by exclusion reason (plus 'labelled') — the honesty artifact."""
    if EXCLUSION_COL not in df.columns:
        df = add_labels(df)
    reasons = df[EXCLUSION_COL].cat.add_categories(["labelled"]).fillna("labelled")
    return reasons.value_counts()


if __name__ == "__main__":
    from credit_default.ingest import INTERIM_ACCEPTED

    frame = add_labels(pd.read_parquet(INTERIM_ACCEPTED))
    print("exclusion report:")
    print(exclusion_report(frame).to_string())
    lab = labelled_only(frame)
    rate = float(lab[LABEL_COL].mean())
    print(f"\nlabelled population: {len(lab):,} rows; default rate {rate:.4f}")
