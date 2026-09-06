"""API skeleton: schemas mirror the contract, the contract gates scoring, readiness."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from credit_default.api import create_app
from credit_default.features.serving import frame_to_payloads
from credit_default.ingest import read_accepted


class StubModel:
    """Deterministic scores, no registry needed."""

    def predict_proba(self, frame):
        p = np.full(len(frame), 0.42)
        return np.column_stack([1 - p, p])


def stub_loader():
    return StubModel(), "stub-model", 7


def failing_loader():
    raise ConnectionError("registry unreachable")


@pytest.fixture(scope="module")
def payload():
    fixture = read_accepted("tests/fixtures/parity_sample.csv", strict=False)
    return frame_to_payloads(fixture.head(1))[0]


@pytest.fixture()
def client():
    with TestClient(create_app(model_loader=stub_loader)) as c:
        yield c


def test_health_is_always_up(client):
    assert client.get("/health").json() == {"status": "up"}


def test_ready_reports_the_loaded_model(client):
    body = client.get("/ready").json()
    assert body["ready"] is True
    assert body["model_name"] == "stub-model"
    assert body["model_version"] == 7


def test_ready_is_503_when_the_model_cannot_load(payload):
    with TestClient(create_app(model_loader=failing_loader)) as c:
        r = c.get("/ready")
        assert r.status_code == 503
        assert "registry unreachable" in r.json()["detail"]
        assert c.post("/score", json=payload).status_code == 503  # never scores blind


def test_valid_application_scores_and_decides(client, payload):
    r = client.post("/score", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == payload["id"]
    assert body["p_default"] == pytest.approx(0.42)
    assert body["decision"] == "decline"  # 0.42 >= θ=0.1667
    assert body["threshold"] == pytest.approx(1 / 6, abs=1e-4)
    assert "[ASSUMED]" in body["cost_ratio_assumed"]


def test_unknown_category_is_rejected_at_the_door(client, payload):
    bad = payload | {"purpose": "yacht"}
    assert client.post("/score", json=bad).status_code == 422


def test_unexpected_extra_field_is_rejected(client, payload):
    assert client.post("/score", json=payload | {"total_pymnt": 999.0}).status_code == 422


def test_contract_bounds_reject_out_of_range_values(client, payload):
    bad = payload | {"loan_amnt": 999_999.0}
    r = client.post("/score", json=bad)
    assert r.status_code == 422
    violations = r.json()["detail"]["violations"]
    assert any(v["column"] == "loan_amnt" for v in violations)


def test_cross_column_invariant_enforced(client, payload):
    bad = payload | {"fico_range_low": 700.0, "fico_range_high": 650.0}
    r = client.post("/score", json=bad)
    assert r.status_code == 422
    assert "contract" in r.json()["detail"]["message"]
