"""Structured JSON logging with request-scoped IDs (ticket #48).

Two pieces:

- **A JSON formatter**, hand-rolled rather than pulling a dependency for ~30 lines.
  Every record becomes one JSON object per line — greppable by machines, which is
  the point once the replay (#50) generates hundreds of thousands of them.
- **A request-id ContextVar.** The middleware sets it once per request; every log
  call anywhere below inherits it without being passed it. That is what makes a
  single request traceable across middleware, validation, scoring and persistence.

Privacy note: request logs carry the loan id and the *names* of violated columns —
never the feature payload. The full payload lives in the prediction store, behind
database access; logs are the more widely-readable surface, so they get less.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

REQUEST_ID_HEADER = "X-Request-ID"

#: Set per request by the middleware; read by the formatter and by handlers.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

#: Keys the stdlib puts on every LogRecord — anything else is ours and gets emitted.
_STANDARD_FIELDS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        # structured extras: logger.info("scored", extra={"loan_id": ...})
        payload.update(
            {k: v for k, v in record.__dict__.items() if k not in _STANDARD_FIELDS}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """Route everything through one JSON handler on stdout (idempotent)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn's own access log is superseded by our middleware, which logs the same
    # request with more context (request id, duration, decision).
    logging.getLogger("uvicorn.access").disabled = True


def new_request_id() -> str:
    return str(uuid.uuid4())


def current_request_id() -> str | None:
    return request_id_var.get()
