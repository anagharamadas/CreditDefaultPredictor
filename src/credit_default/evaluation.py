"""P6 evaluation harness: compare tracked runs on later vintages, per the protocol.

Models are loaded FROM their MLflow runs (runs:/<id>/model) — the comparison scores
exactly what was logged, not a re-trained lookalike. Results are themselves logged
as an evaluation run (lineage-tagged like any other), so every comparison is as
traceable as the models it compares.

Holdout discipline: split_features(HOLDOUT) demands the same spelled-out
acknowledgment as the manifest guard, verifies the frozen manifest end-to-end, and
cross-checks the frame against the frozen ID list before returning a single row.
The final report (#42) is the only intended caller.

Run:  PYTHONPATH=src python -m credit_default.evaluation            # latest per family
"""

from __future__ import annotations

import mlflow
import pandas as pd

from credit_default.holdout import load_holdout_ids
from credit_default.holdout import verify as verify_holdout
from credit_default.ingest import INTERIM_ACCEPTED
from credit_default.labels import LABEL_COL
from credit_default.splits import HOLDOUT, VALIDATION, assign_split, split_frame
from credit_default.tracking import setup_tracking, start_tracked_run
from credit_default.train import evaluate

BASELINE_FAMILIES = ("prior", "logistic", "lightgbm")


def split_features(
    split_name: str,
    *,
    i_understand_this_is_for_final_p6_evaluation: bool = False,
):
    """(x, y, coverage) for an evaluation split's labelled subset.

    HOLDOUT additionally requires the explicit acknowledgment, a full manifest
    verification, and an exact ID cross-check against the frozen list.
    """
    if split_name == HOLDOUT and not i_understand_this_is_for_final_p6_evaluation:
        raise PermissionError(
            "holdout evaluation requires the explicit acknowledgment "
            "(EVAL_PROTOCOL §1); pass it only from the final P6 report."
        )
    df = assign_split(pd.read_parquet(INTERIM_ACCEPTED))
    frame = split_frame(df, split_name)
    if split_name == HOLDOUT:
        verify_holdout(df)  # hash + recomputation integrity before any metric
        frozen = load_holdout_ids(i_understand_this_is_for_final_p6_evaluation=True)
        assert sorted(frame["id"].astype(str), key=int) == frozen, (
            "holdout frame does not match the frozen manifest"
        )
    coverage = float(frame[LABEL_COL].notna().mean())
    labelled = frame.loc[frame[LABEL_COL].notna()]
    y = labelled[LABEL_COL].astype("int8")
    x = labelled.drop(columns=["loan_status", LABEL_COL])
    return x, y, coverage


def probabilities(run: mlflow.entities.Run, x: pd.DataFrame):
    """Scores from a tracked run: the logged model artifact, or the prior constant."""
    import numpy as np

    if run.data.params.get("model") == "prior":
        return np.full(len(x), float(run.data.params["train_prior"]))
    model = mlflow.sklearn.load_model(f"runs:/{run.info.run_id}/model")
    return model.predict_proba(x)[:, 1]


def latest_runs(families=BASELINE_FAMILIES) -> dict[str, str]:
    """Newest non-reproduction run id per model family."""
    experiment = mlflow.get_experiment_by_name("credit-default")
    runs = mlflow.search_runs([experiment.experiment_id], output_format="list")
    out: dict[str, str] = {}
    for run in sorted(runs, key=lambda r: r.info.start_time, reverse=True):
        family = run.data.tags.get("model_family")
        if (
            family in families
            and family not in out
            and "reproduction_of" not in run.data.tags
            and run.info.status == "FINISHED"
        ):
            out[family] = run.info.run_id
    return out


def compare_on_split(
    run_ids: dict[str, str],
    split_name: str = VALIDATION,
    **holdout_ack,
) -> pd.DataFrame:
    """Score every run on one split; log the comparison as its own tracked run."""
    x, y, coverage = split_features(split_name, **holdout_ack)
    rows = {}
    for name, run_id in run_ids.items():
        run = mlflow.get_run(run_id)
        metrics = evaluate(y, probabilities(run, x), coverage)
        metrics["scored_run_id"] = run_id
        rows[name] = metrics
    table = pd.DataFrame(rows).T.sort_values("pr_auc", ascending=False)

    with start_tracked_run(f"evaluation-{split_name}", "evaluation") as eval_run:
        mlflow.log_param("split", split_name)
        mlflow.log_param("compared_runs", ",".join(f"{k}={v}" for k, v in run_ids.items()))
        for name, metrics in rows.items():
            mlflow.log_metrics(
                {f"{name}__{k}": v for k, v in metrics.items() if isinstance(v, float)}
            )
        mlflow.log_table(table.reset_index(names="model"), "comparison.json")
        table.attrs["evaluation_run_id"] = eval_run.info.run_id
    return table


if __name__ == "__main__":
    setup_tracking()
    ids = latest_runs()
    print(f"comparing latest runs on {VALIDATION}: {ids}")
    result = compare_on_split(ids)
    cols = ["pr_auc", "roc_auc", "brier", "expected_cost_at_5to1", "label_coverage"]
    print(result[cols].round(4).to_string())
    print(f"evaluation run: {result.attrs['evaluation_run_id']}")
