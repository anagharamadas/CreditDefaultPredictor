# Credit Default Predictor — LendingClub

An MLOps-first portfolio project: predict whether a personal loan will default using only
information available at application time, then keep that model honest in production —
temporal (vintage) splits, a leakage-audited feature pipeline, experiment tracking, a
serving API with train/serve parity, drift monitoring via month-by-month historical
replay, and a human-in-the-loop retraining approval gate.

**The model is deliberately the least interesting part.** The evaluated signal is the
operational machinery around it.

## Status

Phase **P0 — charter & requirements** (of a P0–P12 roadmap). See:

- [CHARTER.md](CHARTER.md) — what is being built, the target definition, non-goals,
  constraints, and the HITL design requirement.
- [RISK_REGISTER.md](RISK_REGISTER.md) — ranked risks with mitigations, re-scored per phase.
- [BACKLOG.md](BACKLOG.md) — deliberately parked extensions.
- [ARCHITECTURE.md](ARCHITECTURE.md) — planned system design and load-bearing rules.
- [docs/adr/](docs/adr/README.md) — immutable decision records (the "why" behind each fork).
- [CHANGELOG.md](CHANGELOG.md) — dated record of notable changes.
- [data/README.md](data/README.md) — data provenance, integrity manifest, and layout.

## Headline design decisions so far

- **Dataset**: full Kaggle `wordsforthewise/lending-club` accepted-loans file
  (2.26M loans, 2007–2018, 151 columns). Chosen over a pre-cleaned academic subset so
  that censoring policy and leakage exclusion are explicit, auditable decisions of this
  project rather than inherited ones.
- **Target**: charged off vs fully paid, derived from `loan_status` by documented rule.
- **v1 scope**: 36-month loans; train on fully-matured 2013–2015 vintages; replay
  2016–2018 through the live API to observe genuine (not injected) drift under label lag.
- **Excluded by decision**: `grade`, `sub_grade`, `int_rate` (LendingClub's own
  underwriting outputs) and all post-origination columns (leakage).

## Setup

A conda environment supplies the Python 3.12 interpreter; [uv](https://docs.astral.sh/uv/)
installs every dependency into that same environment from `uv.lock`. There is no separate
`.venv/`. Rationale: [ADR-0002](docs/adr/0002-python-environment.md).

```bash
bash scripts/bootstrap_env.sh          # creates the env, installs uv, syncs uv.lock
conda activate credit-default-predictor
```

The script is idempotent — rerun it any time to repair or re-sync the environment. It also
installs a conda activation hook that exports `UV_PROJECT_ENVIRONMENT=$CONDA_PREFIX`, which
is what keeps uv installing into the conda env instead of creating `.venv/`.

Day-to-day, once activated:

| Task | Command |
|---|---|
| Re-sync after pulling | `uv sync --frozen --inexact` |
| Add a dependency | `uv add <pkg>` (never bare `pip install` — see ADR-0002) |
| Add a dev dependency | `uv add --dev <pkg>` |
| Check lock is in sync | `uv lock --check` |
| Tests / lint | `pytest` · `ruff check .` |

## Data

Raw data is not committed. Download the Kaggle distribution
(`wordsforthewise/lending-club`) and place the files per
[data/README.md](data/README.md), then verify the md5 hashes against its manifest.

## Attribution

- LendingClub loan data via Kaggle dataset `wordsforthewise/lending-club`.
- Benchmark subset: Ariza-Garzón, Sanz-Guerrero & Arroyo Gallardo, Zenodo,
  DOI 10.5281/zenodo.11295916 (CC-BY-4.0).
