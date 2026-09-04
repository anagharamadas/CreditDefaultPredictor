"""Training entrypoint units: protocol metrics arithmetic and lineage facts."""

import numpy as np
import pandas as pd
import pytest

from credit_default.tracking import LineageError, lineage_tags
from credit_default.train import evaluate


def test_evaluate_perfect_predictions():
    y = pd.Series([1, 0, 1, 0])
    p = np.array([0.9, 0.1, 0.8, 0.2])
    m = evaluate(y, p, label_coverage=0.82)
    assert m["pr_auc"] == pytest.approx(1.0)
    assert m["roc_auc"] == pytest.approx(1.0)
    assert m["label_coverage"] == 0.82  # coverage rides with every metric batch


def test_evaluate_constant_prior_scores():
    y = pd.Series([1, 0, 0, 0])
    p = np.full(4, 0.25)
    m = evaluate(y, p, label_coverage=1.0)
    assert m["pr_auc"] == pytest.approx(0.25)  # AP of a constant score = prevalence
    assert m["roc_auc"] == pytest.approx(0.5)  # no ranking information
    assert m["default_rate_labelled"] == 0.25


def test_evaluate_reports_the_whole_sensitivity_band():
    y = pd.Series([1, 0])
    p = np.array([0.9, 0.1])
    m = evaluate(y, p, label_coverage=1.0)
    for ratio in (3, 4, 5, 6, 8):
        assert f"expected_cost_at_{ratio}to1" in m
    assert m["expected_cost_at_5to1"] == 0.0  # perfect decisions cost nothing
    assert m["threshold_baseline"] == pytest.approx(1 / 6)


def test_lineage_tags_carry_the_reproducibility_facts():
    tags = lineage_tags()
    assert set(tags) == {"git_commit", "git_dirty", "raw_data_md5", "holdout_manifest_sha256"}
    assert len(tags["git_commit"]) == 40  # a real commit hash
    assert tags["raw_data_md5"] == "40d0463a883c602e3732b5f821a3dac7"  # matches the manifest
    assert tags["holdout_manifest_sha256"].startswith("b4272dd9")


def test_lineage_refuses_to_resolve_without_the_dvc_pointer(tmp_path):
    with pytest.raises(LineageError, match="DVC pointer missing"):
        lineage_tags(dvc_pointer=tmp_path / "nope.dvc")


def test_lineage_refuses_without_holdout_metadata(tmp_path):
    pointer = tmp_path / "x.dvc"
    pointer.write_text("outs:\n- md5: abc123\n")
    with pytest.raises(LineageError, match="holdout metadata missing"):
        lineage_tags(dvc_pointer=pointer, holdout_metadata=tmp_path / "nope.json")


def test_lineage_refuses_a_pointer_without_md5(tmp_path):
    pointer = tmp_path / "x.dvc"
    pointer.write_text("outs:\n- path: whatever.csv\n")
    with pytest.raises(LineageError, match="no md5"):
        lineage_tags(dvc_pointer=pointer)
