# Model Card — credit-default-granting v1

Registry: `models:/credit-default-granting@champion` (v1) · Source run:
`e299b8e7489e4e9186b3680c39b45166` (bit-reproducible from that ID —
docs/REPRODUCIBILITY.md) · Selection: [ADR-0004](adr/0004-model-selection.md) ·
Card date: 2026-09-05. A P11-approved retrain produces a **new** card version;
this one describes v1 only.

## 1. Model details

LightGBM 4.7.0 classifier behind the project's single feature pipeline
(84 audited input columns → 184 features: median-impute + missing indicators +
standardise, one-hot categoricals with unknown→zeros, zip frequency encoding,
`credit_history_months`), packaged as ONE artifact. Fixed zero-search
hyperparameters (Charter non-goal 8). Uncalibrated **by evidenced decision** —
an isotonic calibrator was built, evaluated, and rejected (#39 / ADR-0004).

## 2. Intended use

**Rank-order and score 36-month US personal-loan applications for a
grant/decline decision at application time**, thresholded per the derived policy
(θ = 0.1667 under the **[ASSUMED]** FN:FP = 5:1 matrix, ADR-0003; sensitivity band
3:1–8:1 reported in docs/DECISION_POLICY.md; ratio under review, issue #70).
Secondarily: portfolio risk-ranking for reporting.

Operated with a human-in-the-loop lifecycle (Charter §7): the model never
retrains or promotes itself; drift alarms produce candidates for recorded human
approval, with a rehearsed rollback path.

## 3. Prohibited uses

- **60-month loans** — excluded from v1 by measured censoring (their vintages are
  unresolved in the data window; default profile ~2× the 36-month book).
- **Any market other than US, or any era far from 2013–2018** — no claim made.
- **Pricing, collections, or portfolio expected-loss estimation** — this is a
  granting model; those are different targets (Charter §1).
- **Fully automated adverse decisions without human accountability** — the HITL
  design is a requirement, not decoration.
- **Any compliance claim** — nothing here certifies fairness or regulatory
  conformance; see §6.

## 4. Training data & label

Kaggle `wordsforthewise/lending-club` accepted-loans file (md5-pinned via DVC).
Training population: **546,018 loans, 36-month term, issued 2013-01–2015-12,
14.07% default rate, 100% label coverage** (every training loan ran its full term
inside the observed window — enforced by an assertion, not assumed).

Label: `Charged Off`/`Default` → 1, `Fully Paid` → 0, transitory and
credit-policy-legacy statuses excluded with counted reasons (labels.py truth
table). LendingClub's own underwriting outputs (`grade`, `sub_grade`, `int_rate`,
`installment`) are excluded **by decision**; ~40 post-origination columns are
banned as leakage (docs/LEAKAGE_LEDGER.md).

## 5. Evaluation (frozen protocol; coverage stated always)

| Split | Coverage | PR-AUC | ROC-AUC | ECE | Cost/loan @5:1 |
|---|---|---|---|---|---|
| Validation 2016-H1 | 0.821 | 0.3446 | 0.7085 | 0.0269 | 0.610 |
| Holdout 2016-H2 (opened once) | 0.604 | 0.3767 | 0.6914 | 0.0636 | 0.701 |

Selection margin vs logistic regression: +0.0209 PR-AUC, 95% CI
[+0.0177, +0.0242] (month-stratified bootstrap). At the baseline threshold the
policy declines ~39% of validation applicants; the declined pool defaults at
~2.7× the funded book's rate. Full tables: docs/P6_FINAL_REPORT.md,
docs/DECISION_POLICY.md.

## 6. Known limitations (Charter §8, carried over, plus measured findings)

1. **Under-prediction under drift** — the model carries its 2013–15 base rate
   (14%) into riskier later vintages (18%+): mean predicted 0.157 vs observed
   0.184 on validation; ECE grows 0.027 → 0.064 into 2016-H2, monotonically by
   month. No within-window fix exists (#39); this is a standing monitoring
   obligation (P10) and the core retraining trigger (P11).
2. **Evaluation-label bias** — 2016+ metrics are computed on the resolved
   (fast-resolving, non-representative) subset; every number above is honest only
   WITH its coverage figure (docs/VINTAGE_NOTES.md).
3. **Selection bias, inherited** — funded loans only; no reject-inference
   correction in v1 (BACKLOG).
4. **Self-reported income** — `annual_inc` is borrower-declared.
5. **Status snapshot** — all outcomes as of the distribution's ~2019 snapshot.
6. **Weaker ranking where defaults are rare** — high-FICO slices (740+) show low
   PR-AUC at low base rates; three small purposes (car/medical/vacation)
   discriminate weakly (docs/SLICE_REPORT.md).
7. **Joint applications** — scored on primary-applicant features only; the
   16-column joint/secondary block is EXCLUDED_SCOPE (v2 design needed).

## 7. Fairness considerations

`zip_code`, `addr_state`, and income are established proxies for protected
attributes in US lending; the model uses geography (state one-hots, zip frequency)
and income. The slice report (39 slices) documents behaviour across state, income
quintile, purpose, and FICO band: **no state or income slice tripped the
visibility heuristics**; the measured calibration gap is a time phenomenon, not
concentrated in any proxy group. This documentation is a deliberate R7 obligation.
**It is not a fairness certification, not a compliance claim, and not legal
advice.**

## 8. Maintenance

Monitoring (P10): calibration drift is a first-class replay metric; alert
thresholds to be justified in writing. Retraining (P11): drift alarm → candidate →
recorded human approval → alias promotion; rollback = alias move back (rehearsed
in the registry test). Cost-ratio revision (issue #70) re-derives the threshold
without touching the model.
