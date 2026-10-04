"""Performance monitoring under label lag (ticket #57) — the hard part of P10.

The problem, concretely. A loan scored in January 2017 has no outcome in January
2017. Some resolve after 8 months, some after 30, some never within the data window.
So "how is the model performing on 2017-01 loans?" has no single answer — it has an
answer *as of* a point in time, computed on whichever loans have resolved by then,
and that subset is not representative.

It is not representative in a specific, measurable way. In this data, **defaults
resolve faster than repayments** (median 16 months vs 29). So an early look at a
vintage sees a default-enriched sample, and any metric computed on it describes a
population that does not exist in the book.

Two ways to report performance, and the difference between them IS the finding:

- **Naive / as-observed** — evaluate on every loan whose outcome is known today.
  This is what a monitoring dashboard does if nobody thinks about it, and it is not
  comparable across vintages, because older vintages have had longer to resolve.
- **Fixed-horizon** — for every vintage, evaluate only outcomes observable within the
  same number of months after issue. Every month is then judged on an equal
  observation window, so a change in the metric is a change in the model's world
  rather than a change in how long we have been watching.

**Where the timing comes from.** `last_pymnt_d` tells us when a resolved loan
resolved. It is BANNED_POST in the leakage ledger and can never be a feature — the
ledger's own entry anticipated this use: *"legitimate later for label-timing
arithmetic, which is not feature use."* It is loaded here through a separate,
clearly-named path that returns only id/status/timing, so it cannot reach the model.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from credit_default.ingest import RAW_ACCEPTED
from credit_default.labels import STATUS_RULE

#: columns read for TIMING ONLY. Not features, never joined into the model frame.
TIMING_COLUMNS = ["id", "issue_d", "loan_status", "last_pymnt_d", "term"]


def load_outcome_timing(raw: Path | str = RAW_ACCEPTED) -> pd.DataFrame:
    """When each loan's outcome became knowable, for 36-month loans.

    Returns id, issue_month, label (1/0/NA) and months_to_resolution — NaN where the
    loan never resolved inside the data window (right-censored, which is information,
    not a gap to fill).
    """
    frame = pd.read_csv(raw, usecols=TIMING_COLUMNS, low_memory=False)
    frame = frame[frame["term"] == " 36 months"].dropna(subset=["loan_status"])

    issued = pd.to_datetime(frame["issue_d"], format="%b-%Y", errors="coerce")
    last_payment = pd.to_datetime(frame["last_pymnt_d"], format="%b-%Y", errors="coerce")

    label = frame["loan_status"].map({s: rule[0] for s, rule in STATUS_RULE.items()})
    months = (last_payment.dt.year - issued.dt.year) * 12 + (
        last_payment.dt.month - issued.dt.month
    )
    # only a terminal outcome counts as resolved; a Current loan's last payment is
    # not a resolution date
    months = months.where(label.notna())

    return pd.DataFrame(
        {
            "loan_id": frame["id"].astype(str),
            "issue_month": issued.dt.to_period("M").astype(str),
            "label": pd.array(label, dtype="Int8"),
            "months_to_resolution": months.astype("float64"),
        }
    )


def known_at_horizon(timing: pd.DataFrame, horizon_months: int | None) -> pd.DataFrame:
    """Loans whose outcome was observable within `horizon_months` of issue.

    `horizon_months=None` means "everything known by the data snapshot" — the naive
    view, kept so the two can be compared side by side.
    """
    resolved = timing[timing["label"].notna()]
    if horizon_months is None:
        return resolved
    return resolved[resolved["months_to_resolution"] <= horizon_months]


def data_snapshot_month(timing: pd.DataFrame) -> pd.Period:
    """The last month at which this dataset can observe anything.

    Outcomes stop being recorded at the distribution's snapshot, so no vintage can be
    judged over a window that extends past it.
    """
    resolved = timing[timing["months_to_resolution"].notna()]
    observed = pd.PeriodIndex(resolved["issue_month"], freq="M") + resolved[
        "months_to_resolution"
    ].astype(int).to_numpy()
    return observed.max()


def is_evaluable(month: str, horizon_months: int | None, snapshot: pd.Period) -> bool:
    """Can this vintage be judged over `horizon_months` without running past the data?

    The rule is structural, not a tuned cut-off: a 12-month view of a vintage issued
    six months before the data ends is not a weak measurement, it is an impossible
    one. Months that fail this are reported as unevaluable rather than given a number
    computed from whichever few loans happened to resolve early — which is exactly
    the fast-resolver bias this module exists to avoid.
    """
    if horizon_months is None:
        return True
    return pd.Period(month, freq="M") + horizon_months <= snapshot


def performance_by_month(
    predictions: pd.DataFrame,
    timing: pd.DataFrame,
    horizon_months: int | None,
    snapshot: pd.Period | None = None,
) -> pd.DataFrame:
    """Per vintage month: coverage and metrics on whichever loans are evaluable.

    `predictions` needs loan_id, issue_month and p_default. Coverage is reported on
    every row because a metric without it is, per EVAL_PROTOCOL, a violation.
    """
    if snapshot is None:
        snapshot = data_snapshot_month(timing)
    evaluable = known_at_horizon(timing, horizon_months)
    merged = predictions.merge(
        evaluable[["loan_id", "label"]], on="loan_id", how="inner", validate="1:1"
    )
    scored_per_month = predictions.groupby("issue_month").size()

    rows = []
    for month, group in merged.groupby("issue_month", sort=True):
        y = group["label"].astype(int).to_numpy()
        p = group["p_default"].to_numpy()
        # two independent reasons a number may be unavailable, kept separate:
        # the observation window runs past the data (nothing is meaningful), or the
        # evaluable loans are all one class (rates are fine, ranking is undefined)
        window_complete = is_evaluable(month, horizon_months, snapshot)
        both_classes = 0 < y.mean() < 1
        rows.append(
            {
                "issue_month": month,
                "scored": int(scored_per_month.get(month, 0)),
                "evaluable": len(group),
                "coverage": round(len(group) / max(int(scored_per_month.get(month, 0)), 1), 4),
                "window_complete": window_complete,
                "default_rate": round(float(y.mean()), 4) if window_complete else np.nan,
                "mean_predicted": round(float(p.mean()), 4) if window_complete else np.nan,
                "pr_auc": round(float(average_precision_score(y, p)), 4)
                if window_complete and both_classes else np.nan,
                "roc_auc": round(float(roc_auc_score(y, p)), 4)
                if window_complete and both_classes else np.nan,
            }
        )
    table = pd.DataFrame(rows)
    table["calibration_gap"] = (table["mean_predicted"] - table["default_rate"]).round(4)
    table["horizon_months"] = horizon_months if horizon_months is not None else "as-observed"
    return table


def compare_views(
    predictions: pd.DataFrame,
    timing: pd.DataFrame,
    horizon_months: int = 12,
    snapshot: pd.Period | None = None,
) -> pd.DataFrame:
    """The naive view beside the fixed-horizon view — the point of the ticket.

    Where they disagree, the naive number is reporting the passage of time as if it
    were a change in the model.
    """
    if snapshot is None:
        snapshot = data_snapshot_month(timing)
    naive = performance_by_month(predictions, timing, None, snapshot)
    fixed = performance_by_month(predictions, timing, horizon_months, snapshot)
    return pd.concat([naive, fixed], ignore_index=True)


def load_replay_predictions() -> pd.DataFrame:
    """Replayed predictions from the store — what the live service actually produced."""
    from credit_default.store import open_pool

    pool = open_pool()
    try:
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT loan_id, to_char(issue_d, 'YYYY-MM') AS issue_month, p_default"
                " FROM predictions WHERE source = 'replay'"
            ).fetchall()
    finally:
        pool.close()
    return pd.DataFrame(rows, columns=["loan_id", "issue_month", "p_default"])
