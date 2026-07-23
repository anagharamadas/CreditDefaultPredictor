# Risk Register — Credit Default Granting Model

Phase: P0
Status: DRAFT v0.2

Scoring: Likelihood (L) and Impact (I) on 1-5. Score = L x I.
Impact is measured against the project's actual purpose: evidencing operational maturity.

Revision note (v0.1 → v0.2): dataset switched from the Zenodo curated subset to the full
Kaggle accepted-loans file. R1 re-framed (hidden survivorship bias → managed
right-censoring), R2 re-scoped (curator-trust → full 151-column audit), R11 updated
(licence now Kaggle-distribution terms), R13–R14 appended. Nothing deleted.

---

## R1 — Right-censoring mishandled in training or replay

L 4 / I 5 / Score 20 — CRITICAL   (v0.1: hidden survivorship bias, 25)

The raw file now contains the 878k censored (Current/transitory) loans, so censoring is
visible rather than silently baked in by a curator — but it is still the easiest way to
corrupt the project. Failure modes: mapping transitory loans to "repaid"; letting
under-matured 60-month vintages into training; reading replay-window degradation as pure
drift when 2016–2018 labels are only 12–72% resolved.

Mitigation:
- Charter §3.3 fixes the policy: 36-month term only, training on 2013–2015 vintages
  (≥99.9% resolved — measured, not assumed).
- P2: plot default rate and resolution rate by `issue_d` month before any modelling;
  inspect the final 24–36 months for snapshot-boundary artifacts.
- P10: report replay performance under an explicit label-lag framework, separating
  "observed shift" from "labels not yet mature".
- Model card: stated as a top-line limitation.

Detection: composition and resolution plots in P2. Do this before any modelling.

## R2 — Leakage from the 40+ post-origination columns present in the file

L 4 / I 5 / Score 20 — CRITICAL   (v0.1: trusting curators' leakage claim, 20)

The v0.1 dataset had leakage-prone columns removed by a third party. The full file does
not: repayment totals, recoveries, collection fees, last payment amount/date, last FICO
pulls, all 15 hardship fields, all 6 settlement fields, and `loan_status`-derived
information all sit in the same 151-column header as the legitimate features. One careless
`df.drop` list instead of an allowlist and the model is a fake with spectacular metrics.

Mitigation:
- P2 leakage ledger classifies **every one of the 151 columns** as
  FEATURE / BANNED-POST-ORIGINATION / TARGET / METADATA / UNDECIDED with one-line
  justification. Zero UNDECIDED at P2 exit.
- The feature pipeline is allowlist-based: a column not affirmatively classified as
  FEATURE never enters the matrix.
- Timing-ambiguous columns (e.g. `verification_status`, joint/secondary-applicant
  fields, `revol_util`) get flagged, not assumed.

Cost of mitigation: a few hours. Cost of skipping it: the entire artifact's credibility.

## R3 — Scope creep into modelling, NLP, and reject inference

L 4 / I 4 / Score 16 — MAJOR

343 hours is enough time to over-build the modelling phase. The `desc`/`title`/`emp_title`
text fields invite an LLM detour, and the 27.6M-row rejected file invites a
reject-inference side quest. Both are legitimate extensions and both are traps before P11
exists.

Mitigation: BACKLOG.md entries, revisited only after P11 is demonstrably working.
Time-boxed hyperparameter budget agreed in P5 and not exceeded.

Detection: if the effort split diverges from 25/25/50 by more than 10 points, stop and
re-plan.

## R4 — Ops phases (P8-P12) compressed into stubs

L 3 / I 5 / Score 15 — MAJOR

The classic failure. The phases carrying the evaluated signal are the ones done last and
therefore the ones that get rushed.

Mitigation: schedule P8-P12 as fixed calendar blocks at the start rather than as whatever
time remains. Consider building a trivial end-to-end skeleton early (dummy model behind the
API, container, one CI job) so the ops path exists before the model is good.

## R5 — Threshold chosen without a defensible cost matrix

L 3 / I 4 / Score 12 — MAJOR

Selecting an operating point by maximising F1 or accuracy is indefensible for a credit
decision and an interviewer will press on it.

Mitigation: P3 writes the cost assumptions down explicitly, tagged as assumptions, before
any model output is seen. P6 runs sensitivity on the cost ratio.

## R6 — Miscalibrated probabilities

L 3 / I 3 / Score 9 — MAJOR

Tree ensembles on imbalanced data commonly produce poorly calibrated probabilities.
A granting model that ranks well but is miscalibrated cannot support a cost-based threshold.

Mitigation: calibration assessed as a first-class metric in P6, not an afterthought.
Calibration method, if applied, fitted inside the training window only.

## R7 — Geographic features as proxies for protected attributes

L 3 / I 3 / Score 9 — MAJOR

`zip_code` and `addr_state` are established proxies in US lending contexts.

Mitigation: fairness slice reporting in P6 across geography, income band, purpose and term
where available. Documented as a consideration, not a compliance claim. Not legal advice.

## R8 — Train/serve skew

L 3 / I 4 / Score 12 — MAJOR

Divergence between the training transform and the serving transform is a common and
silent production failure.

Mitigation: single shared code path, enforced by a parity test in CI comparing training
transform output against the served transform output on a fixed sample.

## R9 — Stack churn and version drift

L 3 / I 2 / Score 6 — MINOR

MLflow, Evidently, Great Expectations and orchestration tools have all had breaking
changes across major versions. Tutorials found online will be for other versions.

Mitigation: pin every version at P0, record in a lockfile, write against the pinned
version's own docs rather than blog posts. Re-verify any API before relying on it.

## R10 — Cost overrun against the USD 20 ceiling

L 2 / I 3 / Score 6 — MINOR

Cloud resources left running.

Mitigation: local-first architecture. Any cloud demo is short-lived, has a teardown script,
and a billing alert is configured before the first resource is created.

## R11 — Data licence / attribution mishandled

L 2 / I 3 / Score 6 — MINOR

Raw data is never committed to the repo (also a practical necessity: files exceed
GitHub's limits). The Kaggle `wordsforthewise/lending-club` distribution's licence terms
must be verified on its Kaggle page before this repo is made public [VERIFY]. If the
Zenodo benchmark is used in any published comparison, its CC-BY-4.0 attribution
(DOI 10.5281/zenodo.11295916) is mandatory. A portfolio repo with sloppy licensing is a
bad look in a project whose whole theme is doing things properly.

Mitigation: attribution block in README at P1; data/README.md records provenance and
hashes; licence check before flipping the repo public.

## R12 — Market mismatch in portfolio framing

L 2 / I 2 / Score 4 — MINOR

Target job market is India; the data and regulatory framing are US.

Mitigation: README states plainly that the transferable asset is the MLOps architecture,
and includes a short section on what would change for an Indian lending context. Do not
overclaim domain knowledge that has not been verified.

## R13 — Ambiguous loan_status values mapped carelessly (NEW in v0.2)

L 3 / I 3 / Score 9 — MAJOR

Three status groups have no obvious mapping: `Default` (40 loans — a delinquency state
distinct from `Charged Off`), and the two legacy `Does not meet the credit policy`
variants (2,749 loans, pre-2010 policy regime, arguably a different population). Plus 33
null footer rows.

Mitigation: P2 decides and documents each mapping with a one-line justification; ingest
drops the footer rows; the decision is unit-tested so it cannot silently change.

## R14 — Dirty raw file breaks naive ingestion (NEW in v0.2)

L 3 / I 2 / Score 6 — MINOR

The 1.6 GB file has mixed dtypes, footer junk, percent-sign strings, and free-text columns
with embedded commas. `pd.read_csv` defaults will produce silent dtype surprises.

Mitigation: explicit dtype map and usecols allowlist at ingest (P1 data contract);
row-count and hash assertions against the recorded manifest; ingest is a tested function,
not a notebook cell.

---

## Review cadence

Re-scored at the end of each phase in the RETRO. New risks appended, never deleted;
closed risks marked CLOSED with the evidence that closed them.
