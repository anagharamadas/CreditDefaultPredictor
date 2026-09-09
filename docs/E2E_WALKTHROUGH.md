# End-to-end walkthrough — P9 integration buffer

Run 2026-09-09 (ticket #53). Every component had passing tests; this exercise asks a
different question — **do they still work when connected?** Components that pass in
isolation can still disagree at the seams, and the seams are where nobody is looking.

Two gaps found, both filed. Neither would have been caught by a unit test, and both
would have surfaced at a much worse moment: one during P11's rollback demonstration,
one six hours into a P10 replay.

## The chain, as exercised

| # | Step | Result |
|---|---|---|
| 1 | Raw data integrity (`dvc status`) | up to date |
| 2 | Services health | api, mlflow, postgres all healthy |
| 3 | **Rebuild the interim parquet from the raw 1.6 GB file** | 186 MB, 84 columns, **26 s** |
| 4 | Frozen holdout re-verified against the rebuilt data | 152,838 loans, hash matches |
| 5 | Train via the Prefect flow | contract gate passed, run logged, **28 s** |
| 6 | Quality gate: retrained candidate vs incumbent | **blocked** — see below |
| 7 | Register + promote a new champion version | v3, alias moved |
| 8 | Does the running service notice? | **no — gap 1** |
| 9 | Score while stale | recorded under the *old* version |
| 10 | Restart, re-check | picks up v3 |
| 11 | Score + verify the stored row | correct version, correct score |
| 12 | Per-request latency | 32 ms median → **gap 2** |

Registry and prediction store were restored afterwards: champion back to v1 (the run
ADR-0004 pins), v3 deleted, walkthrough rows removed.

## Two results worth keeping

**Determinism survives a full retrain.** Step 5 retrained LightGBM from the freshly
rebuilt parquet, and the quality gate measured the difference against the incumbent
as **exactly 0.00000, CI [0.00000, 0.00000]**. Same data, same code, same seed →
byte-identical model. The gate then blocked it as a tie, which is the correct
behaviour: do not churn a live model for no gain.

**The frozen holdout reproduces from raw.** Step 4 rebuilt the parquet from scratch
and the manifest still verified — so the 152,838 held-out loan IDs are a function of
the raw data and the split rules, not of any intermediate file that happened to be
lying around.

## Gap 1 — the service caches its champion (issue #79)

The API resolves `@champion` once at startup and never re-checks. Moving the alias
has no effect on a running service:

```
registry:   @champion -> v3
GET /ready: {"model_version": 1}     <- stale
POST /score: recorded as version 1
(restart)
GET /ready: {"model_version": 3}
```

Two reasons this matters more than it first appears:

1. **Rollback is P11's emergency path.** If rolling back means "move the alias *and*
   restart", then the alias move alone is not a rollback — and the rehearsed
   one-line gesture from P7 is incomplete.
2. **The audit trail can contradict the registry.** The walkthrough produced two
   stored rows with identical inputs and identical scores under *two different*
   `model_version` values. A prediction store whose version field can be wrong
   undermines the reason it exists.

Filed for P11 with four options weighed (per-request resolution, timed polling,
explicit reload endpoint, or documenting restart as the mechanism). Whichever is
chosen, `/ready` should expose the alias it resolved and when — staleness should be
observable, not invisible.

## Gap 2 — replay throughput (issue #80)

32 ms per request × 665,090 replay loans ≈ **5.9 hours** sequentially.

The danger is subtle: at six hours a run, the replay stops being repeatable, and the
tempting shortcut is to compute drift offline in pandas — quietly abandoning the
point, which is drift measured on predictions that actually went through the live
service. Filed for P10 with the options (concurrency, batch endpoint, sampling) and
the constraint that must survive whichever is chosen: one stored row per scored loan,
through the real API.

## Minor observation

Registry version numbers are monotonic and leave gaps when versions are deleted — an
earlier test's v2 was removed, so the next registration became v3. Version number is
not a count of promotions; anything reading it should not assume otherwise.

## Timings, for the runbook

| Stage | Duration |
|---|---|
| Raw CSV → typed parquet | 26 s |
| Train one model (546k rows) via the flow | 28 s |
| Quality gate (500 bootstrap resamples, 140k rows) | ~90 s |
| Cold start to first scored request | 8 s |
| Single score | 32 ms |
