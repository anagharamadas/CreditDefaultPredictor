"""Shared test fixtures.

Lives here rather than being imported across test modules: pytest injects
conftest fixtures by name with no import at all, so nothing depends on how the
suite was invoked. (`python -m pytest` puts the CWD on sys.path and plain
`pytest` does not — a cross-module `from tests.test_api import ...` works under
one and fails under the other. Fixtures avoid the question entirely.)
"""

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


@pytest.fixture(scope="session")
def stub_loader():
    """A model loader that never touches MLflow."""

    def loader():
        return StubModel(), "stub-model", 7

    return loader


@pytest.fixture(scope="session")
def failing_loader():
    def loader():
        raise ConnectionError("registry unreachable")

    return loader


@pytest.fixture(scope="module")
def payload():
    """One valid scoring payload, built through the real ingest + serving path."""
    fixture = read_accepted("tests/fixtures/parity_sample.csv", strict=False)
    return frame_to_payloads(fixture.head(1))[0]


@pytest.fixture()
def client(stub_loader):
    """App with a stub model and no prediction store — pure API behaviour."""
    with TestClient(create_app(model_loader=stub_loader, store_opener=None)) as c:
        yield c
