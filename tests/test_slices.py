"""Slice report: key derivation, per-slice arithmetic, flagging heuristics."""

import numpy as np
import pandas as pd

from credit_default.slices import flag_notable, slice_frame, slice_report


def _frame(n=1000, seed=3):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "issue_d": pd.Timestamp("2016-02-01"),
            "purpose": pd.Categorical(rng.choice(["credit_card", "car"], n)),
            "addr_state": pd.Categorical(rng.choice(list("ABCDEFGHIJKLM"), n)),
            "annual_inc": rng.uniform(20_000, 200_000, n),
            "fico_range_low": rng.integers(620, 820, n).astype(float),
        }
    )


def test_slice_frame_families_and_state_grouping():
    keys = slice_frame(_frame())
    assert list(keys.columns) == ["vintage_month", "purpose", "state", "income_band", "fico_band"]
    assert keys["state"].nunique() <= 11  # top-10 + OTHER
    assert "OTHER" in set(keys["state"])
    assert set(keys["income_band"]) == {"Q1", "Q2", "Q3", "Q4", "Q5"}


def test_slice_report_rates_and_single_class_guard():
    x = _frame()
    y = (x["purpose"] == "car").astype(float)  # all car loans default, no credit_card does
    p = np.full(len(x), 0.5)
    report = slice_report(x, y, p)
    purpose = report[report["family"] == "purpose"].set_index("slice")
    assert purpose.loc["car", "default_rate"] == 1.0
    assert purpose.loc["credit_card", "default_rate"] == 0.0
    assert np.isnan(purpose.loc["car", "pr_auc"])  # single-class slice: no ranking metric


def test_flag_notable_catches_gaps_and_ignores_small_slices():
    report = pd.DataFrame(
        {
            "family": ["purpose"] * 3,
            "slice": ["ok", "gapped", "tiny"],
            "loans": [5000, 5000, 50],
            "default_rate": [0.20, 0.20, 0.90],
            "mean_predicted": [0.21, 0.10, 0.10],
            "calibration_gap": [0.01, -0.10, -0.80],
            "pr_auc": [0.35, 0.34, 0.05],
            "brier": [0.1, 0.1, 0.5],
        }
    )
    flagged = flag_notable(report, overall_pr_auc=0.35)
    assert flagged["slice"].tolist() == ["gapped"]  # gap caught; tiny slice ignored
