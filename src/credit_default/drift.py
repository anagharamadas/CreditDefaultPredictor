"""Feature and prediction drift (ticket #56, method fixed by ADR-0005).

Two statistics, both implemented here rather than imported, both tested against
hand-computed cases:

- **PSI** (population stability index), the credit-risk convention:
  `sum (a_i - e_i) * ln(a_i / e_i)` over bins, where e and a are the reference and
  current *proportions*. Symmetric, unbounded, and sensitive to shifts anywhere in
  the distribution. Works for categoricals directly, using categories as bins.
- **KS**, the largest gap between two empirical CDFs. Bounded in [0, 1] and
  distribution-free. We use the *statistic* only, never its p-value: at 27,000 loans
  a month, every difference is "significant" and the p-value stops carrying
  information.

**Where the numbers come from.** The current distribution is read back from the
PREDICTION STORE, not recomputed from the parquet — so what is measured is what the
live service actually received and scored. Recomputing offline would be easier and
would be measuring a different thing.

**Thresholds are derived, not adopted.** The published PSI bands (0.1 / 0.25) are
conventions, and EVAL_PROTOCOL forbids alert thresholds copied from a default. So the
alert level is calibrated against this dataset's own quiet period: PSI is computed
between the training reference and each *training* month, where by construction the
model is not drifting. Whatever range that produces is the noise floor, and the alert
sits above it. See `calibrate_thresholds`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: proportions below this are floored so a zero bin cannot make PSI infinite; small
#: enough not to move a real result, large enough to keep the statistic finite
EPSILON = 1e-6
DEFAULT_BINS = 10

#: floor for a feature that never moved while stable, so its ratio stays finite
MIN_ALERT = 0.01


def _proportions(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    counts, _ = np.histogram(values, bins=edges)
    proportions = counts / max(counts.sum(), 1)
    return np.clip(proportions, EPSILON, None)


def quantile_edges(reference: pd.Series, bins: int = DEFAULT_BINS) -> np.ndarray:
    """Bin edges from the REFERENCE distribution's quantiles, with open ends.

    Quantile bins (rather than equal width) keep every reference bin populated, which
    is what stops PSI exploding on a skewed feature like `annual_inc`.
    """
    clean = pd.to_numeric(reference, errors="coerce").dropna()
    edges = np.unique(np.quantile(clean, np.linspace(0, 1, bins + 1)))
    if len(edges) < 2:  # a constant feature has no distribution to drift
        return np.array([-np.inf, np.inf])
    edges[0], edges[-1] = -np.inf, np.inf
    return edges


def psi(reference: pd.Series, current: pd.Series, bins: int = DEFAULT_BINS) -> float:
    """PSI for a numeric feature. 0 = identical; larger = more shifted.

    Low-cardinality features fall back to treating each value as its own bin. Two
    reasons: quantile edges collapse when there are fewer distinct values than bins,
    and — the reason it matters — a *constant* reference would otherwise put every
    observation in one bin and report PSI 0, i.e. "no drift", for a feature that had
    moved entirely. Silently reporting no-drift for something we cannot measure is
    worse than the measurement being unavailable. Many bureau counts here are
    genuinely low-cardinality (`pub_rec`, `num_tl_30dpd`), so this path is also the
    more accurate one for them.
    """
    ref = pd.to_numeric(reference, errors="coerce").dropna()
    cur = pd.to_numeric(current, errors="coerce").dropna()
    if len(ref) == 0 or len(cur) == 0:
        return float("nan")
    if ref.nunique() <= bins:
        return psi_categorical(ref, cur)
    edges = quantile_edges(ref, bins)
    e, a = _proportions(ref.to_numpy(), edges), _proportions(cur.to_numpy(), edges)
    return float(np.sum((a - e) * np.log(a / e)))


def psi_categorical(reference: pd.Series, current: pd.Series) -> float:
    """PSI over categories — no binning needed, categories ARE the bins.

    Unseen categories are kept (they are exactly the kind of shift worth alerting on)
    and floored by EPSILON so they contribute without becoming infinite.
    """
    ref = reference.dropna().astype(str)
    cur = current.dropna().astype(str)
    if ref.empty or cur.empty:
        return float("nan")
    categories = sorted(set(ref) | set(cur))
    e = np.clip(ref.value_counts(normalize=True).reindex(categories).fillna(0).to_numpy(), EPSILON, None)
    a = np.clip(cur.value_counts(normalize=True).reindex(categories).fillna(0).to_numpy(), EPSILON, None)
    return float(np.sum((a - e) * np.log(a / e)))


def ks_statistic(reference: pd.Series, current: pd.Series) -> float:
    """Largest gap between the two empirical CDFs, in [0, 1].

    Statistic only. At tens of thousands of loans a month the p-value is always
    tiny and says nothing about whether the difference matters.
    """
    ref = np.sort(pd.to_numeric(reference, errors="coerce").dropna().to_numpy())
    cur = np.sort(pd.to_numeric(current, errors="coerce").dropna().to_numpy())
    if len(ref) == 0 or len(cur) == 0:
        return float("nan")
    grid = np.concatenate([ref, cur])
    cdf_ref = np.searchsorted(ref, grid, side="right") / len(ref)
    cdf_cur = np.searchsorted(cur, grid, side="right") / len(cur)
    return float(np.max(np.abs(cdf_ref - cdf_cur)))


def drift_table(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    numeric_features: list[str],
    categorical_features: list[str],
) -> pd.DataFrame:
    """One row per feature: PSI, and KS where the feature is numeric."""
    rows = []
    for column in numeric_features:
        if column not in current:
            continue
        rows.append(
            {
                "feature": column,
                "kind": "numeric",
                "psi": psi(reference[column], current[column]),
                "ks": ks_statistic(reference[column], current[column]),
            }
        )
    for column in categorical_features:
        if column not in current:
            continue
        rows.append(
            {
                "feature": column,
                "kind": "categorical",
                "psi": psi_categorical(reference[column], current[column]),
                "ks": float("nan"),  # undefined for unordered categories
            }
        )
    return pd.DataFrame(rows).sort_values("psi", ascending=False).reset_index(drop=True)


def calibrate_thresholds(
    reference: pd.DataFrame,
    quiet_periods: dict[str, pd.DataFrame],
    numeric_features: list[str],
    categorical_features: list[str],
    safety_factor: float = 2.0,
) -> pd.DataFrame:
    """Derive a PER-FEATURE alert level from the dataset's own quiet period.

    `quiet_periods` are month slices from INSIDE the training window, where the model
    is not drifting by construction. Whatever PSI/KS a feature produces there is *that
    feature's* natural month-to-month variation, and its alarm sits at `safety_factor`
    times its own worst quiet value.

    Per feature, not one global number, because features are not equally noisy. On
    this data the quiet period produced PSI 0.175 for `mths_since_last_record` — a
    feature that is 84% null, so its non-null sample is small and jumpy — while
    well-populated features like `loan_amnt` stayed near 0.005. A single global
    threshold set high enough not to cry wolf about the first would be far too deaf
    to ever notice the second.

    Returns one row per feature: its quiet maximum and its alert level.
    """
    observed = [
        drift_table(reference, frame, numeric_features, categorical_features).assign(month=month)
        for month, frame in quiet_periods.items()
    ]
    if not observed:
        raise ValueError("need at least one quiet-period month to calibrate against")

    combined = pd.concat(observed)
    quiet = (
        combined.groupby(["feature", "kind"], as_index=False)
        .agg(quiet_max_psi=("psi", "max"), quiet_max_ks=("ks", "max"))
    )
    # round the observed maxima FIRST so the published table is internally
    # consistent: alert == quiet maximum x safety factor at displayed precision
    quiet["quiet_max_psi"] = quiet["quiet_max_psi"].round(4)
    quiet["quiet_max_ks"] = quiet["quiet_max_ks"].round(4)
    quiet["psi_alert"] = (quiet["quiet_max_psi"] * safety_factor).round(4)
    quiet["ks_alert"] = (quiet["quiet_max_ks"] * safety_factor).round(4)
    quiet.attrs["safety_factor"] = safety_factor
    quiet.attrs["quiet_months"] = sorted(quiet_periods)
    quiet.attrs["basis"] = (
        "each feature's alert is the worst PSI/KS it produced between the training "
        "reference and individual training months, scaled by the safety factor — "
        "i.e. larger than that feature ever moved while this dataset was stable"
    )
    return quiet.sort_values("psi_alert", ascending=False).reset_index(drop=True)


def evaluate_against_thresholds(
    drift: pd.DataFrame, thresholds: pd.DataFrame
) -> pd.DataFrame:
    """Join measured drift to each feature's own alert level and flag breaches."""
    merged = drift.merge(
        thresholds[["feature", "psi_alert", "ks_alert", "quiet_max_psi"]],
        on="feature",
        how="left",
    )
    merged["psi_alarm"] = merged["psi"] > merged["psi_alert"]
    merged["ks_alarm"] = merged["ks"] > merged["ks_alert"]
    # A feature that never varied during the quiet period gets a zero threshold, so
    # any movement at all divides by zero. Flag it instead: "did something it has
    # never done" is a different KIND of finding from "moved more than usual", and
    # deserves to be named rather than rendered as inf.
    merged["never_varied_in_training"] = merged["quiet_max_psi"] == 0
    floor = merged["psi_alert"].where(merged["psi_alert"] > 0, MIN_ALERT)
    merged["psi_ratio"] = (merged["psi"] / floor).round(2)
    return merged.sort_values("psi_ratio", ascending=False).reset_index(drop=True)
