"""Prefect orchestration: the end-to-end training DAG (ticket #37).

ingest -> contract validation -> per-model train+log, as observable, retryable
tasks instead of a script that either finishes or doesn't. Prefect 3 runs this
locally with no server to operate (flow runs are recorded in its local store);
MLflow remains the system of record for models and metrics — Prefect records
*execution*, MLflow records *results*.

Run:  PYTHONPATH=src python -m credit_default.flows            # all three baselines
      PYTHONPATH=src python -m credit_default.flows logistic   # a subset
"""

from __future__ import annotations

import sys
from pathlib import Path

from prefect import flow, get_run_logger, task


@task(retries=0)
def ensure_interim(rebuild: bool = False) -> str:
    """Raw CSV -> typed parquet, skipped when the parquet already exists."""
    from credit_default.ingest import INTERIM_ACCEPTED, build_interim

    logger = get_run_logger()
    if Path(INTERIM_ACCEPTED).exists() and not rebuild:
        logger.info("interim parquet present, skipping ingest: %s", INTERIM_ACCEPTED)
        return str(INTERIM_ACCEPTED)
    logger.info("building interim parquet from raw CSV…")
    return str(build_interim())


@task(retries=0)
def validate_interim(path: str) -> int:
    """The Pandera contract as a pipeline gate: bad data stops the flow here."""
    import pandas as pd

    from credit_default.contract import validate_accepted

    df = pd.read_parquet(path)
    validate_accepted(df)
    get_run_logger().info("contract OK: %s rows", f"{len(df):,}")
    return len(df)


@task(retries=0)
def train_model(model_name: str) -> str:
    """One baseline through the tracked entrypoint; returns the MLflow run id."""
    from credit_default.tracking import setup_tracking
    from credit_default.train import RUNNERS, prepare_data

    setup_tracking()
    run_id = RUNNERS[model_name](*prepare_data())
    get_run_logger().info("%s -> mlflow run %s", model_name, run_id)
    return run_id


@flow(name="baseline-training")
def baseline_training(models: tuple[str, ...] = ("prior", "logistic", "lightgbm")) -> dict:
    """The P5 DAG. Sequential on purpose: one laptop, memory-heavy tasks."""
    from credit_default.train import RUNNERS

    unknown = set(models) - set(RUNNERS)
    if unknown:
        raise ValueError(f"unknown models: {sorted(unknown)}; choose from {sorted(RUNNERS)}")

    path = ensure_interim()
    validate_interim(path)
    run_ids = {name: train_model(name) for name in models}
    get_run_logger().info("flow complete: %s", run_ids)
    return run_ids


if __name__ == "__main__":
    selected = tuple(sys.argv[1:]) or ("prior", "logistic", "lightgbm")
    print(baseline_training(models=selected))
