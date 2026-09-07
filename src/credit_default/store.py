"""Prediction store (ticket #47): every scored decision, persisted.

This table is not a log — it is the substrate P10 replays and P11 retrains from,
so the schema is designed for those consumers now rather than retrofitted later:

- **`issue_d` is stored separately from `scored_at`.** Replaying 2016-2018 through
  the API in one afternoon makes every `scored_at` "today"; the loan's own vintage
  is the axis drift is measured along. Without this column the replay is unreadable.
- **`features` is JSONB, not 84 columns.** Feature-set changes (v2 joint-applicant
  support, an NLP field) then need no migration, and drift can be computed on any
  feature that was actually sent. At this scale the query cost is irrelevant.
- **No label column, deliberately.** Outcomes arrive months-to-years after the
  decision; they live on the loan side and are joined at analysis time. A label
  column here would invite writing an outcome next to a prediction as if both were
  known at once — the exact confusion the whole project is built to avoid.
- **The decision policy in force is stored** (`threshold`, `cost_ratio`), so a past
  decision can be audited against the assumptions it was made under — which matters
  because the cost ratio is [ASSUMED] and under review (issue #70).

Write policy: **mandatory**. If the store is unreachable the request fails; a credit
decision that cannot be recorded is not made. This matches the project's posture
elsewhere (training refuses to run untracked, runs refuse to start untraceable).
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime

from psycopg_pool import ConnectionPool

DEFAULT_DSN = "postgresql://credit:local-dev-only@localhost:5432/predictions"

#: Indexes exist for the consumers, not for tidiness:
#: issue_d      -> P10 groups drift by vintage month
#: scored_at    -> operational queries ("what did we serve today")
#: loan_id      -> P11 joins predictions to outcomes as loans mature
#: model_version-> incumbent-vs-candidate comparisons
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id  UUID PRIMARY KEY,
    request_id     TEXT        NOT NULL,
    loan_id        TEXT        NOT NULL,
    scored_at      TIMESTAMPTZ NOT NULL,
    issue_d        DATE        NOT NULL,
    model_name     TEXT        NOT NULL,
    model_version  INTEGER     NOT NULL,
    p_default      DOUBLE PRECISION NOT NULL,
    decision       TEXT        NOT NULL CHECK (decision IN ('fund', 'decline')),
    threshold      DOUBLE PRECISION NOT NULL,
    cost_ratio     TEXT        NOT NULL,
    source         TEXT        NOT NULL DEFAULT 'live',
    features       JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS predictions_issue_d_idx       ON predictions (issue_d);
CREATE INDEX IF NOT EXISTS predictions_scored_at_idx     ON predictions (scored_at);
CREATE INDEX IF NOT EXISTS predictions_loan_id_idx       ON predictions (loan_id);
CREATE INDEX IF NOT EXISTS predictions_model_version_idx ON predictions (model_version);
"""

INSERT_SQL = """
INSERT INTO predictions (
    prediction_id, request_id, loan_id, scored_at, issue_d, model_name,
    model_version, p_default, decision, threshold, cost_ratio, source, features
) VALUES (
    %(prediction_id)s, %(request_id)s, %(loan_id)s, %(scored_at)s, %(issue_d)s,
    %(model_name)s, %(model_version)s, %(p_default)s, %(decision)s, %(threshold)s,
    %(cost_ratio)s, %(source)s, %(features)s
)
"""


@dataclass(frozen=True)
class PredictionRecord:
    prediction_id: str
    request_id: str
    loan_id: str
    scored_at: datetime
    issue_d: date
    model_name: str
    model_version: int
    p_default: float
    decision: str
    threshold: float
    cost_ratio: str
    source: str
    features: dict


def dsn() -> str:
    """Connection string; DATABASE_URL in compose, a local default otherwise."""
    return os.environ.get("DATABASE_URL", DEFAULT_DSN)


def build_record(
    *,
    payload: dict,
    p_default: float,
    decision: str,
    threshold: float,
    cost_ratio: str,
    model_name: str,
    model_version: int,
    scored_at: datetime,
    request_id: str | None = None,
    source: str = "live",
) -> PredictionRecord:
    """Assemble the row from a validated payload and its decision (pure, testable).

    The full payload is stored as sent (post-validation), so a later drift analysis
    sees exactly what the model saw.
    """
    return PredictionRecord(
        prediction_id=str(uuid.uuid4()),
        request_id=request_id or str(uuid.uuid4()),
        loan_id=str(payload["id"]),
        scored_at=scored_at,
        issue_d=date.fromisoformat(str(payload["issue_d"])),
        model_name=model_name,
        model_version=int(model_version),
        p_default=float(p_default),
        decision=decision,
        threshold=float(threshold),
        cost_ratio=cost_ratio,
        source=source,
        features=payload,
    )


def open_pool(conninfo: str | None = None, **kwargs) -> ConnectionPool:
    pool = ConnectionPool(conninfo or dsn(), min_size=1, max_size=4, open=True, **kwargs)
    pool.wait(timeout=30)
    return pool


def init_schema(pool: ConnectionPool) -> None:
    """Idempotent DDL. Called at API startup so the stack is self-installing."""
    with pool.connection() as conn:
        conn.execute(SCHEMA_SQL)


def persist(pool: ConnectionPool, record: PredictionRecord) -> None:
    """Write one decision. Raises on failure — see the module's write policy."""
    params = asdict(record) | {"features": json.dumps(record.features)}
    with pool.connection() as conn:
        conn.execute(INSERT_SQL, params)


def count(pool: ConnectionPool) -> int:
    with pool.connection() as conn:
        return int(conn.execute("SELECT count(*) FROM predictions").fetchone()[0])
