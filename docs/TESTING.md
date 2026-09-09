# Testing strategy

Counts measured 2026-09-09: **148 tests**, of which **139 run in CI** (9 need
something CI does not have). Full local suite: ~35s with services up, ~5s without.

## The idea the suite is built on

Every promise this project makes in prose has a test that can fail. Not "we test the
code" — *the documented guarantees are the test list*. A reader can go down the
charter and find, for each claim, the thing that breaks if it stops being true:

| Promise (where it is made) | What fails if it stops being true |
|---|---|
| Only audited columns reach the model (LEAKAGE_LEDGER) | `test_features.py` smuggles `total_pymnt` in and asserts it is dropped; `test_ledger.py` cross-guards the ingest allowlist against the ban list |
| Training never learns from outside its window (Charter §4.2) | `test_features.py` fits on 2016 and 2012 rows and requires a raise |
| Training and serving transform identically (Charter §4.2) | `test_parity.py` sends one fixture down both paths through a real JSON round trip and demands byte-identical matrices |
| Runs are reproducible (Charter §4.2) | `test_determinism.py` compares two interpreters with different `PYTHONHASHSEED`, and the pickle boundary |
| The holdout stays sealed until P6 (Charter §3.3) | `test_holdout.py` tampers with the manifest and requires detection; `test_evaluation.py` requires the acknowledgment |
| The threshold is derived, never tuned (EVAL_PROTOCOL §5) | `test_decision_policy.py` greps the module and forbids score-maximising statistics |
| Documents match the code that generates them | `test_catalogue.py` compares the committed file to the renderer's output, character for character |
| A decision that cannot be recorded is not returned (store.py) | `test_api.py` + the live stop-Postgres check |

If you add a guarantee to a document, add its test. If you cannot think of the test,
the guarantee is probably a wish.

## Tiers, and where each runs

CI is not "the tests, in the cloud". It is the tests **without a developer's local
advantages** — fresh clone, no raw data, no Docker, no conda env, no shell habits.
That difference is the point: it is what catches a pass that only held on one
machine.

| Tier | What it proves | Runs in CI |
|---|---|---|
| 0 — environment | `uv.lock` alone builds the environment; `pyproject` has not drifted from it | ✅ |
| 1 — lint | `ruff` over `src`, `tests`, `scripts` | ✅ |
| 2 — suite | 139 tests against committed fixtures | ✅ |
| 3 — smoke | the real entrypoints run as a *program*, not a test subject (`scripts/ci_smoke.py`) | ✅ |
| 4 — doc sync | regenerate the ledger and catalogue; any diff fails | ✅ |
| 5 — model quality gate | a candidate model beats the incumbent | ❌ — see below |

## What CI deliberately cannot do, and why that is stated rather than faked

Nine tests are excluded from CI by marker, because the runner genuinely lacks what
they need. Pretending otherwise would be worse than the gap.

| Marker | Count | Needs | Why not in CI |
|---|---|---|---|
| `realdata` | 3 | `data/interim/accepted.parquet` | Derived from a 1.6 GB DVC-tracked file that is never committed |
| `services` | 7 | MLflow + Postgres via Compose | Requires the running stack; two tests carry both markers |

```bash
pytest -m "not realdata and not services"   # what CI runs
pytest                                       # everything, locally, with the stack up
```

The **model quality gate** is the larger honest gap. It compares a candidate against
the registered incumbent on real validation data — so it cannot run on a machine with
neither. The split we chose:

- its **rules** are a pure function (`quality_gate.decide`) and are unit-tested in CI —
  9 tests covering a clear win, a noisy tie, an outright regression, ranking bought
  with worse calibration, and the fail-closed exit code;
- its **execution** happens where the models live: run by hand today, wired into the
  retraining flow in P11.

A CI badge therefore means "the code is sound", not "the model is approved". Those are
different claims and the project keeps them apart on purpose.

## Gate criteria

Two gates block promotion, and they answer different questions. Both must pass.

**Gate 1 — quality (mechanical, no judgement).** `quality_gate.py`, rules fixed in
EVAL_PROTOCOL §3 before any model existed:

1. PR-AUC must improve *beyond noise* — the 95% month-stratified bootstrap interval of
   the difference lies entirely above zero. A higher number alone is not enough.
2. Brier must not degrade beyond noise — blocks buying ranking with worse
   probabilities, which would break a threshold derived *from* probabilities.
3. Ties go to the incumbent. Do not swap a live model for noise.

Exit codes: `0` may proceed, `1` blocked, `2` could not evaluate. **`2` is a refusal,
not a pass** — a gate that withholds approval must treat "cannot check" as "no".

**Gate 2 — human (judgement, P11).** Asks what the metrics cannot see: does the drift
evidence support retraining now, do the fairness slices look acceptable, is the cost
assumption still the one we want? Recorded with its evidence pack. A model reaches
serving only after both.

## Conventions

- **Fixtures are tiny, synthetic and derived.** The 64-row `parity_sample.csv` is
  generated from the contract's own category sets and ranges, so a schema change
  updates it rather than breaking it. Its sha256 is pinned: silent regeneration fails.
- **Shared fixtures live in `conftest.py`**, injected by name. Test modules never
  import each other — that made the suite depend on how it was invoked, and it broke
  under plain `pytest` while passing under `python -m pytest`.
- **Attack your own defences.** The most valuable tests here try to do the forbidden
  thing: smuggle a banned column, fit outside the window, tamper with the manifest,
  peek at the holdout.
- **Pin decisions, not just behaviour.** `COST_FN == 5.0` and "zero UNDECIDED columns"
  are asserted so that changing a *decision* breaks the build and demands a new ADR.
- **Tests that write real state clean up after themselves** — the stack tests tag
  their traffic `X-Source: pytest-stack` and delete it, leaving the prediction store
  empty after a full run.

## Running it

```bash
pytest -q                                   # everything (needs stack + data)
pytest -m "not realdata and not services"   # the CI subset, ~5s, no dependencies
ruff check src tests scripts                # lint
PYTHONPATH=src python scripts/ci_smoke.py   # entrypoints as a program
PYTHONPATH=src python -m credit_default.quality_gate <run_id>   # the model gate
```
