"""API skeleton: schemas mirror the contract, the contract gates scoring, readiness."""

import pytest
from fastapi.testclient import TestClient

from credit_default.api import create_app

# StubModel, stub_loader, failing_loader, payload and client come from conftest.py


def test_health_is_always_up(client):
    assert client.get("/health").json() == {"status": "up"}


def test_ready_reports_the_loaded_model(client):
    body = client.get("/ready").json()
    assert body["ready"] is True
    assert body["model_name"] == "stub-model"
    assert body["model_version"] == 7


def test_ready_is_503_when_the_model_cannot_load(payload, failing_loader):
    with TestClient(create_app(model_loader=failing_loader, store_opener=None)) as c:
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
