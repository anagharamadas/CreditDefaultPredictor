"""MLflow tracking configuration — one place, imported by every training entrypoint.

The server runs locally via docker compose (service `mlflow`, host port 5001,
sqlite backend + artifact store on the gitignored ./.mlflow volume). Every run
in this project belongs to the single experiment below; lineage fields (data
hash, commit, split manifest hash) are ticket #36's logging helper.
"""

from __future__ import annotations

import os

import mlflow

DEFAULT_TRACKING_URI = "http://127.0.0.1:5001"
EXPERIMENT_NAME = "credit-default"


def tracking_uri() -> str:
    """Env override first (CI, remote demo), the compose default otherwise."""
    return os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)


def setup_tracking() -> str:
    """Point mlflow at the server and ensure the project experiment exists.

    Idempotent; returns the experiment id. Raises if the server is unreachable —
    a training run that cannot be tracked should fail, not run untracked.
    """
    mlflow.set_tracking_uri(tracking_uri())
    experiment = mlflow.set_experiment(EXPERIMENT_NAME)
    return experiment.experiment_id
