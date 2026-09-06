"""Registry lifecycle against the live server (services-marked): register,
promote through aliases, load standalone, roll back — then clean up."""

import urllib.error
import urllib.request

import numpy as np
import pytest

from credit_default.registry import load, promote, register_run, resolve
from credit_default.tracking import DEFAULT_TRACKING_URI


def _server_reachable() -> bool:
    try:
        urllib.request.urlopen(f"{DEFAULT_TRACKING_URI}/health", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


pytestmark = [
    pytest.mark.services,
    pytest.mark.skipif(not _server_reachable(), reason="mlflow compose service not running"),
]

TEST_MODEL = "test-registry-lifecycle"


@pytest.fixture
def clean_registry():
    from contextlib import suppress

    from mlflow import MlflowClient
    from mlflow.exceptions import MlflowException

    from credit_default.tracking import setup_tracking

    setup_tracking()
    yield
    with suppress(MlflowException):
        MlflowClient().delete_registered_model(TEST_MODEL)


def test_full_lifecycle_register_promote_load_rollback(clean_registry):
    from credit_default.evaluation import latest_runs
    from credit_default.ingest import read_accepted

    run_id = latest_runs(families=("lightgbm",))["lightgbm"]

    v1 = register_run(run_id, name=TEST_MODEL)
    promote(v1, "staging", name=TEST_MODEL)
    assert resolve("staging", name=TEST_MODEL) == v1

    promote(v1, "champion", name=TEST_MODEL)
    assert resolve("champion", name=TEST_MODEL) == v1

    # standalone load through the registry address; scores real fixture rows
    model = load("champion", name=TEST_MODEL)
    fixture = read_accepted("tests/fixtures/parity_sample.csv", strict=False)
    probs = model.predict_proba(fixture.drop(columns=["loan_status"]))[:, 1]
    assert probs.shape == (len(fixture),)
    assert np.all((probs >= 0) & (probs <= 1))

    # rollback is an alias move: register the same run as v2, promote, then revert
    v2 = register_run(run_id, name=TEST_MODEL)
    promote(v2, "champion", name=TEST_MODEL)
    assert resolve("champion", name=TEST_MODEL) == v2
    promote(v1, "champion", name=TEST_MODEL)  # the P11 rollback gesture
    assert resolve("champion", name=TEST_MODEL) == v1
