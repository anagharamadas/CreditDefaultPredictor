"""Rehearse a rollback against a REAL registry (ticket #79, ADR-0006).

The unit tests inject a fake registry, which proves the swap logic but cannot prove
that `registry.resolve` / `registry.load` behave against a live MLflow server the way
ADR-0006 assumes. This script closes that gap: it registers two models that score
differently, serves one, moves the alias, and MEASURES how long the running service
takes to notice — without a restart.

**It never touches the real model.** It registers under its own name
(`champion-refresh-rehearsal`) and its own alias, and deletes them afterwards, so it
is safe to run against the project stack. Rehearsing rollback on the production
registry entry would be its own kind of incident.

Run:  PYTHONPATH=src python scripts/verify_champion_refresh.py
      MLFLOW_TRACKING_URI=http://127.0.0.1:5001 PYTHONPATH=src python scripts/...
"""

from __future__ import annotations

import sys
import time

import mlflow
import numpy as np
from fastapi.testclient import TestClient
from mlflow import MlflowClient
from sklearn.base import BaseEstimator

from credit_default import registry
from credit_default.api import create_app
from credit_default.features.serving import frame_to_payloads
from credit_default.ingest import read_accepted
from credit_default.tracking import tracking_uri

REHEARSAL_NAME = "champion-refresh-rehearsal"
ALIAS = "champion"
REFRESH_SECONDS = 2.0      # production default is 30; shortened so a rehearsal is quick
OLD_SCORE, NEW_SCORE = 0.11, 0.77


class ConstantScorer(BaseEstimator):
    """Stands in for the pipeline. The score identifies WHICH VERSION answered, so a
    swap is provable from the output — not only from the metadata, which could be
    right while the old model is still doing the work."""

    def __init__(self, p: float = 0.5):
        self.p = p

    def fit(self, X, y=None):
        return self

    def predict_proba(self, X):
        p = np.full(len(X), self.p)
        return np.column_stack([1 - p, p])


def _register(p: float) -> int:
    with mlflow.start_run():
        mlflow.sklearn.log_model(
            ConstantScorer(p=p), name="model", serialization_format="cloudpickle"
        )
        run_id = mlflow.active_run().info.run_id
    return int(mlflow.register_model(f"runs:/{run_id}/model", REHEARSAL_NAME).version)


def main() -> int:
    mlflow.set_tracking_uri(tracking_uri())
    print(f"registry: {tracking_uri()}")
    mlflow.set_experiment("champion-refresh-rehearsal")

    old = _register(OLD_SCORE)
    new = _register(NEW_SCORE)
    registry.promote(old, ALIAS, name=REHEARSAL_NAME)
    print(f"registered v{old} (p={OLD_SCORE}) and v{new} (p={NEW_SCORE}); "
          f"@{ALIAS} -> v{registry.resolve(ALIAS, name=REHEARSAL_NAME)}")

    payload = frame_to_payloads(
        read_accepted("tests/fixtures/parity_sample.csv", strict=False).head(1)
    )[0]

    # The REAL registry calls, just pointed at the rehearsal entry.
    def loader():
        return registry.load(ALIAS, name=REHEARSAL_NAME), REHEARSAL_NAME, registry.resolve(
            ALIAS, name=REHEARSAL_NAME
        )

    app = create_app(
        model_loader=loader,
        store_opener=None,
        alias_probe=lambda: registry.resolve(ALIAS, name=REHEARSAL_NAME),
        refresh_seconds=REFRESH_SECONDS,
    )

    failures: list[str] = []
    try:
        with TestClient(app) as client:
            before = client.post("/score", json=payload).json()
            print(f"\nbefore   version={before['model_version']}  "
                  f"p_default={before['p_default']}")
            if before["model_version"] != old:
                failures.append("service did not start on the aliased version")

            print(f"--- moving @{ALIAS} to v{new}; the service is NOT restarted ---")
            registry.promote(new, ALIAS, name=REHEARSAL_NAME)
            started = time.perf_counter()

            ready = {}
            deadline = started + REFRESH_SECONDS * 10
            while time.perf_counter() < deadline:
                ready = client.get("/ready").json()
                if ready.get("model_version") == new:
                    break
                time.sleep(0.25)
            took = time.perf_counter() - started

            after = client.post("/score", json=payload).json()
            print(f"after    version={after['model_version']}  "
                  f"p_default={after['p_default']}   (noticed in {took:.1f}s, "
                  f"budget {REFRESH_SECONDS:g}s)")

            if ready.get("model_version") != new:
                failures.append(f"service never noticed the alias move ({took:.1f}s)")
            if after["model_version"] != new:
                failures.append("scoring still reports the old version")
            if round(after["p_default"], 2) != NEW_SCORE:
                # The failure this check exists for: metadata updated, model didn't.
                failures.append("reported the new version but scored with the old model")
            if took > REFRESH_SECONDS * 2:
                failures.append(f"took {took:.1f}s against a {REFRESH_SECONDS:g}s budget")
    finally:
        MlflowClient().delete_registered_model(REHEARSAL_NAME)
        print(f"cleaned up {REHEARSAL_NAME}")

    if failures:
        print("\nFAIL:\n  " + "\n  ".join(failures))
        return 1
    print("\nPASS — the alias move reached a running service, and the score moved with it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
