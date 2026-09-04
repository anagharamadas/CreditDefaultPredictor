# Changelog

Notable changes to this project. Format follows [Keep a Changelog](https://keepachangelog.com/);
entries are dated rather than semver-numbered until there is a releasable artifact
(expected at P7, first registered model).

This file records *what* changed; *why* lives in the charter revision notes and
[docs/adr/](docs/adr/README.md).

## [Unreleased]

### Added (P3 — via feature/p3-eval-protocol)
- `src/credit_default/splits.py`: deterministic vintage splits (train 2013–2015 36-mo,
  validation 2016-H1, holdout 2016-H2, replay 2017–2018) with the maturity gap enforced
  as a config assertion; measured audit table (train 546,018 @ 100% labelled).
- Holdout frozen: committed 152,838-ID manifest + sha256, tamper/drift-detecting
  verify(), and a spelled-out access-guard keyword for P6.
- `docs/EVAL_PROTOCOL.md` frozen pre-model: metric set, label-coverage rule,
  comparison rules, threshold policy §5.
- ADR-0003: cost matrix FN:FP = 5:1 [ASSUMED], 3:1–8:1 sensitivity; `threshold.py`
  derives θ ≈ 0.167 (never tuned). Research review tracked as issue #70 / BACKLOG 6.

### Added (P2 — via feature/p2-leakage-labels + feature/p2-completion)
- Leakage ledger over all 151 columns as importable code (`src/credit_default/ledger.py`)
  with generated `docs/LEAKAGE_LEDGER.md`; second pass resolved all 24 UNDECIDED
  (zero-UNDECIDED now test-enforced). Census: 81 FEATURE / 40 BANNED_POST /
  4 BANNED_UNDERWRITING / 7 METADATA / 18 EXCLUDED_SCOPE / 1 TARGET.
- Label truth table (`src/credit_default/labels.py`): nine statuses mapped explicitly,
  unknown statuses raise, exclusions counted. Labelled population 1,345,350 (19.96%).
- Vintage composition figure + notes (R1 detection artifact); class balance measured:
  v1 scope 546,018 loans at 14.07% default.
- R1/R2 re-scored 20→10 at P2 exit with evidence; Charter §3 target confirmed.

### Added (P1 — via feature/p1-data-contract)
- DVC tracking for all five raw files: committed `.dvc` pointers whose md5s match the
  manifest; no remote by design (solo, $0, re-downloadable data).
- `src/credit_default/ingest.py`: allowlist (28 candidate application-time columns) +
  explicit dtypes; drops the 33 footer rows with exact-count assertions; writes
  `data/interim/accepted.parquet` (60 MB derived working copy).
- `docs/SCHEMA.md`: measured profile of all 151 raw columns (generated, regenerable).
- `src/credit_default/contract.py`: executable Pandera contract — closed vocabularies,
  measured ranges with documented headroom, cross-column invariants, `strict=True`.
  First run caught 30 trace-null rows (29 in 2007 credit-policy legacy population).
- `docs/DATA_CONTRACT.md` (principles + amendment process), `docs/WALKTHROUGH.md`
  (plain-English per-phase record for interview preparation).
- Tests: ingest fixture suite + contract violation matrix + full-data validation.

## 2026-08-18

### Added
- ADR-0002: Python environment settled — the conda env `credit-default-predictor`
  is the project environment, with uv installing `uv.lock` into it via
  `UV_PROJECT_ENVIRONMENT`; no separate `.venv/`.
- `scripts/bootstrap_env.sh` — idempotent, reproducible environment bootstrap
  (create conda env → install uv → install activation hooks → `uv sync --frozen --inexact`
  → verify).

### Removed
- `.venv/` (689 MB) — superseded by the conda env per ADR-0002. Remains gitignored as a
  guard against it being recreated.

### Added (earlier same day)
- Agile execution structure on GitHub: 12 phase epics (#1–#12), 53 estimated task
  tickets with acceptance criteria, 7 sprint milestones with due dates
  (2026-08-19 → 2026-11-20); plan and working agreement in docs/PROJECT_PLAN.md.
- Pinned environment: `pyproject.toml` + `uv.lock` (uv, Python 3.12) covering the six
  locked tools — mlflow 3.15.1, dvc 3.67.1, pandera 0.32.1, prefect 3.8.3,
  fastapi 0.141.1, uvicorn 0.52.3 — plus pandas 2.3.3, pyarrow 25.0.1; dev group:
  pytest, ruff. **P0 definition of done complete.**
- ADR-0001: tool stack locked — MLflow, DVC, Pandera, Prefect, Postgres, FastAPI;
  drift monitoring (P10) and deploy target (P8) left open by design.
- LICENSE (MIT), CHANGELOG.md, ADR index, ARCHITECTURE.md stub.

### Changed
- Charter v0.3: §6.1 records the locked stack as a constraint, pointing at ADR-0001
  for rationale.

## 2026-07-23

### Added
- Initial commit: CHARTER.md (v0.2), RISK_REGISTER.md (v0.2), BACKLOG.md, README.md,
  data/README.md integrity manifest (md5 + row counts for all raw files), .gitignore.

### Changed
- Primary dataset switched from the Zenodo curated subset to the full Kaggle
  `wordsforthewise/lending-club` accepted-loans file (2.26M rows, 151 columns,
  2007–2018). Censoring policy and leakage exclusions become explicit project
  decisions instead of inherited curation. v1 scope fixed: 36-month loans, train on
  matured 2013–2015 vintages, replay 2016–2018 under label lag.
- Raw data laid out immutably under `data/raw/{kaggle,zenodo}/` and gitignored.
