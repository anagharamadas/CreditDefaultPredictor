"""Holdout freeze: immutability, integrity verification, and the access guard."""

import pandas as pd
import pytest

from credit_default.holdout import (
    HoldoutAccessError,
    freeze,
    load_holdout_ids,
    verify,
)


@pytest.fixture
def frame() -> pd.DataFrame:
    rows = [
        ("1", "2014-03-01", "Fully Paid"),    # train
        ("2", "2016-02-01", "Fully Paid"),    # validation
        ("3", "2016-08-01", "Charged Off"),   # holdout
        ("10", "2016-11-01", "Current"),      # holdout (unlabelled kept)
        ("4", "2017-05-01", "Current"),       # replay
    ]
    return pd.DataFrame(
        {
            "id": [r[0] for r in rows],
            "issue_d": [pd.Timestamp(r[1]) for r in rows],
            "term": pd.Categorical([" 36 months"] * len(rows)),
            "loan_status": pd.Categorical([r[2] for r in rows]),
        }
    )


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "holdout.txt", tmp_path / "holdout.json"


def test_freeze_writes_sorted_ids_and_metadata(frame, paths):
    manifest, metadata = paths
    meta = freeze(frame, manifest, metadata)
    assert manifest.read_text().splitlines() == ["3", "10"]  # numeric sort
    assert meta["n_loans"] == 2
    assert len(meta["sha256"]) == 64


def test_freeze_refuses_overwrite(frame, paths):
    manifest, metadata = paths
    freeze(frame, manifest, metadata)
    with pytest.raises(FileExistsError, match="frozen"):
        freeze(frame, manifest, metadata)


def test_verify_passes_on_untouched_freeze(frame, paths):
    manifest, metadata = paths
    freeze(frame, manifest, metadata)
    assert verify(frame, manifest, metadata)["n_loans"] == 2


def test_verify_detects_manifest_tampering(frame, paths):
    manifest, metadata = paths
    freeze(frame, manifest, metadata)
    manifest.write_text("3\n")  # someone trims the holdout
    with pytest.raises(HoldoutAccessError, match="modified after freezing"):
        verify(frame, manifest, metadata)


def test_verify_detects_data_or_rule_drift(frame, paths):
    manifest, metadata = paths
    freeze(frame, manifest, metadata)
    drifted = frame.copy()
    drifted.loc[drifted["id"] == "2", "issue_d"] = pd.Timestamp("2016-09-01")  # moves into holdout
    with pytest.raises(HoldoutAccessError, match="differs from the frozen manifest"):
        verify(drifted, manifest, metadata)


def test_access_guard_blocks_unacknowledged_reads(frame, paths):
    manifest, metadata = paths
    freeze(frame, manifest, metadata)
    with pytest.raises(HoldoutAccessError, match="frozen until the final P6"):
        load_holdout_ids(manifest=manifest)


def test_access_guard_opens_with_explicit_acknowledgment(frame, paths):
    manifest, metadata = paths
    freeze(frame, manifest, metadata)
    ids = load_holdout_ids(
        i_understand_this_is_for_final_p6_evaluation=True, manifest=manifest
    )
    assert ids == ["3", "10"]
