# Changelog

Notable changes to this project. Format follows [Keep a Changelog](https://keepachangelog.com/);
entries are dated rather than semver-numbered until there is a releasable artifact
(expected at P7, first registered model).

This file records *what* changed; *why* lives in the charter revision notes and
[docs/adr/](docs/adr/README.md).

## [Unreleased]

### Added (P7 — via feature/p7-packaging)
- `credit-default-granting` v1 registered from the ADR-0004 run; version tags chain
  to full lineage. Alias lifecycle (staging/champion) replaces MLflow-3-removed
  stages, adaptation recorded; promotion and rollback demonstrated as alias moves
  (self-cleaning lifecycle test). Standalone load via registry address scored the
  parity fixture.
- `docs/MODEL_CARD.md` for v1: intended use, prohibited uses, training data + label
  rule, protocol metrics with coverage, measured limitations (drift
  under-prediction, resolved-subset bias), R7 fairness framing, maintenance
  obligations. Consistency-pinned by test.

### Added (P6 — via feature/p6-selection)
- Evaluation harness scoring tracked artifacts on later vintages; comparisons are
  themselves lineage-tagged runs. Holdout guarded at this layer (acknowledgment +
  manifest verify + ID cross-check).
- Calibration assessed: isotonic method built window-honest and REJECTED on evidence
  (base-rate drift is the miscalibration; a within-window calibrator can't fix it).
- Decision policy (generated doc + tracked run): 5:1 declines 38.7% / cost 0.610 /
  saving 33.5%; band swings declines 17–61% (the issue-#70 case, quantified).
- Slice report: 39 slices, 8 flagged coherently; no state/income slice flagged; R7
  framing throughout.
- ADR-0004: LightGBM uncalibrated selected — margin bootstrap-real
  (+0.0209, CI [+0.0177,+0.0242]); holdout opened ONCE for the final report
  (PR-AUC 0.3767, coverage 0.604 stated; ECE drift-worsened to 0.064, accepted and
  routed to P10/P11). docs/P6_FINAL_REPORT.md.

### Added (P5 — via feature/p5-baselines)
- MLflow v3.15.1 tracking server in Docker Compose (sqlite volume, restart-proven);
  `tracking.py` with fail-if-untracked posture; `services` pytest marker.
- Three protocol-evaluated baselines: prior (PR-AUC 0.1835 = prevalence floor),
  logistic (0.3236, cost 0.625/loan @5:1), LightGBM 4.7.0 zero-search (0.3446,
  0.610). Coverage logged beside every metric; holdout untouched.
- Lineage enforced: `start_tracked_run()` raises without git commit + raw-data md5 +
  manifest sha. Reproduce-from-run-ID demonstrated bit-exact (delta 0.0) and
  documented in docs/REPRODUCIBILITY.md.
- Prefect DAG (`flows.py`): ingest → contract gate → trainings; flow-run metrics
  matched standalone runs exactly.
- Fixed: expected-cost index-alignment bug (silent zero cost) with regression test.
- lightgbm 4.7.0 pinned (macOS: `brew install libomp`, in README).

### Added (P4 completion — via feature/p4-completion)
- Transforms finalised: missing-indicator columns (28 on real data), dti clipped to
  [0,100], zip_code frequency-encoded (custom transformer; unseen→0), StandardScaler
  on the numeric branch. Real matrix: 184 features.
- `TrainWindowGate`: pipeline fit() refuses rows issued outside 2013-01..2015-12 —
  fit-on-train-only enforced by construction, transform unrestricted.
- Determinism finalised: cross-process equality under different hash seeds, pickle
  round-trip parity (the P7/P8 artifact boundary), real-data double-build equality.
- `realdata` pytest marker; CI mode `-m "not realdata"` (85 tests, no raw data).
- Parity fixture regenerated inside the train window and re-pinned; catalogue
  regenerated (FINALISED); pipeline flow diagram committed (docs/figures/).
- WALKTHROUGH P4 section. **P4 exit criteria met.**

### Added (P4 part 1 — via feature/p4-feature-pipeline)
- Ingest allowlist now derived from the ledger: 84 columns (81 FEATURE + essentials);
  contract extended with 56 measured-bound columns; rebuilt 186 MB interim parquet
  passes all checks on 2,260,668 rows.
- Feature pipeline skeleton (`src/credit_default/features/`): single transform path,
  ledger-partition tests, serving-safe one-hot, `credit_history_months` engineered;
  50k-row smoke -> 155-feature matrix.
- Train/serve parity harness: committed sha256-pinned 64-row synthetic fixture,
  `serving.py` JSON converters, byte-identical batch-vs-per-request tests.
- `docs/FEATURE_CATALOGUE.md` (generated; sync-tested against the code) — started,
  finalised at #32.
- scikit-learn 1.9.0 added to the locked environment.

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
