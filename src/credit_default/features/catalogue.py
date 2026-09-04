"""Feature catalogue renderer: docs/FEATURE_CATALOGUE.md from the pipeline's own groups.

The catalogue answers, per feature: what is it, where does it come from, what
transform touches it, and why is it knowable at application time. Name/source/
justification come from the ledger (single source of truth); transform facts come
from the pipeline module. A test asserts the committed document equals this
renderer's output, so the catalogue cannot drift from the code.

Status: STARTED at ticket #29 (skeleton transforms); FINALISED at #32 when the
transform decisions (scaling, zip encoding, dti clipping) land in #30.
"""

from __future__ import annotations

from credit_default.contract import (
    APPLICATION_TYPES,
    DISBURSEMENT_METHODS,
    EMP_LENGTHS,
    HOME_OWNERSHIP,
    PURPOSES,
    US_STATES_DC,
    VERIFICATION,
)
from credit_default.features.pipeline import (
    CATEGORICAL_FEATURES,
    ENGINEERED,
    EXCLUDED_FROM_MATRIX,
    NUMERIC_FEATURES,
)
from credit_default.ledger import LEDGER

CATEGORY_SETS = {
    "purpose": PURPOSES,
    "application_type": APPLICATION_TYPES,
    "emp_length": EMP_LENGTHS,
    "home_ownership": HOME_OWNERSHIP,
    "verification_status": VERIFICATION,
    "disbursement_method": DISBURSEMENT_METHODS,
    "addr_state": US_STATES_DC,
}

NUMERIC_TRANSFORM = (
    "median impute + missing-indicator columns (a meaningful null stays visible to the "
    "model) -> standardise. Medians, indicator set, means and variances are all learned "
    "on the training split only — enforced by the pipeline's train-window gate"
)
CATEGORICAL_TRANSFORM = (
    'impute constant "missing" -> one-hot (categories learned on the training split; '
    "unknown values at serving time encode as all-zeros, never an error)"
)


def render_markdown() -> str:
    lines = [
        "# Feature Catalogue",
        "",
        "GENERATED from `src/credit_default/features/catalogue.py` — edit code, rerun",
        "`scripts/render_feature_catalogue.py`. A test asserts this file matches the code.",
        "",
        "Status: transforms FINALISED (#30): scaling on the numeric branch, zip_code",
        "frequency-encoded, dti clipped to [0, 100], missing-indicator columns added,",
        "and fit-on-training-window enforced by a gate that raises otherwise.",
        "",
        (
            f"Matrix composition: {len(NUMERIC_FEATURES)} numeric + {len(ENGINEERED)} "
            f"engineered + one-hot expansions of {len(CATEGORICAL_FEATURES)} categoricals. "
            "Every feature's application-time justification is inherited verbatim from the "
            "leakage ledger; a column without a FEATURE verdict there cannot appear here."
        ),
        "",
        "## Engineered features",
        "",
        "| Feature | Definition | Source columns | Transform | Application-time justification |",
        "|---|---|---|---|---|",
        (
            "| `credit_history_months` | Age of the credit file at application, in months "
            "| `issue_d`, `earliest_cr_line` | (issue year-month − earliest year-month); "
            "then the numeric branch | Both dates are on the application; the difference is "
            "known the moment it is submitted. `issue_d` itself is never a feature "
            "(METADATA: calendar time would not transfer to serving). |"
        ),
        (
            "| `zip_code_freq` | Share of training loans in the applicant's masked "
            "3-digit zip | `zip_code` | frequency encoding learned on the training "
            "split; unknown zips at serving time -> 0.0 | On the application; encoding "
            "replaces 956 one-hots with one column. Target encoding rejected as "
            "leak-prone. Geographic proxy: fairness-slice obligation (R7). |"
        ),
        (
            "| `dti` (treatment) | Raw dti clipped to [0, 100] before the numeric branch "
            "| `dti` | clip, then the numeric branch | Measured raw range is -1..999 with "
            "sentinel-like extremes (SCHEMA.md); beyond 100 carries no credible ratio "
            "information. |"
        ),
        "",
        f"## Categorical features ({len(CATEGORICAL_FEATURES)})",
        "",
        f"Transform, all rows: {CATEGORICAL_TRANSFORM}.",
        "",
        "| Feature | Values | Application-time justification (ledger) |",
        "|---|---|---|",
    ]
    for col in CATEGORICAL_FEATURES:
        n = len(CATEGORY_SETS[col])
        lines.append(f"| `{col}` | {n} categories | {LEDGER[col][1]} |")

    lines += [
        "",
        f"## Numeric features ({len(NUMERIC_FEATURES)})",
        "",
        f"Transform, all rows: {NUMERIC_TRANSFORM}. Bounds enforced upstream by the",
        "data contract (`docs/DATA_CONTRACT.md`); meaningful nulls are imputed, and",
        "whether null-indicator columns should be added is a #30 decision.",
        "",
        "| Feature | Application-time justification (ledger) |",
        "|---|---|",
    ]
    for col in NUMERIC_FEATURES:
        lines.append(f"| `{col}` | {LEDGER[col][1]} |")

    lines += [
        "",
        "## FEATURE columns deliberately not in the v1 matrix",
        "",
        "Ledger verdict FEATURE (legitimate), excluded by pipeline scope decision:",
        "",
        "| Column | Reason |",
        "|---|---|",
    ]
    for col, reason in EXCLUDED_FROM_MATRIX.items():
        lines.append(f"| `{col}` | {reason} |")
    lines.append("")
    return "\n".join(lines)
