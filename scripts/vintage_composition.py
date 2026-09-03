"""Vintage composition: originations, resolution rate, and default rate by issue month.

The R1 detection artifact (RISK_REGISTER): run BEFORE any modelling. Three panels,
shared time axis, split by term where rates are compared — never a dual axis.
Writes docs/figures/vintage_composition.png and prints the numbers the notes cite.

Run:  PYTHONPATH=src python scripts/vintage_composition.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from credit_default.ingest import INTERIM_ACCEPTED
from credit_default.labels import add_labels

OUT = Path("docs/figures/vintage_composition.png")

# dataviz reference palette, light mode: categorical slots 1-2 (validated pair)
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, MUTED, GRID = "#1a1a19", "#6b6a60", "#e6e4dc"
TRAIN_SPAN = (pd.Timestamp("2013-01-01"), pd.Timestamp("2016-01-01"))
REPLAY_SPAN = (pd.Timestamp("2016-01-01"), pd.Timestamp("2019-01-01"))


def monthly_stats() -> pd.DataFrame:
    df = add_labels(pd.read_parquet(INTERIM_ACCEPTED, columns=["issue_d", "term", "loan_status"]))
    df["month"] = df["issue_d"].dt.to_period("M").dt.to_timestamp()
    df["resolved"] = df["default"].notna()
    g = df.groupby(["month", "term"], observed=True)
    out = g.agg(
        total=("default", "size"),
        resolved=("resolved", "sum"),
        defaults=("default", lambda s: (s == 1).sum()),
    ).reset_index()
    out["resolution_rate"] = out["resolved"] / out["total"]
    out["default_rate"] = out["defaults"] / out["resolved"].where(out["resolved"] > 0)
    return out


def draw(stats: pd.DataFrame) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, dpi=150)
    fig.patch.set_facecolor("white")
    terms = {" 36 months": ("36-month", BLUE), " 60 months": ("60-month", ORANGE)}

    for ax in axes:
        ax.set_facecolor("white")
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=MUTED, labelsize=9)
        ax.axvspan(*TRAIN_SPAN, color=BLUE, alpha=0.05, zorder=0)
        ax.axvspan(*REPLAY_SPAN, color=ORANGE, alpha=0.05, zorder=0)

    # Panel 1: originations per month (single series -> no legend, title names it)
    vol = stats.groupby("month", as_index=False)["total"].sum()
    axes[0].fill_between(vol["month"], vol["total"], color=BLUE, alpha=0.25, linewidth=0)
    axes[0].plot(vol["month"], vol["total"], color=BLUE, linewidth=2)
    axes[0].set_title("Loans originated per month", loc="left", fontsize=11, color=INK)
    axes[0].set_ylim(bottom=0)

    # Panels 2-3: rates by term
    for ax, col, title, fmt in (
        (axes[1], "resolution_rate", "Share of loans with a terminal outcome (resolution rate)", "{:.0%}"),
        (axes[2], "default_rate", "Default rate among resolved loans", "{:.0%}"),
    ):
        # legend carries identity; end-of-line labels would collide where series converge
        for term, (label, color) in terms.items():
            d = stats[stats["term"] == term]
            ax.plot(d["month"], d[col], color=color, linewidth=2, label=label)
        ax.set_title(title, loc="left", fontsize=11, color=INK)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
        ax.set_ylim(0, 1.05 if col == "resolution_rate" else None)
        ax.legend(frameon=False, fontsize=9, labelcolor=MUTED, loc="lower left")

    axes[2].annotate("train window\n2013–2015", (pd.Timestamp("2014-06-01"), 0.02),
                     fontsize=8.5, color=MUTED, ha="center")
    axes[2].annotate("replay window\n2016–2018\n(labels immature)", (pd.Timestamp("2017-06-01"), 0.02),
                     fontsize=8.5, color=MUTED, ha="center")
    axes[2].xaxis.set_major_locator(mdates.YearLocator(2))
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    fig.suptitle("Vintage composition — accepted loans 2007–2018 (status snapshot: 2019)",
                 x=0.065, ha="left", fontsize=13, color=INK, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    print(f"wrote {OUT}")


def headline_numbers(stats: pd.DataFrame) -> None:
    for year in (2013, 2015, 2016, 2017, 2018):
        y = stats[stats["month"].dt.year == year]
        for term in (" 36 months", " 60 months"):
            t = y[y["term"] == term]
            if not len(t):
                continue
            res = t["resolved"].sum() / t["total"].sum()
            dr = t["defaults"].sum() / max(int(t["resolved"].sum()), 1)
            print(f"{year} {term.strip():>10}: resolved {res:6.1%}  default(among resolved) {dr:6.1%}")


if __name__ == "__main__":
    s = monthly_stats()
    draw(s)
    headline_numbers(s)
