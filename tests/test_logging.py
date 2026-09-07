"""Structured logging: JSON shape, request-id propagation, and the privacy rule."""

import json
import logging
from io import StringIO

import pytest
from fastapi.testclient import TestClient
from tests.test_api import stub_loader

from credit_default.api import create_app
from credit_default.api.logging_config import (
    REQUEST_ID_HEADER,
    JsonFormatter,
    request_id_var,
)
from credit_default.features.serving import frame_to_payloads
from credit_default.ingest import read_accepted


@pytest.fixture(scope="module")
def payload():
    fixture = read_accepted("tests/fixtures/parity_sample.csv", strict=False)
    return frame_to_payloads(fixture.head(1))[0]


@pytest.fixture()
def captured_logs():
    """Attach the JSON formatter to a buffer and return a parsed-lines reader."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    previous, previous_level = root.handlers, root.level
    root.handlers, root.level = [handler], logging.INFO
    def read(app_only: bool = True):
        lines = [json.loads(line) for line in stream.getvalue().splitlines() if line]
        # Third-party loggers (httpx inside TestClient) emit outside the request
        # context and legitimately carry no request id; assert on our own lines.
        return [x for x in lines if x["logger"].startswith("credit_default")] if app_only else lines

    yield read
    root.handlers, root.level = previous, previous_level


@pytest.fixture()
def client():
    with TestClient(create_app(model_loader=stub_loader, store_opener=None)) as c:
        yield c


def test_formatter_emits_one_json_object_with_extras():
    record = logging.LogRecord(
        "t", logging.INFO, "f.py", 1, "scored", None, None
    )
    record.loan_id = "123"
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["message"] == "scored"
    assert parsed["level"] == "INFO"
    assert parsed["loan_id"] == "123"          # structured extras survive
    assert "request_id" not in parsed           # none set outside a request


def test_formatter_picks_up_the_context_request_id():
    token = request_id_var.set("abc-123")
    try:
        record = logging.LogRecord("t", logging.INFO, "f.py", 1, "x", None, None)
        assert json.loads(JsonFormatter().format(record))["request_id"] == "abc-123"
    finally:
        request_id_var.reset(token)


def test_supplied_request_id_is_echoed_and_logged(client, payload, captured_logs):
    response = client.post("/score", json=payload, headers={REQUEST_ID_HEADER: "caller-42"})
    assert response.headers[REQUEST_ID_HEADER] == "caller-42"

    lines = captured_logs()
    assert lines, "expected structured log output"
    assert all(line["request_id"] == "caller-42" for line in lines)
    # both the decision and the completion line carry it — the whole request traced
    assert {"decision", "request completed"} <= {line["message"] for line in lines}


def test_request_id_is_generated_when_absent(client, payload):
    a = client.post("/score", json=payload).headers[REQUEST_ID_HEADER]
    b = client.post("/score", json=payload).headers[REQUEST_ID_HEADER]
    assert a and b and a != b  # one per request, not one per process


def test_decision_line_carries_the_audit_fields(client, payload, captured_logs):
    client.post("/score", json=payload)
    decision = next(line for line in captured_logs() if line["message"] == "decision")
    assert decision["decision"] in {"fund", "decline"}
    assert decision["loan_id"] == payload["id"]
    assert decision["model_version"] == 7
    assert "p_default" in decision and "threshold" in decision


def test_rejections_log_column_names_but_never_the_payload(client, payload, captured_logs):
    response = client.post("/score", json=payload | {"loan_amnt": 999_999.0})
    assert response.status_code == 422

    rejection = next(
        line for line in captured_logs() if line["message"].startswith("payload rejected")
    )
    assert rejection["violated_columns"] == ["loan_amnt"]
    # the privacy rule: feature values never reach the log stream
    assert "999999" not in json.dumps(rejection)
    assert "annual_inc" not in rejection
