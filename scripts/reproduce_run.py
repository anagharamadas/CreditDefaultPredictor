"""Reproduce a training run from its run ID alone (Charter §4.2, ticket #36).

Given a run ID, this script:
1. fetches the run's lineage tags and parameters from MLflow;
2. VERIFIES the current environment matches the recorded lineage — same git commit,
   same raw-data md5 (from the DVC pointer), same holdout-manifest sha — and refuses
   to proceed on any mismatch (that is the point: the run ID names an exact world);
3. re-executes the same model entrypoint, producing a new run tagged
   `reproduction_of=<original>`;
4. compares the protocol metrics and passes only on (near-)exact agreement.

Run:  PYTHONPATH=src python scripts/reproduce_run.py <run_id>
"""

from __future__ import annotations

import sys

import mlflow

from credit_default.tracking import lineage_tags, setup_tracking
from credit_default.train import RUNNERS, prepare_data

TOLERANCE = 1e-9
COMPARED_METRICS = ("pr_auc", "roc_auc", "brier", "expected_cost_at_5to1")


def main(run_id: str) -> int:
    setup_tracking()
    original = mlflow.get_run(run_id)
    recorded = {k: original.data.tags.get(k, "?") for k in
                ("git_commit", "git_dirty", "raw_data_md5", "holdout_manifest_sha256")}
    model = original.data.params.get("model")
    if model not in RUNNERS:
        print(f"run {run_id} has no reproducible model param (got {model!r})")
        return 2

    current = lineage_tags()
    mismatches = [
        f"  {key}: recorded {recorded[key][:12]}… vs current {current[key][:12]}…"
        for key in ("git_commit", "raw_data_md5", "holdout_manifest_sha256")
        if recorded[key] != current[key]
    ]
    if mismatches:
        print("environment does not match the recorded lineage — cannot reproduce here:")
        print("\n".join(mismatches))
        print(f"fix: git checkout {recorded['git_commit'][:12]} && dvc checkout")
        return 2
    if recorded["git_dirty"] == "yes":
        print("note: original run was made from a dirty tree; the commit alone may not "
              "pin its exact code state. Proceeding — judge the comparison accordingly.")

    print(f"reproducing {model!r} from run {run_id} …")
    data = prepare_data()
    with_tag = RUNNERS[model]
    from credit_default import tracking

    original_start = tracking.start_tracked_run

    def tagged(run_name, family, extra_tags=None):
        return original_start(run_name, family, (extra_tags or {}) | {"reproduction_of": run_id})

    tracking.start_tracked_run = tagged
    import credit_default.train as train_module

    train_module.start_tracked_run = tagged
    try:
        new_id = with_tag(*data)
    finally:
        tracking.start_tracked_run = original_start
        train_module.start_tracked_run = original_start

    reproduced = mlflow.get_run(new_id)
    print(f"\n{'metric':<24} {'original':>12} {'reproduced':>12} {'delta':>10}")
    ok = True
    for key in COMPARED_METRICS:
        a = original.data.metrics[key]
        b = reproduced.data.metrics[key]
        delta = abs(a - b)
        ok &= delta <= TOLERANCE
        print(f"{key:<24} {a:>12.8f} {b:>12.8f} {delta:>10.1e}")
    print(f"\nreproduction {'PASSED' if ok else 'FAILED'} "
          f"(tolerance {TOLERANCE:g}); new run: {new_id}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
