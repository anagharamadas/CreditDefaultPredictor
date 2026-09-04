"""Baseline training entrypoints (P5): every run tracked, evaluated per the protocol.

Rules inherited from docs/EVAL_PROTOCOL.md and enforced here:
- fit on TRAIN only (the pipeline's gate raises otherwise);
- selection metrics computed on VALIDATION's labelled subset, with label coverage
  logged next to every metric (quoting one without the other is a violation);
- the operating threshold comes from threshold.py — derived, never tuned;
- the frozen holdout is not touched (nothing here imports it).

Run:  PYTHONPATH=src python -m credit_default.train prior
      PYTHONPATH=src python -m credit_default.train logistic
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline

from credit_default.features import build_pipeline
from credit_default.ingest import INTERIM_ACCEPTED, RAW_ACCEPTED
from credit_default.labels import LABEL_COL
from credit_default.splits import TRAIN, VALIDATION, assign_split, split_frame
from credit_default.threshold import (
    SENSITIVITY_RATIOS,
    derive_threshold,
    expected_cost_per_loan,
)
from credit_default.tracking import setup_tracking

HOLDOUT_METADATA = Path("data/splits/holdout_manifest.json")

# Model serialisation: MLflow 3.x defaults to skops (a safe-loading format), but skops
# cannot represent our FunctionTransformer(derive_features) — function references are
# unsupported by design. cloudpickle is the documented fallback; acceptable here
# because the artifact is produced AND consumed inside this project only, and the
# pickle-boundary parity tests (#31) prove transform fidelity across it.
MODEL_SERIALIZATION = "cloudpickle"


# --- lineage (formalised + enforced in #36) ----------------------------------------

def lineage_tags() -> dict[str, str]:
    """The facts that make a run reproducible: exact data, exact code, exact splits."""
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
        return result.stdout.strip()

    raw_md5 = "unknown"
    dvc_pointer = Path(f"{RAW_ACCEPTED}.dvc")
    if dvc_pointer.exists():
        for line in dvc_pointer.read_text().splitlines():
            if "md5:" in line:
                raw_md5 = line.split("md5:")[1].strip()
                break

    manifest_sha = "unknown"
    if HOLDOUT_METADATA.exists():
        import json

        manifest_sha = json.loads(HOLDOUT_METADATA.read_text())["sha256"]

    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": "yes" if git("status", "--porcelain") else "no",
        "raw_data_md5": raw_md5,
        "holdout_manifest_sha256": manifest_sha,
    }


# --- evaluation per the frozen protocol --------------------------------------------

def evaluate(y_true: pd.Series, y_prob: np.ndarray, label_coverage: float) -> dict[str, float]:
    """The EVAL_PROTOCOL metric set. Coverage rides along with every metric batch."""
    metrics = {
        "pr_auc": float(average_precision_score(y_true, y_prob)),
        "roc_auc": float(roc_auc_score(y_true, y_prob)),
        "brier": float(brier_score_loss(y_true, y_prob)),
        "label_coverage": float(label_coverage),
        "default_rate_labelled": float(np.mean(y_true)),
    }
    for ratio in SENSITIVITY_RATIOS:
        theta = derive_threshold(ratio, 1.0)
        metrics[f"expected_cost_at_{ratio:g}to1"] = expected_cost_per_loan(
            y_true, pd.Series(y_prob), theta, cost_fn=ratio, cost_fp=1.0
        )
    metrics["threshold_baseline"] = derive_threshold()
    return metrics


# --- data --------------------------------------------------------------------------

def prepare_data():
    df = assign_split(pd.read_parquet(INTERIM_ACCEPTED))
    train = split_frame(df, TRAIN)
    val = split_frame(df, VALIDATION)
    coverage = float(val[LABEL_COL].notna().mean())
    val_labelled = val.loc[val[LABEL_COL].notna()]

    y_train = train[LABEL_COL].astype("int8")
    y_val = val_labelled[LABEL_COL].astype("int8")
    x_train = train.drop(columns=["loan_status", LABEL_COL])
    x_val = val_labelled.drop(columns=["loan_status", LABEL_COL])
    return x_train, y_train, x_val, y_val, coverage


# --- models ------------------------------------------------------------------------

def run_prior(x_train, y_train, x_val, y_val, coverage) -> str:
    """Majority/prior baseline: everyone gets the training default rate."""
    with mlflow.start_run(run_name="baseline-prior") as run:
        mlflow.set_tags(lineage_tags() | {"model_family": "prior"})
        mlflow.log_params({"model": "prior", "train_rows": len(y_train)})
        prior = float(y_train.mean())
        y_prob = np.full(len(y_val), prior)
        mlflow.log_param("train_prior", prior)
        mlflow.log_metrics(evaluate(y_val, y_prob, coverage))
        return run.info.run_id


def run_logistic(x_train, y_train, x_val, y_val, coverage) -> str:
    """Regularised logistic regression behind the one feature pipeline."""
    params = {"C": 1.0, "max_iter": 2000, "solver": "lbfgs"}
    with mlflow.start_run(run_name="baseline-logistic") as run:
        mlflow.set_tags(lineage_tags() | {"model_family": "logistic"})
        mlflow.log_params({"model": "logistic", "train_rows": len(y_train), **params})
        model = Pipeline(
            [("features", build_pipeline()), ("clf", LogisticRegression(**params))]
        )
        model.fit(x_train, y_train)
        y_prob = model.predict_proba(x_val)[:, 1]
        mlflow.log_metrics(evaluate(y_val, y_prob, coverage))
        mlflow.sklearn.log_model(model, name="model", serialization_format=MODEL_SERIALIZATION)
        return run.info.run_id


def run_lightgbm(x_train, y_train, x_val, y_val, coverage) -> str:
    """Gradient-boosted trees behind the same pipeline.

    Params are a fixed, modest set — NO search (Charter non-goal 8: hyperparameter
    tuning beyond a small time-boxed budget is out; the time-box here is zero, and
    any future budget belongs to P6's selection work, recorded there).
    deterministic + force_row_wise + fixed seed keep runs reproducible at the cost
    of some speed — reproducibility is a charter metric, wall-clock is not.
    """
    import lightgbm

    params = {
        "n_estimators": 500,
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_child_samples": 100,
        "random_state": 42,
        "deterministic": True,
        "force_row_wise": True,
        "verbose": -1,
    }
    with mlflow.start_run(run_name="baseline-lightgbm") as run:
        mlflow.set_tags(lineage_tags() | {"model_family": "lightgbm"})
        mlflow.log_params(
            {"model": "lightgbm", "train_rows": len(y_train),
             "lightgbm_version": lightgbm.__version__, **params}
        )
        model = Pipeline(
            [("features", build_pipeline()), ("clf", lightgbm.LGBMClassifier(**params))]
        )
        model.fit(x_train, y_train)
        y_prob = model.predict_proba(x_val)[:, 1]
        mlflow.log_metrics(evaluate(y_val, y_prob, coverage))
        mlflow.sklearn.log_model(model, name="model", serialization_format=MODEL_SERIALIZATION)
        return run.info.run_id


RUNNERS = {"prior": run_prior, "logistic": run_logistic, "lightgbm": run_lightgbm}


def main(which: str) -> None:
    setup_tracking()
    data = prepare_data()
    run_id = RUNNERS[which](*data)
    print(f"{which}: run_id={run_id}")


if __name__ == "__main__":
    main(sys.argv[1])
