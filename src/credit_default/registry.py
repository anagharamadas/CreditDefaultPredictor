"""Model registry (ticket #43): the selected model as a versioned, promotable artifact.

The logged artifact already bundles preprocessing + model as ONE object (the sklearn
Pipeline from P4/P5) — registration makes it versioned and addressable. Serving (P8)
loads `models:/<name>@champion` and nothing else; promotion and rollback are alias
moves, recorded server-side with timestamps.

API note (ADR-0001 discipline — verify against the pinned version): the ticket's
acceptance criterion said "stage transitions None->Staging->Production", but MLflow
3.x REMOVED registry stages. The modern equivalent implemented here is aliases:
`staging` for the candidate under review, `champion` for the serving model. Same
lifecycle, current API.

Run:  PYTHONPATH=src python -m credit_default.registry   # register + promote ADR-0004's model
"""

from __future__ import annotations

import mlflow
from mlflow import MlflowClient

from credit_default.tracking import setup_tracking

MODEL_NAME = "credit-default-granting"

#: The v1 selection is a specific run (ADR-0004), not "whatever is newest".
ADR_0004_RUN_ID = "e299b8e7489e4e9186b3680c39b45166"

STAGING, CHAMPION = "staging", "champion"


def register_run(run_id: str, name: str = MODEL_NAME) -> int:
    """Register a run's model artifact; returns the new version number.

    Version tags carry the audit trail: the source run (whose own tags hold the
    full lineage) and the ADR that justified it.
    """
    version = mlflow.register_model(f"runs:/{run_id}/model", name)
    client = MlflowClient()
    client.set_model_version_tag(name, version.version, "source_run_id", run_id)
    client.set_model_version_tag(name, version.version, "selection_adr", "ADR-0004")
    return int(version.version)


def promote(version: int, alias: str, name: str = MODEL_NAME) -> None:
    """Point an alias at a version. Serving only ever reads @champion, so moving
    that alias IS deployment — and moving it back IS rollback (P11's path)."""
    MlflowClient().set_registered_model_alias(name, alias, str(version))


def resolve(alias: str, name: str = MODEL_NAME) -> int:
    """Which version an alias currently points at."""
    return int(MlflowClient().get_model_version_by_alias(name, alias).version)


def load(alias: str = CHAMPION, name: str = MODEL_NAME):
    """The one loading path serving uses: registry name + alias, nothing else."""
    return mlflow.sklearn.load_model(f"models:/{name}@{alias}")


if __name__ == "__main__":
    import pandas as pd

    from credit_default.ingest import read_accepted

    setup_tracking()
    version = register_run(ADR_0004_RUN_ID)
    print(f"registered {MODEL_NAME} v{version} from run {ADR_0004_RUN_ID[:8]}")

    promote(version, STAGING)
    print(f"alias {STAGING!r} -> v{resolve(STAGING)}   (candidate under review)")
    promote(version, CHAMPION)
    print(f"alias {CHAMPION!r} -> v{resolve(CHAMPION)}  (the serving model)")

    # Standalone proof: load via the registry address only, score real fixture rows.
    model = load(CHAMPION)
    fixture = read_accepted("tests/fixtures/parity_sample.csv", strict=False)
    probs = model.predict_proba(fixture.drop(columns=["loan_status"]))[:, 1]
    frame = pd.DataFrame({"id": fixture["id"].head(5), "p_default": probs[:5].round(4)})
    print(f"\nloaded models:/{MODEL_NAME}@{CHAMPION}; scored {len(probs)} fixture loans:")
    print(frame.to_string(index=False))
