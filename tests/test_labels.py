"""Every loan_status mapping is pinned; unknown statuses refuse to pass silently."""

import pandas as pd
import pytest

from credit_default.labels import (
    STATUS_RULE,
    add_labels,
    exclusion_report,
    labelled_only,
)


def _df(statuses: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"loan_status": pd.Categorical(statuses)})


# The full, explicit truth table — one test case per observed status.
@pytest.mark.parametrize(
    ("status", "label", "reason"),
    [
        ("Fully Paid", 0, None),
        ("Charged Off", 1, None),
        ("Default", 1, None),
        ("Current", None, "transitory"),
        ("In Grace Period", None, "transitory"),
        ("Late (16-30 days)", None, "transitory"),
        ("Late (31-120 days)", None, "transitory"),
        ("Does not meet the credit policy. Status:Fully Paid", None, "credit_policy_legacy"),
        ("Does not meet the credit policy. Status:Charged Off", None, "credit_policy_legacy"),
    ],
)
def test_status_truth_table(status, label, reason):
    out = add_labels(_df([status]))
    got_label = out["default"].iloc[0]
    got_reason = out["exclusion_reason"].iloc[0]
    if label is None:
        assert pd.isna(got_label)
        assert got_reason == reason
    else:
        assert got_label == label
        assert pd.isna(got_reason)


def test_truth_table_covers_rule_exactly():
    tested = {s for s, _, _ in test_status_truth_table.pytestmark[0].args[1]}
    assert tested == set(STATUS_RULE)


def test_unknown_status_raises():
    with pytest.raises(ValueError, match="unmapped"):
        add_labels(_df(["Refinanced"]))


def test_transitory_never_labelled_repaid():
    out = add_labels(_df(["Current", "In Grace Period", "Late (31-120 days)"]))
    assert out["default"].isna().all()


def test_labelled_only_filters_and_keeps_labels():
    out = labelled_only(_df(["Fully Paid", "Current", "Charged Off"]))
    assert len(out) == 2
    assert sorted(out["default"].tolist()) == [0, 1]


def test_exclusion_report_counts():
    rep = exclusion_report(_df(["Fully Paid", "Current", "Current", "Charged Off"]))
    assert rep["labelled"] == 2
    assert rep["transitory"] == 2
