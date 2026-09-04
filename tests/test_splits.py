"""Split rules: boundary months, term filter, train-label requirement, maturity guard."""

import pandas as pd
import pytest

from credit_default.splits import (
    DATA_END,
    SplitConfig,
    assign_split,
    split_frame,
    split_summary,
)


def _df(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    """rows: (issue month 'YYYY-MM', term, loan_status)."""
    return pd.DataFrame(
        {
            "id": [str(i) for i in range(len(rows))],
            "issue_d": [pd.Timestamp(f"{m}-01") for m, _, _ in rows],
            "term": pd.Categorical([t for _, t, _ in rows]),
            "loan_status": pd.Categorical([s for _, _, s in rows]),
        }
    )


@pytest.mark.parametrize(
    ("month", "term", "status", "expected"),
    [
        ("2013-01", " 36 months", "Fully Paid", "train"),      # first train month
        ("2015-12", " 36 months", "Charged Off", "train"),     # last train month
        ("2012-12", " 36 months", "Fully Paid", "none"),       # before window
        ("2016-01", " 36 months", "Fully Paid", "validation"), # boundary: month after train
        ("2016-06", " 36 months", "Current", "validation"),    # unlabelled kept in eval splits
        ("2016-07", " 36 months", "Fully Paid", "holdout"),
        ("2016-12", " 36 months", "Charged Off", "holdout"),
        ("2017-01", " 36 months", "Current", "replay"),
        ("2018-12", " 36 months", "Current", "replay"),
        ("2014-06", " 60 months", "Fully Paid", "none"),       # 60-month excluded everywhere
        ("2017-06", " 60 months", "Current", "none"),
    ],
)
def test_boundary_assignments(month, term, status, expected):
    out = assign_split(_df([(month, term, status)]))
    assert out["split"].iloc[0] == expected


def test_train_requires_terminal_label():
    out = assign_split(_df([("2014-06", " 36 months", "Current")]))
    assert out["split"].iloc[0] == "none"  # in-window but unresolved -> excluded from train


def test_maturity_guard_rejects_immature_train_window():
    with pytest.raises(ValueError, match="immature"):
        SplitConfig(train_end=pd.Timestamp("2016-06-01"))


def test_default_train_end_is_exactly_at_the_maturity_limit():
    cfg = SplitConfig()
    assert cfg.train_end + pd.DateOffset(months=36) == DATA_END


def test_boundaries_must_be_ordered():
    with pytest.raises(ValueError, match="ordered"):
        SplitConfig(validation_end=pd.Timestamp("2015-06-01"))


def test_splits_are_disjoint_and_deterministic():
    df = _df(
        [
            ("2014-01", " 36 months", "Fully Paid"),
            ("2016-03", " 36 months", "Fully Paid"),
            ("2016-09", " 36 months", "Charged Off"),
            ("2018-01", " 36 months", "Current"),
        ]
    )
    a, b = assign_split(df), assign_split(df)
    assert a["split"].tolist() == b["split"].tolist()  # no randomness to differ
    assert a["split"].tolist() == ["train", "validation", "holdout", "replay"]
    assert len(split_frame(df, "train")) == 1


def test_summary_counts():
    df = _df(
        [
            ("2014-01", " 36 months", "Fully Paid"),
            ("2014-02", " 36 months", "Charged Off"),
            ("2016-02", " 36 months", "Current"),
        ]
    )
    s = split_summary(df)
    assert s.loc["train", "loans"] == 2
    assert s.loc["train", "defaults"] == 1
    assert s.loc["validation", "label_coverage"] == 0.0
