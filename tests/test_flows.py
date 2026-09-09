"""Flow wiring: structure and input validation, without executing the DAG."""

import pytest

from credit_default.flows import (
    baseline_training,
    ensure_interim,
    train_model,
    validate_interim,
    validate_model_names,
)


def test_flow_and_tasks_are_wired():
    assert baseline_training.name == "baseline-training"
    for t in (ensure_interim, validate_interim, train_model):
        assert hasattr(t, "submit")  # a real Prefect task, not a bare function


def test_unknown_model_names_are_rejected():
    with pytest.raises(ValueError, match="unknown models"):
        validate_model_names(("prior", "quantum-gbm"))


def test_known_model_names_pass_through():
    assert validate_model_names(("prior", "logistic")) == ("prior", "logistic")
