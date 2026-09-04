"""Temporal (vintage) splits with maturity arithmetic, per Charter §3.3.

No randomness anywhere: membership is a pure function of issue_d and term, so the
split is deterministic by construction — the anti-train_test_split. Boundaries are
justified by measurement (docs/VINTAGE_NOTES.md, docs/CLASS_BALANCE.md):

- TRAIN 2013-01..2015-12, 36-month, labelled-only: >=99.9% resolved (measured) —
  effectively zero censoring, and the maturity assertion below makes the arithmetic
  explicit rather than assumed.
- VALIDATION 2016-01..2016-06: model comparison/selection in P6.
- HOLDOUT 2016-07..2016-12: frozen at P3 (hashed manifest, ticket #24); first opened
  for the final P6 report.
- REPLAY 2017-01..2018-12: never used for selection; streamed month-by-month through
  the serving API in P10 under label lag.

Evaluation on 2016+ vintages is on partially-resolved populations (2016: ~72%
resolved at snapshot). The eval protocol (docs/EVAL_PROTOCOL.md) owns how coverage
is reported; this module only draws the boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from credit_default.labels import LABEL_COL, add_labels

V1_TERM = " 36 months"
TERM_MONTHS = 36
DATA_END = pd.Timestamp("2018-12-01")  # last observed issue month (measured)

TRAIN, VALIDATION, HOLDOUT, REPLAY, NONE = "train", "validation", "holdout", "replay", "none"
SPLIT_COL = "split"


TRAIN_START = pd.Timestamp("2013-01-01")
TRAIN_END = pd.Timestamp("2015-12-01")  # inclusive issue month
VALIDATION_END = pd.Timestamp("2016-06-01")
HOLDOUT_END = pd.Timestamp("2016-12-01")


@dataclass(frozen=True)
class SplitConfig:
    train_start: pd.Timestamp = TRAIN_START
    train_end: pd.Timestamp = TRAIN_END
    validation_end: pd.Timestamp = VALIDATION_END
    holdout_end: pd.Timestamp = HOLDOUT_END
    replay_end: pd.Timestamp = DATA_END

    def __post_init__(self) -> None:
        # The maturity gap, as arithmetic: every training loan must have been able to
        # run its full term inside the observed data window. 2015-12 + 36m = 2018-12
        # lands exactly on DATA_END — the train window is as recent as honesty allows.
        maturity = self.train_end + pd.DateOffset(months=TERM_MONTHS)
        if maturity > DATA_END + pd.DateOffset(months=0):
            raise ValueError(
                f"train_end {self.train_end:%Y-%m} + {TERM_MONTHS}m = {maturity:%Y-%m} "
                f"exceeds observed data end {DATA_END:%Y-%m}: training labels would be "
                "immature (right-censored). Move train_end earlier."
            )
        if not (self.train_start < self.train_end < self.validation_end
                < self.holdout_end < self.replay_end):
            raise ValueError("split boundaries must be strictly ordered")


DEFAULT_CONFIG = SplitConfig()


def assign_split(df: pd.DataFrame, config: SplitConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Append a `split` column. Pure date/term rules; no shuffling, no seed to get wrong.

    TRAIN additionally requires a terminal label (the measured 0.1% unresolved
    stragglers are excluded); evaluation splits keep unlabelled rows — coverage
    reporting is the eval protocol's job.
    """
    if LABEL_COL not in df.columns:
        df = add_labels(df)
    out = df.copy()

    month = out["issue_d"].values.astype("datetime64[M]").astype("datetime64[ns]")
    month = pd.Series(month, index=out.index)
    is_v1_term = out["term"].astype("string") == V1_TERM

    split = pd.Series(NONE, index=out.index, dtype="object")
    c = config
    in_train = is_v1_term & month.between(c.train_start, c.train_end) & out[LABEL_COL].notna()
    in_val = is_v1_term & (month > c.train_end) & (month <= c.validation_end)
    in_hold = is_v1_term & (month > c.validation_end) & (month <= c.holdout_end)
    in_replay = is_v1_term & (month > c.holdout_end) & (month <= c.replay_end)
    split[in_train], split[in_val] = TRAIN, VALIDATION
    split[in_hold], split[in_replay] = HOLDOUT, REPLAY

    out[SPLIT_COL] = pd.Categorical(split, categories=[TRAIN, VALIDATION, HOLDOUT, REPLAY, NONE])
    return out


def split_frame(df: pd.DataFrame, name: str, config: SplitConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Rows of one split (train/validation/holdout/replay)."""
    if SPLIT_COL not in df.columns:
        df = assign_split(df, config)
    return df.loc[df[SPLIT_COL] == name].copy()


def split_summary(df: pd.DataFrame, config: SplitConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """Counts, label coverage and default rate per split — the audit table."""
    if SPLIT_COL not in df.columns:
        df = assign_split(df, config)
    g = df.groupby(SPLIT_COL, observed=False)
    out = pd.DataFrame(
        {
            "loans": g.size(),
            "labelled": g[LABEL_COL].count(),
            "defaults": g[LABEL_COL].apply(lambda s: int((s == 1).sum())),
        }
    )
    out["label_coverage"] = (out["labelled"] / out["loans"]).round(4)
    out["default_rate_labelled"] = (out["defaults"] / out["labelled"]).round(4)
    return out


if __name__ == "__main__":
    from credit_default.ingest import INTERIM_ACCEPTED

    frame = pd.read_parquet(INTERIM_ACCEPTED, columns=["id", "issue_d", "term", "loan_status"])
    print(split_summary(frame).to_string())
