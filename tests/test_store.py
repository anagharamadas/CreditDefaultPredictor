"""Prediction store: record assembly (pure) + a live round trip (services-marked)."""

from datetime import UTC, datetime

import pytest

from credit_default.features.serving import frame_to_payloads
from credit_default.ingest import read_accepted
from credit_default.store import build_record


@pytest.fixture(scope="module")
def payload():
    fixture = read_accepted("tests/fixtures/parity_sample.csv", strict=False)
    return frame_to_payloads(fixture.head(1))[0]


def _record(payload, **overrides):
    defaults = {
        "payload": payload,
        "p_default": 0.42,
        "decision": "decline",
        "threshold": 1 / 6,
        "cost_ratio": "5:1 (ADR-0003 [ASSUMED])",
        "model_name": "credit-default-granting",
        "model_version": 1,
        "scored_at": datetime(2026, 9, 7, 12, 0, tzinfo=UTC),
    }
    return build_record(**(defaults | overrides))


def test_record_separates_scoring_time_from_loan_vintage(payload):
    """The distinction the replay depends on: when we scored vs when the loan was issued."""
    record = _record(payload)
    assert record.scored_at.year == 2026          # wall clock
    assert record.issue_d.year in range(2013, 2016)  # the loan's own vintage
    assert str(record.issue_d) == payload["issue_d"]


def test_record_carries_the_decision_policy_in_force(payload):
    record = _record(payload)
    assert record.threshold == pytest.approx(1 / 6)
    assert "[ASSUMED]" in record.cost_ratio  # a past decision is auditable against it


def test_record_stores_the_full_payload_and_no_label(payload):
    record = _record(payload)
    assert record.features == payload
    assert "loan_status" not in record.features
    assert not hasattr(record, "default")  # labels arrive later, by design


def test_ids_are_unique_per_call(payload):
    assert _record(payload).prediction_id != _record(payload).prediction_id


def test_source_defaults_to_live_and_is_overridable(payload):
    assert _record(payload).source == "live"
    assert _record(payload, source="replay-2016-03").source == "replay-2016-03"


# --- live round trip -----------------------------------------------------------------

def _postgres_reachable() -> bool:
    import socket
    import urllib.parse

    from credit_default.store import dsn

    parsed = urllib.parse.urlparse(dsn())
    try:
        socket.create_connection((parsed.hostname, parsed.port or 5432), timeout=2).close()
        return True
    except OSError:
        return False


@pytest.mark.services
@pytest.mark.skipif(not _postgres_reachable(), reason="postgres not running")
def test_round_trip_through_postgres(payload):
    import json

    from credit_default.store import count, init_schema, open_pool, persist

    pool = open_pool()
    try:
        init_schema(pool)  # idempotent: safe to call against an existing table
        before = count(pool)
        record = _record(payload, source="pytest")
        persist(pool, record)
        assert count(pool) == before + 1

        with pool.connection() as conn:
            row = conn.execute(
                "SELECT loan_id, issue_d, model_version, decision, source, features"
                " FROM predictions WHERE prediction_id = %s",
                (record.prediction_id,),
            ).fetchone()
        loan_id, issue_d, version, decision, source, features = row
        assert loan_id == payload["id"]
        assert str(issue_d) == payload["issue_d"]
        assert version == 1 and decision == "decline" and source == "pytest"
        stored = features if isinstance(features, dict) else json.loads(features)
        assert stored["loan_amnt"] == payload["loan_amnt"]  # JSONB survives the trip

        with pool.connection() as conn:  # cleanup
            conn.execute("DELETE FROM predictions WHERE source = 'pytest'")
    finally:
        pool.close()
