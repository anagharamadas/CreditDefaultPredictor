"""End-to-end smoke test on the committed fixture — runs in CI, needs no raw data.

Exercises the real chain as a PROGRAM rather than as a test subject: ingest ->
label -> contract -> feature pipeline -> model -> threshold -> decision. Tests
prove behaviour in isolation; this proves the pieces still fit together when
imported and called the way a script or a service calls them.

64 synthetic rows is far too few to learn anything — the model here is scaffolding,
not a result. What is being checked is that nothing raises and the shapes line up.

Run:  PYTHONPATH=src python scripts/ci_smoke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from credit_default.contract import ACCEPTED_SCHEMA
from credit_default.features import build_pipeline
from credit_default.features.serving import frame_to_payloads, payloads_to_frame
from credit_default.ingest import read_accepted
from credit_default.labels import LABEL_COL, add_labels, labelled_only
from credit_default.threshold import derive_threshold

FIXTURE = Path("tests/fixtures/parity_sample.csv")


def main() -> int:
    print(f"smoke: reading {FIXTURE}")
    frame = read_accepted(FIXTURE, strict=False)
    assert len(frame) == 64, f"fixture changed size: {len(frame)}"

    print("smoke: validating against the training data contract")
    ACCEPTED_SCHEMA.validate(frame, lazy=True)

    print("smoke: deriving labels")
    labelled = labelled_only(add_labels(frame))
    y = labelled[LABEL_COL].astype("int8")
    assert y.nunique() == 2, "fixture must contain both classes for the smoke model"
    print(f"       {len(labelled)} labelled rows of {len(frame)} ({y.mean():.0%} positive)")

    print("smoke: fitting the feature pipeline + a model")
    x = labelled.drop(columns=["loan_status", LABEL_COL])
    model = Pipeline(
        [("features", build_pipeline()), ("clf", LogisticRegression(max_iter=1000))]
    )
    model.fit(x, y)
    probabilities = model.predict_proba(x)[:, 1]
    assert probabilities.shape == (len(x),)
    assert np.all((probabilities >= 0) & (probabilities <= 1))

    print("smoke: serving round trip (JSON out, JSON in, same numbers)")
    # Compare like-shaped batches. An earlier version checked `probabilities[:5]`
    # (five rows computed inside a 21-row batch) against a 5-row batch and demanded
    # bit-equality — which is not a parity check but a claim that BLAS accumulates
    # identically at different matrix shapes. Nothing guarantees that: it held on
    # arm64 and failed on the x86 CI runner. The guarantee this project actually
    # makes is about the TRANSFORM, which is elementwise and so is bit-exact.
    sample = x.head(5)
    served_frame = payloads_to_frame(frame_to_payloads(sample))

    features = model.named_steps["features"]
    assert np.array_equal(features.transform(sample), features.transform(served_frame)), (
        "train/serve feature parity broken"
    )
    direct = model.predict_proba(sample)[:, 1]
    served = model.predict_proba(served_frame)[:, 1]
    assert np.array_equal(direct, served), "train/serve prediction parity broken"

    threshold = derive_threshold()
    decisions = ["decline" if p >= threshold else "fund" for p in served]
    print(f"smoke: decisions at threshold {threshold:.4f} -> {decisions}")

    print("smoke: OK — ingest, contract, labels, pipeline, model, parity, threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
