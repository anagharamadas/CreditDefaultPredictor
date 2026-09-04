"""Determinism finalised (#31): byte-identity across processes, pickles, and real data.

The in-suite double-build test (test_features) proves same-process determinism.
These close the remaining gaps:

- cross-process: two fresh interpreters with DIFFERENT hash seeds must produce the
  same matrix bytes — catches dict-order / hash-seed nondeterminism a same-process
  test cannot see.
- pickle round trip: the serialised fitted pipeline is what P7 ships and P8 serves;
  parity across the pickle boundary is the guarantee that matters in production.
- real data: the same claims on an actual train sample (marker: realdata — skipped
  where the interim parquet is absent, e.g. CI).
"""

import hashlib
import os
import pickle
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from credit_default.features import build_pipeline
from credit_default.features.pipeline import feature_names
from credit_default.ingest import INTERIM_ACCEPTED, read_accepted

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "parity_sample.csv"

_SUBPROCESS_SCRIPT = r"""
import hashlib
from credit_default.features import build_pipeline
from credit_default.features.pipeline import feature_names
from credit_default.ingest import read_accepted

df = read_accepted("tests/fixtures/parity_sample.csv", strict=False)
x_frame = df.drop(columns=["loan_status"])
pipe = build_pipeline().fit(x_frame)
matrix = pipe.transform(x_frame)
print(hashlib.sha256(matrix.tobytes()).hexdigest())
print(hashlib.sha256("|".join(feature_names(pipe)).encode()).hexdigest())
"""


def _run_in_fresh_process(hash_seed: str) -> tuple[str, str]:
    env = os.environ | {"PYTHONHASHSEED": hash_seed, "PYTHONPATH": "src"}
    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT],
        capture_output=True, text=True, cwd=ROOT, env=env, check=True,
    )
    matrix_hash, names_hash = result.stdout.split()
    return matrix_hash, names_hash


def test_cross_process_determinism_under_different_hash_seeds():
    a = _run_in_fresh_process("0")
    b = _run_in_fresh_process("42")
    assert a == b  # same matrix bytes and same feature-name order, different interpreters


def _fixture_features():
    return read_accepted(FIXTURE, strict=False).drop(columns=["loan_status"])


def test_pickle_roundtrip_preserves_parity():
    x_frame = _fixture_features()
    fitted = build_pipeline().fit(x_frame)
    revived = pickle.loads(pickle.dumps(fitted))
    assert np.array_equal(fitted.transform(x_frame), revived.transform(x_frame))
    assert feature_names(fitted) == feature_names(revived)


def test_pickle_is_stable_across_dump_load_cycles():
    x_frame = _fixture_features()
    fitted = build_pipeline().fit(x_frame)
    once = pickle.loads(pickle.dumps(fitted))
    twice = pickle.loads(pickle.dumps(once))
    assert np.array_equal(fitted.transform(x_frame), twice.transform(x_frame))


@pytest.mark.realdata
@pytest.mark.skipif(not Path(INTERIM_ACCEPTED).exists(), reason="interim parquet not built")
def test_real_train_sample_is_deterministic_and_pickle_safe():
    import pandas as pd

    from credit_default.splits import TRAIN, assign_split, split_frame

    df = assign_split(pd.read_parquet(INTERIM_ACCEPTED))
    train = split_frame(df, TRAIN).head(20_000).drop(columns=["loan_status"])

    a = build_pipeline().fit_transform(train)
    b = build_pipeline().fit_transform(train)
    assert np.array_equal(a, b)

    fitted = build_pipeline().fit(train)
    revived = pickle.loads(pickle.dumps(fitted))
    assert np.array_equal(fitted.transform(train), revived.transform(train))
    assert hashlib.sha256(a.tobytes()).hexdigest() == hashlib.sha256(b.tobytes()).hexdigest()
