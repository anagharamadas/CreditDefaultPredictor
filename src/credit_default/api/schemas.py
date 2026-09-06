"""Request/response schemas, GENERATED from the same constants as ingest + contract.

Division of labour (deliberate, so nothing is typed twice to drift apart):
- pydantic (here): structure — field names, types, closed category sets, unknown
  fields forbidden. Fast, self-documenting 422s at the door.
- pandera (contract.py, applied in app.py): the numeric bounds and cross-column
  invariants — the SAME schema object training data passes through, minus the
  target column. The API cannot enforce a different contract than training did.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from credit_default.contract import (
    APPLICATION_TYPES,
    DISBURSEMENT_METHODS,
    EMP_LENGTHS,
    HOME_OWNERSHIP,
    PURPOSES,
    TERMS,
    US_STATES_DC,
    VERIFICATION,
)
from credit_default.ingest import ALLOWLIST, CATEGORICAL_COLS, DATE_COLS, STRING_COLS

CATEGORY_SETS = {
    "term": TERMS,
    "purpose": PURPOSES,
    "application_type": APPLICATION_TYPES,
    "emp_length": EMP_LENGTHS,
    "home_ownership": HOME_OWNERSHIP,
    "verification_status": VERIFICATION,
    "disbursement_method": DISBURSEMENT_METHODS,
    "addr_state": US_STATES_DC,
}
#: categoricals the contract allows to be null in a payload
NULLABLE_CATEGORICALS = {"emp_length"}
#: non-numeric optionality mirrors contract nullability
NULLABLE_OTHER = {"zip_code", "earliest_cr_line"}

PAYLOAD_COLUMNS = tuple(c for c in ALLOWLIST if c != "loan_status")


def _field(col: str):
    if col == "id":
        return (str, Field(pattern=r"^\d+$", description="loan application id"))
    if col in STRING_COLS:  # zip_code
        typ = (str | None) if col in NULLABLE_OTHER else str
        return (typ, Field(default=None, pattern=r"^\d{3}xx$"))
    if col in DATE_COLS:
        if col in NULLABLE_OTHER:
            return (date | None, Field(default=None))
        return (date, ...)
    if col in CATEGORICAL_COLS:
        literal = Literal[tuple(CATEGORY_SETS[col])]  # closed vocabulary -> 422 on unknown
        if col in NULLABLE_CATEGORICALS:
            return (literal | None, Field(default=None))
        return (literal, ...)
    # numeric: nullability is the contract's call — pandera decides after the door
    return (float | None, Field(default=None))


LoanApplication = create_model(
    "LoanApplication",
    __config__=ConfigDict(extra="forbid"),  # an unexpected field is a violation, as everywhere
    **{col: _field(col) for col in PAYLOAD_COLUMNS},
)


class ScoreResponse(BaseModel):
    id: str
    p_default: float
    decision: Literal["fund", "decline"]
    threshold: float
    cost_ratio_assumed: str
    model_name: str
    model_version: int
    scored_at: datetime


class ReadyResponse(BaseModel):
    ready: bool
    model_name: str | None = None
    model_version: int | None = None
    detail: str | None = None
