# Reproducibility — demonstrated, not asserted

Charter §4.2 promises: *any logged run reproducible from run ID alone*. This page
records the machinery and the demonstration.

## What a run ID buys you

Every training run opens through `tracking.start_tracked_run()`, which gathers and
validates these facts BEFORE the run starts (a run that cannot resolve them refuses
to open — `LineageError`):

| Tag | Meaning | Source |
|---|---|---|
| `git_commit` (+ `git_dirty`) | exact code | `git rev-parse HEAD` |
| `raw_data_md5` | exact bytes trained on | the committed DVC pointer |
| `holdout_manifest_sha256` | exact split world | the frozen manifest metadata |

Together with `uv.lock` (exact libraries) and the deterministic pipeline (#31),
the run ID names an exact, restorable world.

## The demonstration (2026-09-04)

Fresh `baseline-logistic` run from a clean tree, then
`scripts/reproduce_run.py <run_id>` — which verifies the current environment
matches the recorded lineage (and refuses with instructions if not), re-executes
the same entrypoint tagged `reproduction_of=<id>`, and compares protocol metrics:

```
reproducing 'logistic' from run 442c153d14704a54a31bded3e5698abf …

metric                       original   reproduced      delta
pr_auc                     0.32359605   0.32359605    0.0e+00
roc_auc                    0.69538229   0.69538229    0.0e+00
brier                      0.13999054   0.13999054    0.0e+00
expected_cost_at_5to1      0.62478585   0.62478585    0.0e+00

reproduction PASSED (tolerance 1e-09); new run: 2834b1b4ce3545d2845203cbdd75f3d2
```

Delta 0.0 across the board — bit-exact, not merely "close".

## To reproduce any run yourself

```bash
PYTHONPATH=src python scripts/reproduce_run.py <run_id>
```

If your checkout or data differ from the run's lineage the script refuses and
prints the fix (`git checkout <commit> && dvc checkout`). A run tagged
`git_dirty=yes` is reproducible only up to its commit — the script says so and
proceeds with that caveat; keeping trees clean for runs that matter is the
discipline this tag exists to encourage.

## Boundaries (stated, not hidden)

- Reproduction is verified on the same machine/architecture; cross-platform
  bit-exactness (different BLAS, different CPU) is NOT claimed.
- LightGBM runs set `deterministic=true, force_row_wise=true, seed=42` to hold the
  same guarantee at some speed cost.
