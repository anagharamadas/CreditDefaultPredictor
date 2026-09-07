"""Compose-stack smoke test (services-marked): the containerised API really serves.

Skipped unless the stack is up (`docker compose up -d`), so the default suite and
CI stay independent of Docker.
"""

import urllib.error
import urllib.request

import pytest

from credit_default.features.serving import frame_to_payloads
from credit_default.ingest import read_accepted

API = "http://127.0.0.1:8000"


def _api_up() -> bool:
    try:
        urllib.request.urlopen(f"{API}/health", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


pytestmark = [
    pytest.mark.services,
    pytest.mark.skipif(not _api_up(), reason="compose stack not running"),
]


def _post(path: str, payload: dict):
    import json

    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


@pytest.fixture(scope="module")
def payload():
    fixture = read_accepted("tests/fixtures/parity_sample.csv", strict=False)
    return frame_to_payloads(fixture.head(1))[0]


def test_stack_serves_the_registered_champion():
    import json

    with urllib.request.urlopen(f"{API}/ready", timeout=10) as response:
        body = json.load(response)
    assert body["ready"] is True
    assert body["model_name"] == "credit-default-granting"
    assert body["model_version"] >= 1


def test_containerised_score_matches_the_in_process_pipeline(payload):
    """Cross-environment parity: the container's score equals a local load's."""
    from credit_default.registry import load

    status, body = _post("/score", payload)
    assert status == 200

    frame = read_accepted("tests/fixtures/parity_sample.csv", strict=False).head(1)
    local = load("champion").predict_proba(frame.drop(columns=["loan_status"]))[:, 1][0]
    assert body["p_default"] == pytest.approx(float(local), abs=1e-12)


def test_stack_rejects_contract_violations(payload):
    status, body = _post("/score", payload | {"loan_amnt": 999_999.0})
    assert status == 422
    assert any(v["column"] == "loan_amnt" for v in body["detail"]["violations"])
