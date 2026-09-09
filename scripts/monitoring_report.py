"""Monitoring report (ticket #58): drift, performance and coverage in one place.

Reads what the LIVE service produced during the replay (from the prediction store),
compares it against the training reference, and writes docs/MONITORING_REPORT.md plus
the figures. Everything here is measured; nothing is injected.

Run:  PYTHONPATH=src python scripts/monitoring_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from credit_default.drift import (
    calibrate_thresholds,
    drift_table,
    evaluate_against_thresholds,
    psi,
)
from credit_default.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from credit_default.ingest import INTERIM_ACCEPTED
from credit_default.label_lag import (
    load_outcome_timing,
    load_replay_predictions,
    performance_by_month,
)
from credit_default.splits import TRAIN, assign_split, split_frame

DOC = Path("docs/MONITORING_REPORT.md")
FIGURE = Path("docs/figures/monitoring.png")
HORIZON_MONTHS = 12
QUIET_MONTHS = ["2015-01", "2015-04", "2015-07", "2015-10"]

# dataviz reference palette (light mode), used consistently across the project
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1a1a19", "#6b6a60", "#e6e4dc"


def load_replay_features() -> pd.DataFrame:
    """Feature payloads as the service received them, from the store's JSONB."""
    from credit_default.store import open_pool

    pool = open_pool()
    try:
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT to_char(issue_d, 'YYYY-MM') AS month, features, p_default"
                " FROM predictions WHERE source = 'replay'"
            ).fetchall()
    finally:
        pool.close()
    if not rows:
        raise SystemExit("no replay rows in the store — run credit_default.replay first")
    frame = pd.DataFrame(
        [{"month": m, "p_default": p, **(f if isinstance(f, dict) else json.loads(f))}
         for m, f, p in rows]
    )
    return frame


def build_report() -> None:
    print("loading training reference…")
    train = split_frame(assign_split(pd.read_parquet(INTERIM_ACCEPTED)), TRAIN)
    train = train.assign(month=train["issue_d"].dt.to_period("M").astype(str))

    print("deriving alert thresholds from the quiet period…")
    thresholds = calibrate_thresholds(
        train,
        {m: train[train["month"] == m] for m in QUIET_MONTHS},
        NUMERIC_FEATURES,
        CATEGORICAL_FEATURES,
    )
    print(f"  {thresholds.attrs['basis']}")
    print(f"  per-feature alerts span PSI {thresholds['psi_alert'].min():.4f} "
          f"to {thresholds['psi_alert'].max():.4f}")

    print("loading replayed predictions from the store…")
    replayed = load_replay_features()
    months = sorted(replayed["month"].unique())
    print(f"  {len(replayed):,} predictions across {len(months)} months")

    print("computing feature drift per month…")
    train_scores = _train_scores(train)
    per_month, alarm_detail = [], []
    for month in months:
        current = replayed[replayed["month"] == month]
        table = drift_table(train, current, NUMERIC_FEATURES, CATEGORICAL_FEATURES)
        judged = evaluate_against_thresholds(table, thresholds)
        alarming = judged[judged["psi_alarm"]]
        alarm_detail.append(judged.assign(month=month).head(5))
        per_month.append(
            {
                "month": month,
                "loans": len(current),
                "max_psi": round(float(table["psi"].max()), 4),
                # measured against EACH feature's own noise floor, so this counts
                # features that moved more than they ever did while stable
                "features_alerting": len(alarming),
                "worst_feature": judged.iloc[0]["feature"],
                "worst_vs_own_floor": judged.iloc[0]["psi_ratio"],
                "prediction_psi": round(psi(train_scores, current["p_default"]), 4),
            }
        )
    drift_summary = pd.DataFrame(per_month)
    alarms = pd.concat(alarm_detail, ignore_index=True)

    print("computing performance under label lag…")
    predictions = load_replay_predictions()
    timing = load_outcome_timing()
    naive = performance_by_month(predictions, timing, None)
    fixed = performance_by_month(predictions, timing, HORIZON_MONTHS)

    _draw(drift_summary, naive, fixed, thresholds)
    _write_markdown(drift_summary, naive, fixed, thresholds, len(replayed), alarms)
    print(f"wrote {DOC} and {FIGURE}")


def _train_scores(train: pd.DataFrame) -> pd.Series:
    """Champion scores on the training window — the prediction-drift reference."""
    from credit_default.registry import load

    cached = Path("data/interim/train_scores.parquet")
    if cached.exists():
        return pd.read_parquet(cached)["p_default"]
    model = load("champion")
    scores = model.predict_proba(train.drop(columns=["loan_status", "default", "exclusion_reason", "split", "month"]))[:, 1]
    pd.DataFrame({"p_default": scores}).to_parquet(cached)
    return pd.Series(scores)


def _draw(drift_summary, naive, fixed, thresholds) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, dpi=150)
    fig.patch.set_facecolor("white")
    x = pd.to_datetime(drift_summary["month"])

    for ax in axes:
        ax.set_facecolor("white")
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=MUTED, labelsize=9)

    axes[0].plot(x, drift_summary["max_psi"], color=BLUE, linewidth=2, label="worst feature PSI")
    axes[0].plot(x, drift_summary["prediction_psi"], color=ORANGE, linewidth=2, label="prediction PSI")
    axes[0].set_title(
        "Drift vs the training reference (each feature judged against its own floor)",
        loc="left", fontsize=11, color=INK,
    )
    axes[0].legend(frameon=False, fontsize=9, labelcolor=MUTED, loc="upper left")

    for frame, colour, label in ((naive, BLUE, "as observed"), (fixed, ORANGE, f"{HORIZON_MONTHS}-month horizon")):
        d = frame.dropna(subset=["pr_auc"])
        axes[1].plot(pd.to_datetime(d["issue_month"]), d["pr_auc"], color=colour, linewidth=2, label=label)
    axes[1].set_title("PR-AUC — the same months, two ways of looking", loc="left", fontsize=11, color=INK)
    axes[1].legend(frameon=False, fontsize=9, labelcolor=MUTED, loc="lower left")

    for frame, colour, label in ((naive, BLUE, "as observed"), (fixed, ORANGE, f"{HORIZON_MONTHS}-month horizon")):
        axes[2].plot(pd.to_datetime(frame["issue_month"]), frame["coverage"], color=colour, linewidth=2, label=label)
    axes[2].set_title("Label coverage — the fraction that can be evaluated at all", loc="left", fontsize=11, color=INK)
    axes[2].yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    axes[2].legend(frameon=False, fontsize=9, labelcolor=MUTED, loc="upper right")
    axes[2].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    fig.suptitle("Replay monitoring — 2017–2018 scored through the live service",
                 x=0.065, ha="left", fontsize=13, color=INK, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE, bbox_inches="tight", facecolor="white")


def _write_markdown(drift_summary, naive, fixed, thresholds, n_predictions, alarms) -> None:
    lines = [
        "# Monitoring report — replayed 2017–2018",
        "",
        "GENERATED by `scripts/monitoring_report.py`. Every number here comes from",
        "predictions the **live service** produced during the replay and stored in",
        "Postgres — not from an offline recomputation.",
        "",
        f"Predictions analysed: **{n_predictions:,}** across {len(drift_summary)} vintage months.",
        "",
        "## Alert thresholds, derived rather than adopted",
        "",
        f"- Basis: {thresholds.attrs['basis']}",
        (
            f"- Quiet months used: {', '.join(thresholds.attrs['quiet_months'])}, "
            f"scaled by {thresholds.attrs['safety_factor']}×."
        ),
        "",
        "The published 0.1/0.25 PSI bands are conventions. EVAL_PROTOCOL forbids alert",
        "levels copied from a default, so each alarm is set above anything **that",
        "feature** produced while this dataset was demonstrably stable.",
        "",
        "Thresholds are per feature because features are not equally noisy: the quiet",
        "period moved `mths_since_last_record` (84% null, small non-null sample) by",
        "PSI 0.17 while well-populated features stayed near 0.005. One global number",
        "high enough to ignore the first would be deaf to a real move in the second.",
        "",
        "Noisiest and quietest five, by derived alert level:",
        "",
        pd.concat([thresholds.head(5), thresholds.tail(5)])[
            ["feature", "kind", "quiet_max_psi", "psi_alert"]
        ].to_markdown(index=False),
        "",
        "## Feature and prediction drift",
        "",
        drift_summary.to_markdown(index=False),
        "",
        "`worst_vs_own_floor` is PSI divided by that feature's alert level — a value",
        "above 1 means the feature moved further than it ever did while stable, and it",
        "is comparable across features in a way raw PSI is not.",
        "",
        "### Worst offenders by month",
        "",
        alarms[alarms["psi_alarm"]][
            ["month", "feature", "psi", "psi_alert", "psi_ratio"]
        ].head(20).to_markdown(index=False)
        if alarms["psi_alarm"].any()
        else "*No feature exceeded its own noise floor in any replayed month.*",
        "",
        "## Performance under label lag",
        "",
        "Two views of the same months. `as-observed` evaluates every loan resolved by",
        f"the data snapshot; `{HORIZON_MONTHS}-month` evaluates only outcomes visible",
        f"within {HORIZON_MONTHS} months of issue, so each vintage is judged on an equal",
        "window. Where they disagree, the as-observed number is reporting the passage of",
        "time as if it were a change in the model.",
        "",
        "### As observed",
        "",
        naive.to_markdown(index=False),
        "",
        f"### Fixed {HORIZON_MONTHS}-month horizon",
        "",
        fixed.to_markdown(index=False),
        "",
        "![monitoring](figures/monitoring.png)",
    ]
    DOC.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    build_report()
