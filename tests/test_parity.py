"""Train/serve parity (#28): one fixture, two paths, byte-identical matrices.

The fixture is committed and sha256-pinned; regenerating it without updating the
pin fails loudly. The batch path is what training does; the serve path pushes every
row through a JSON round trip and the serving converter, one request at a time.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from credit_default.features import build_pipeline
from credit_default.features.serving import frame_to_payloads, payloads_to_frame
from credit_default.ingest import read_accepted

FIXTURE = Path(__file__).parent / "fixtures" / "parity_sample.csv"
# Re-pinned at #30: fixture regenerated with train-window issue dates, because the
# pipeline's TrainWindowGate now refuses to fit on out-of-window rows.
FIXTURE_SHA256 = "0832b6faac9f6444d49c804ffcd9c12e48dd9f65055db7d0097fc2d22472e958"


def test_fixture_is_committed_and_unchanged():
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert digest == FIXTURE_SHA256, (
        "parity fixture changed — if regeneration was intentional, update the pinned "
        "sha256 here in the same commit and say why in its message"
    )


@pytest.fixture(scope="module")
def fixture_frame():
    return read_accepted(FIXTURE, strict=False)  # the true ingest path, no special casing


@pytest.fixture(scope="module")
def features_view(fixture_frame):
    # The pipeline's input contract on BOTH paths: no target source. Training code
    # drops loan_status before transform; serving requests never carry it.
    return fixture_frame.drop(columns=["loan_status"])


@pytest.fixture(scope="module")
def fitted(features_view):
    return build_pipeline().fit(features_view)


def test_parity_batch_vs_single_row_json_roundtrip(fixture_frame, features_view, fitted):
    """THE parity test: training-batch output == per-request serving output."""
    batch = fitted.transform(features_view)

    payloads = frame_to_payloads(fixture_frame)
    # force a genuine JSON wire round trip, not just dict passing
    payloads = [json.loads(json.dumps(p)) for p in payloads]
    served_rows = [fitted.transform(payloads_to_frame([p])) for p in payloads]
    served = np.vstack(served_rows)

    assert served.shape == batch.shape
    assert np.array_equal(batch, served)  # byte-identical, not approximately equal


def test_parity_batch_vs_serving_batch(fixture_frame, features_view, fitted):
    """Same but serving receives all rows in one request."""
    payloads = json.loads(json.dumps(frame_to_payloads(fixture_frame)))
    served = fitted.transform(payloads_to_frame(payloads))
    assert np.array_equal(fitted.transform(features_view), served)


def test_serving_frame_reproduces_ingest_dtypes(fixture_frame):
    served = payloads_to_frame(frame_to_payloads(fixture_frame))
    for col in served.columns:
        expected = fixture_frame[col].dtype
        got = served[col].dtype
        if str(expected) == "category":
            assert str(got) == "category", col
        else:
            assert got == expected, col


def test_nulls_survive_the_round_trip(fixture_frame):
    served = payloads_to_frame(frame_to_payloads(fixture_frame))
    for col in ("mths_since_last_delinq", "dti", "emp_length"):
        assert served[col].isna().sum() == fixture_frame[col].isna().sum(), col
    assert served["mths_since_last_delinq"].isna().sum() > 0  # fixture really has gaps


def test_payload_excludes_the_target_source(fixture_frame):
    payloads = frame_to_payloads(fixture_frame)
    assert all("loan_status" not in p for p in payloads)
