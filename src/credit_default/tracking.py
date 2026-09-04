"""MLflow tracking configuration — one place, imported by every training entrypoint.

The server runs locally via docker compose (service `mlflow`, host port 5001,
sqlite backend + artifact store on the gitignored ./.mlflow volume). Every run
in this project belongs to the single experiment below; lineage fields (data
hash, commit, split manifest hash) are ticket #36's logging helper.
"""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import mlflow

DEFAULT_TRACKING_URI = "http://127.0.0.1:5001"
EXPERIMENT_NAME = "credit-default"

# Lineage sources (the facts that make a run reproducible)
RAW_DVC_POINTER = Path("data/raw/kaggle/accepted_2007_to_2018Q4.csv.dvc")
HOLDOUT_METADATA = Path("data/splits/holdout_manifest.json")

LINEAGE_KEYS = ("git_commit", "git_dirty", "raw_data_md5", "holdout_manifest_sha256")


class LineageError(RuntimeError):
    """A tracked run cannot start without its reproducibility facts."""


def lineage_tags(
    *,
    dvc_pointer: Path = RAW_DVC_POINTER,
    holdout_metadata: Path = HOLDOUT_METADATA,
) -> dict[str, str]:
    """Exact data + exact code + exact splits. Raises rather than tagging 'unknown' —
    an untraceable run is worse than no run (Charter §4.2)."""

    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise LineageError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    if not dvc_pointer.exists():
        raise LineageError(f"DVC pointer missing: {dvc_pointer} — which bytes trained this?")
    raw_md5 = next(
        (line.split("md5:")[1].strip() for line in dvc_pointer.read_text().splitlines()
         if "md5:" in line),
        None,
    )
    if not raw_md5:
        raise LineageError(f"no md5 recorded in {dvc_pointer}")

    if not holdout_metadata.exists():
        raise LineageError(f"holdout metadata missing: {holdout_metadata}")
    manifest_sha = json.loads(holdout_metadata.read_text())["sha256"]

    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": "yes" if git("status", "--porcelain") else "no",
        "raw_data_md5": raw_md5,
        "holdout_manifest_sha256": manifest_sha,
    }


@contextmanager
def start_tracked_run(run_name: str, model_family: str, extra_tags: dict | None = None):
    """The only sanctioned way to open a training run: lineage tags or no run.

    Enforcement is structural — the tags are gathered (and validated) BEFORE the run
    opens, so an MLflow run created through this helper cannot lack them.
    """
    tags = lineage_tags() | {"model_family": model_family} | (extra_tags or {})
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.set_tags(tags)
        yield run


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
