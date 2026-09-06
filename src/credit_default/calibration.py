"""Calibration assessment + method (ticket #39, EVAL_PROTOCOL §5.1).

A granting model's probability must MEAN something: of loans scored 20%, about 20%
should default — otherwise θ = C_FP/(C_FP+C_FN) minimises nothing. Tree ensembles
are routinely miscalibrated, so this is assessed, not assumed.

Method, honouring "calibrator fit inside the training window only" (Charter §4.2):
the train window is split TEMPORALLY — base model fit on 2013-01..2015-06,
isotonic calibrator fit on 2015-07..2015-12. The calibration slice is out-of-sample
for the model (calibrating on data the model trained on would inherit its overfit
confidence) yet entirely inside the training vintages. Nothing later than 2015-12
teaches either component anything.

Run:  PYTHONPATH=src python -m credit_default.calibration
"""

from __future__ import annotations

import mlflow
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.isotonic import IsotonicRegression
from sklearn.pipeline import Pipeline

from credit_default.features import build_pipeline
from credit_default.splits import TRAIN_END
from credit_default.tracking import setup_tracking, start_tracked_run
from credit_default.train import MODEL_SERIALIZATION, evaluate, prepare_data

#: last issue month the BASE model may learn from; later train months calibrate.
CALIBRATION_SPLIT = pd.Timestamp("2015-06-01")

LGBM_PARAMS = {  # identical to the #35 baseline — this ticket changes calibration, not the model
    "n_estimators": 500,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 100,
    "random_state": 42,
    "deterministic": True,
    "force_row_wise": True,
    "verbose": -1,
}


# --- assessment --------------------------------------------------------------------

def reliability_table(y_true, y_prob, n_bins: int = 10) -> pd.DataFrame:
    """Equal-count bins: mean predicted vs observed default rate per bin.

    This table IS the reliability curve (the figure is just its plot); perfect
    calibration means predicted == observed in every bin.
    """
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_prob, dtype=float)
    order = np.argsort(p, kind="stable")
    bins = np.array_split(order, n_bins)
    rows = [
        {
            "bin": i + 1,
            "loans": len(idx),
            "mean_predicted": float(p[idx].mean()),
            "observed_rate": float(y[idx].mean()),
        }
        for i, idx in enumerate(bins)
    ]
    out = pd.DataFrame(rows)
    out["gap"] = out["mean_predicted"] - out["observed_rate"]
    return out


def expected_calibration_error(y_true, y_prob, n_bins: int = 10) -> float:
    """ECE: count-weighted mean absolute predicted-vs-observed gap."""
    table = reliability_table(y_true, y_prob, n_bins)
    weights = table["loans"] / table["loans"].sum()
    return float((weights * table["gap"].abs()).sum())


def per_month_calibration(x_val, y_val, y_prob) -> pd.DataFrame:
    """Brier + ECE per validation vintage month (the protocol's per-vintage view)."""
    month = x_val["issue_d"].dt.to_period("M").astype(str)
    rows = []
    for m, idx in pd.Series(range(len(month)), index=month).groupby(level=0):
        sel = idx.to_numpy()
        y_m, p_m = np.asarray(y_val)[sel], np.asarray(y_prob)[sel]
        rows.append(
            {
                "month": m,
                "loans": len(sel),
                "brier": float(np.mean((p_m - y_m) ** 2)),
                "ece": expected_calibration_error(y_m, p_m, n_bins=10),
            }
        )
    return pd.DataFrame(rows)


# --- the calibrated model ----------------------------------------------------------

class CalibratedModel(BaseEstimator):
    """Fitted pipeline + isotonic map, one artifact (top-level class: picklable)."""

    def __init__(self, base: Pipeline, calibrator: IsotonicRegression):
        self.base = base
        self.calibrator = calibrator

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        raw = self.base.predict_proba(x)[:, 1]
        cal = self.calibrator.transform(raw)
        return np.column_stack([1.0 - cal, cal])


def run_lightgbm_calibrated(x_train, y_train, x_val, y_val, coverage) -> str:
    """LightGBM fit on the early train window, isotonic-calibrated on the late one."""
    import lightgbm

    fit_mask = (x_train["issue_d"] <= CALIBRATION_SPLIT).to_numpy()
    calib_mask = ~fit_mask
    assert x_train.loc[calib_mask, "issue_d"].max() <= TRAIN_END + pd.offsets.MonthEnd(0)

    with start_tracked_run("lightgbm-calibrated", "lightgbm-calibrated") as run:
        mlflow.log_params(
            {
                "model": "lightgbm_calibrated",
                "calibration_method": "isotonic",
                "base_fit_through": f"{CALIBRATION_SPLIT:%Y-%m}",
                "calibration_slice": f"{CALIBRATION_SPLIT + pd.offsets.MonthBegin(1):%Y-%m}"
                f"..{TRAIN_END:%Y-%m}",
                "fit_rows": int(fit_mask.sum()),
                "calibration_rows": int(calib_mask.sum()),
                **LGBM_PARAMS,
            }
        )
        base = Pipeline(
            [("features", build_pipeline()), ("clf", lightgbm.LGBMClassifier(**LGBM_PARAMS))]
        )
        base.fit(x_train.loc[fit_mask], y_train.loc[fit_mask])

        raw_calib = base.predict_proba(x_train.loc[calib_mask])[:, 1]
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(raw_calib, y_train.loc[calib_mask])
        model = CalibratedModel(base, calibrator)

        y_prob = model.predict_proba(x_val)[:, 1]
        metrics = evaluate(y_val, y_prob, coverage)
        metrics["ece"] = expected_calibration_error(y_val, y_prob)
        mlflow.log_metrics(metrics)
        mlflow.log_table(reliability_table(y_val, y_prob), "reliability_validation.json")
        mlflow.log_table(per_month_calibration(x_val, y_val, y_prob), "calibration_by_month.json")
        mlflow.sklearn.log_model(model, name="model", serialization_format=MODEL_SERIALIZATION)
        return run.info.run_id


def assess_run(run_id: str, x_val, y_val, coverage) -> dict:
    """Calibration numbers for an already-logged run (comparison side of the ticket)."""
    from credit_default.evaluation import probabilities

    run = mlflow.get_run(run_id)
    y_prob = probabilities(run, x_val)
    return {
        "brier": float(np.mean((np.asarray(y_prob) - np.asarray(y_val)) ** 2)),
        "ece": expected_calibration_error(y_val, y_prob),
        "reliability": reliability_table(y_val, y_prob),
        "y_prob": np.asarray(y_prob),
    }


if __name__ == "__main__":
    from credit_default.evaluation import latest_runs

    setup_tracking()
    x_train, y_train, x_val, y_val, coverage = prepare_data()

    uncal_id = latest_runs(families=("lightgbm",))["lightgbm"]
    before = assess_run(uncal_id, x_val, y_val, coverage)
    print(f"uncalibrated lightgbm ({uncal_id[:8]}): "
          f"brier {before['brier']:.5f}  ece {before['ece']:.5f}")

    cal_id = run_lightgbm_calibrated(x_train, y_train, x_val, y_val, coverage)
    after = mlflow.get_run(cal_id).data.metrics
    print(f"calibrated  lightgbm ({cal_id[:8]}): "
          f"brier {after['brier']:.5f}  ece {after['ece']:.5f}  pr_auc {after['pr_auc']:.4f}")
