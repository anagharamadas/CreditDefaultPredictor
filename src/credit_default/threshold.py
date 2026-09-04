"""Operating-threshold derivation from the ADR-0003 cost matrix (EVAL_PROTOCOL §5).

Written and frozen before any model output exists. P6 imports this — it does not
re-derive, and nothing here accepts a metric to "optimise": the threshold is an
economic consequence, not a tuning knob.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ADR-0003, [ASSUMED]: cost units are relative (FP = 1). See docs/adr/0003-cost-matrix.md.
COST_FN = 5.0
COST_FP = 1.0

# Sensitivity band from ADR-0003: FN:FP ratios whose thresholds P6 must report.
SENSITIVITY_RATIOS = (3.0, 4.0, 5.0, 6.0, 8.0)


def derive_threshold(cost_fn: float = COST_FN, cost_fp: float = COST_FP) -> float:
    """Cost-minimising decision threshold for calibrated probabilities.

    Decline when p(default) >= θ where θ = C_FP / (C_FP + C_FN): the point where the
    expected cost of funding (p * C_FN) equals the expected cost of declining
    ((1 - p) * C_FP).
    """
    if cost_fn <= 0 or cost_fp <= 0:
        raise ValueError("both error costs must be positive")
    return cost_fp / (cost_fp + cost_fn)


def sensitivity_table() -> pd.DataFrame:
    """The θ values P6 reports alongside every threshold-dependent metric."""
    rows = [
        {"fn_to_fp": r, "threshold": round(derive_threshold(r, 1.0), 4),
         "is_baseline": r == COST_FN}
        for r in SENSITIVITY_RATIOS
    ]
    return pd.DataFrame(rows)


def expected_cost_per_loan(
    y_true: pd.Series,
    y_prob: pd.Series,
    threshold: float | None = None,
    cost_fn: float = COST_FN,
    cost_fp: float = COST_FP,
) -> float:
    """Realised cost of decisions at θ, in FP-cost units per loan (P6's business metric).

    decline = y_prob >= θ. FN: funded (not declined) but defaulted. FP: declined but
    would have repaid. Inputs are converted to plain arrays first: two pandas Series
    with different indexes would otherwise silently align-to-nothing and count zero
    errors (found the hard way on the first real baseline run).
    """
    if threshold is None:
        threshold = derive_threshold(cost_fn, cost_fp)
    y = np.asarray(y_true)
    p = np.asarray(y_prob)
    decline = p >= threshold
    fn = int(((~decline) & (y == 1)).sum())
    fp = int((decline & (y == 0)).sum())
    return float(fn * cost_fn + fp * cost_fp) / len(y)


if __name__ == "__main__":
    print(f"baseline θ (FN:FP {COST_FN:g}:{COST_FP:g}) = {derive_threshold():.4f}")
    print(sensitivity_table().to_string(index=False))
