"""Tracking config unit tests + a live round trip against the compose service."""

import urllib.error
import urllib.request

import pytest

from credit_default.tracking import (
    DEFAULT_TRACKING_URI,
    EXPERIMENT_NAME,
    setup_tracking,
    tracking_uri,
)


def _server_reachable() -> bool:
    try:
        urllib.request.urlopen(f"{DEFAULT_TRACKING_URI}/health", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


def test_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://elsewhere:9999")
    assert tracking_uri() == "http://elsewhere:9999"
    monkeypatch.delenv("MLFLOW_TRACKING_URI")
    assert tracking_uri() == DEFAULT_TRACKING_URI


def test_experiment_name_is_stable():
    # Runs accumulate under this name for the life of the project; renaming it
    # orphans history. Change requires a deliberate decision, hence a pin.
    assert EXPERIMENT_NAME == "credit-default"


@pytest.mark.services
@pytest.mark.skipif(not _server_reachable(), reason="mlflow compose service not running")
def test_live_round_trip_log_and_fetch():
    import mlflow

    experiment_id = setup_tracking()
    with mlflow.start_run(run_name="tracking-smoke") as run:
        mlflow.log_param("purpose", "test_tracking round trip")
        mlflow.log_metric("answer", 42.0)
        run_id = run.info.run_id

    fetched = mlflow.get_run(run_id)
    assert fetched.info.experiment_id == experiment_id
    assert fetched.data.metrics["answer"] == 42.0
    assert fetched.data.params["purpose"] == "test_tracking round trip"
