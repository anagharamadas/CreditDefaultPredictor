# Project Charter — Credit Default Granting Model (LendingClub)

Status: DRAFT v0.4
Phase: P0 complete → P1
Date: 2026-08-18
Owner: Anagha Ramadas

Revision note (v0.3 → v0.4): time constraint corrected from ~40 h/week to the actual
4 h/day Mon–Fri (20 h/week); execution re-planned as seven 2-week sprints
(2026-08-19 → 2026-11-20, ~264 h capacity) tracked on GitHub. See docs/PROJECT_PLAN.md.

Revision note (v0.2 → v0.3): stack locked (§6.1); rationale in docs/adr/0001-tool-stack.md.

Revision note (v0.1 → v0.2): primary dataset switched from the Zenodo curated subset to
the full Kaggle `wordsforthewise/lending-club` distribution. Rationale: the raw file
contains `term` and the censored (Current) loans, converting the v0.1 dataset's two
inherited structural defects — a missing maturity field and hidden survivorship bias —
into explicit design decisions owned by this project. The cost is a full 151-column
leakage audit in P2, which was the highest-value planned work anyway. The Zenodo file is
retained as a cross-check benchmark because published results exist for it.

---

## 1. The decision this model serves

**Grant or decline a personal loan application at the moment of application.**

The model outputs a probability of default for a single loan application, using only
information a lender would hold at origination. That probability feeds a threshold-based
grant/decline decision, and secondarily a risk-ranking used for portfolio reporting.

This is a *granting model*, not a pricing model, not a collections model, and not a
portfolio expected-loss model. `grade`, `sub_grade` and `int_rate` are present in the raw
file but are **excluded by our own decision**: they are outputs of LendingClub's
underwriting process, and including them would change the research question from
"predict default" to "predict LendingClub's opinion of the borrower". This exclusion is
now a project decision to defend, not a property inherited from a curator.

Everything downstream in this project is justified against this sentence. If a proposed
feature, metric, or component does not serve the grant/decline decision, it is out of scope.

## 2. Prediction unit

One loan application, scored once, at origination. No re-scoring over the life of the loan.
No borrower-level aggregation across multiple loans.

## 3. Dataset and target definition (CONFIRMED at P2 exit, 2026-09-04 — see
docs/LEAKAGE_LEDGER.md, docs/CLASS_BALANCE.md; §3.2's working assumptions held)

### 3.1 Dataset

Primary: `accepted_2007_to_2018Q4.csv` from the Kaggle `wordsforthewise/lending-club`
distribution. Measured facts (2026-07-23, this machine, not quoted from any brief):

- 2,260,701 rows × 151 columns; issue dates Jun 2007 – Dec 2018.
- 33 footer/junk rows with null `id`/`term`/`loan_status` — dropped at ingest.
- Loan statuses are frozen at the distribution's snapshot (file dated Dec 2019);
  no outcome information exists beyond that point.
- md5 and row counts recorded in `data/README.md`. Raw files are immutable.

Secondary (out of v1 scope): `rejected_2007_to_2018Q4.csv`, 27,648,742 rows × 9 columns,
no outcome label. Usable only for the reject-inference / selection-bias analysis parked in
BACKLOG.md. Its `Risk_Score` column's provenance is unverified.

Benchmark: the Zenodo curated subset (Ariza-Garzón et al., CC-BY-4.0, 1,347,681 rows),
derived from this same Kaggle distribution. Kept for cross-checking against published
results; no longer the training source.

### 3.2 Target

Binary `default`, derived by **our own rule** from `loan_status`:

- `1` = `Charged Off`
- `0` = `Fully Paid`
- Transitory states (`Current`, `In Grace Period`, `Late (16-30 days)`,
  `Late (31-120 days)`) carry no terminal outcome and are excluded from training by our
  documented censoring policy (§3.3) — not by a curator's silent filter.
- `Default` status (40 loans) and the legacy `Does not meet the credit policy` statuses
  (2,749 loans, pre-2010 policy regime): mapping decided and justified in P2. Working
  assumption: map `Default` to charged off [ASSUMED]; exclude credit-policy legacy rows.

### 3.3 Censoring policy and v1 scope (measured, 2026-07-23)

Chosen policy: **matured vintages only, restricted to 36-month term loans.**

- Training window: 36-month loans issued 2013–2015. ~546k loans, ≥99.9% resolved —
  effectively zero censoring in training labels.
- Replay window: 2016–2018, streamed month-by-month through the serving API in P10.
  Resolution rates there are 71.8% (2016), 40.1% (2017), 12.0% (2018): labels arrive
  late by construction. This is not a defect to hide; monitoring performance **under
  label lag** is the P10 story.
- 60-month loans are excluded from v1: vintages after 2013 are not fully matured
  (2014: 82.9% resolved, 2015: 67.1%). Their default rates also run ~2× the 36-month
  rate, so mixing terms without maturity handling would corrupt the label. Revisit via
  the survival-framing entry in BACKLOG.md.

Measured class balance in the training window (36-month, resolved): 12.3% (2013),
13.7% (2014), 14.9% (2015) charged off. Among resolved 36-month loans the rate climbs to
~20% by 2016–17 — the drift the replay is designed to surface.

VERIFY IN P2: full leakage ledger over all 151 columns; exact status-mapping decisions;
default rate by `issue_d` month; discontinuities near the snapshot boundary.

## 4. Success metrics

### 4.1 Technical

| Metric | Role | Why |
|---|---|---|
| PR-AUC | Primary | Default is the minority class (~13-15% in the training window); precision-recall is the honest view under imbalance. |
| ROC-AUC | Secondary | Comparable to published work on this data; threshold-independent ranking. |
| Brier score | Calibration | A granting decision needs a probability that means something, not just a rank. |
| Reliability curve | Calibration | Visual evidence of calibration, reported per vintage. |
| Expected cost at operating threshold | Business | Derived from an explicitly stated cost matrix. See 4.3. |

All metrics are reported on LATER vintages than the training window. Never on a random split.

### 4.2 Operational (the phases that carry the portfolio signal)

| Metric | Target |
|---|---|
| Reproducibility | Any logged run reproducible from run ID alone: data hash + code commit + params + split manifest hash. |
| Train/serve parity | Enforced by a test asserting identical transform output on a fixed sample. |
| Drift detection latency | Number of replayed months between a genuine distribution shift and an alarm firing. Target set in P10 after baselining. |
| Retrain approval cycle | Alarm to approved-or-rejected candidate, fully recorded, no silent promotion. |
| Rollback time | Time to restore the previous registry stage. Demonstrated, not asserted. |

### 4.3 Cost matrix (placeholder — P3 finalises)

- False negative: default predicted as repaid. Cost approximates outstanding principal at
  charge-off. Placeholder assumption to be written in P3.
- False positive: repaid loan declined. Cost approximates forgone interest margin.

These numbers are ASSUMED, not observed. They must be written down explicitly and their
sensitivity tested, because the operating threshold is entirely determined by their ratio.

## 5. Non-goals

Written explicitly so they can be pointed at when scope pressure appears.

1. Beating a published AUC on this dataset. Not the evaluated signal.
2. Using any post-origination information. The raw file **contains** roughly 40+
   post-origination columns (payments, recoveries, hardship, settlement, last FICO
   pulls). They are banned column-by-column in the P2 leakage ledger, with written
   justification each. "The curator removed them" is no longer available as an excuse;
   the audit is ours.
3. Using `grade`, `sub_grade` or `int_rate` as features (see §1).
4. Claiming compliance with any named regulation. Not a lawyer, not a compliance officer,
   not legal advice.
5. NLP on `desc` / `title` / `emp_title` before P11 exists. Parked in BACKLOG.md.
6. Reject-inference modelling on the rejected-loans file in v1. Parked in BACKLOG.md.
7. Distributed compute. The working file is 1.6 GB and fits in 64 GB RAM with an order
   of magnitude to spare. Spark here is a negative signal.
8. Hyperparameter search beyond a small, time-boxed budget.
9. Transferring the model to the Indian lending market. Different bureau, different
   regulatory regime, different features. The transferable asset is the MLOps
   architecture, not the model. Documented as such in P12.

## 6. Constraints

| Constraint | Value |
|---|---|
| Compute | MacBook Pro M2 Max, 64 GB. Full accepted file loads in memory with headroom; dtype discipline at ingest anyway. |
| Budget | USD 20 total. Default posture is local-first: Docker Compose, local tracking backend, local Postgres. Cloud is a short-lived end-stage demo at most. |
| Time | 4 h/day Mon–Fri (20 h/week); seven 2-week sprints, 2026-08-19 → 2026-11-20, ~264 h capacity / ~232 h planned. Sprint plan: docs/PROJECT_PLAN.md. |
| Operator level | Junior, 1-2 years. Phases are sized to be individually completable, not heroic. |
| Data licence | Kaggle `wordsforthewise/lending-club` distribution — verify its stated licence on the Kaggle page before the repo is made public [VERIFY]. Zenodo benchmark is CC-BY-4.0; attribution mandatory if used. Raw data is never committed to the repo. |

Suggested effort split, to be defended against drift:
P0-P3 ~25%, P4-P7 ~25%, P8-P12 ~50%.

### 6.1 Locked stack

Locked at P0. Rationale, alternatives rejected, and accepted tradeoffs are recorded in
docs/adr/0001-tool-stack.md (not repeated here). Every version pinned at install time and
verified against that version's own docs before use.

| Slot | Tool | Status |
|---|---|---|
| Experiment tracking | MLflow (local backend) | LOCKED |
| Data versioning | DVC | LOCKED |
| Data validation | Pandera | LOCKED |
| Orchestration | Prefect | LOCKED |
| Prediction store | Postgres | LOCKED |
| Serving | FastAPI | LOCKED |
| Drift monitoring | undecided (Evidently / NannyML / custom) | OPEN — decide by P10 |
| Containerisation | Docker Compose (implied by local-first) | LOCKED |
| Deploy target | undecided | OPEN — decide by P8 |

## 7. Roles and the human-in-the-loop gate

Solo project, but the artifact must record the separation of duties, because that
separation is the point of the HITL narrative.

| Role | Responsibility |
|---|---|
| ML Engineer | Builds pipeline, trains candidates, produces the evidence pack. |
| Model Approver | Reviews the evidence pack against a written checklist and approves or rejects promotion. Cannot be bypassed by automation. |
| Operator | Executes rollback. |

Approval evidence pack must contain, at minimum: candidate vs incumbent metrics on the
frozen protocol, calibration comparison, fairness slice comparison, drift evidence that
triggered the retrain, data version, and code commit.

No path exists in which a model reaches the serving stage without a recorded human
approval decision. That constraint is a design requirement, not a preference.

## 8. Known structural limitations (carried into the model card)

1. **Right-censoring in the replay window — visible and managed.** Replay-vintage labels
   mature over time (12–72% resolved depending on year). Any performance measured there
   mixes genuine drift with label immaturity, and must be reported under an explicit
   label-lag framework in P10. This replaces v0.1's top limitation (hidden survivorship
   bias from a curator's filter): the same phenomenon, but now observable and owned.
2. **v1 is 36-month loans only.** 60-month behaviour (systematically riskier, ~2× default
   rate) is out of scope and the model must not be applied to it. Stated in the model card.
3. **Selection bias, inherited.** The training data contains funded loans only. The
   rejected-applications file exists and makes the bias measurable, but correcting for it
   (reject inference) is out of v1 scope; documented as a limitation.
4. **Self-reported income.** `annual_inc` is borrower-declared; verification status is a
   separate column with its own timing questions for the P2 ledger.
5. **Outcome snapshot.** All statuses frozen at the distribution's snapshot (late 2019).
   No claim about post-snapshot performance of any loan.
6. **US market, 2007-2018.** No claim of applicability to any other market or period.

## 9. Definition of done for P0

- [x] This charter committed to the repo.
- [x] RISK_REGISTER.md committed.
- [x] Repo initialised; raw data laid out immutably under `data/raw/` and gitignored.
- [x] Datasets hashed (md5) and recorded in `data/README.md`; Zenodo file verified
      against its published md5.
- [x] Pinned environment (uv lockfile, Python 3.12) committed.
- [x] Stack decisions either locked or explicitly deferred with a date (§6.1, ADR-0001).
