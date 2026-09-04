# Project Walkthrough — plain-English record of what was done, in order, and why

Audience: future me, preparing to explain this project in interviews. One section per
phase, updated at each phase exit. Each step answers three questions: *what did I do,
why does it exist, and what would I say when probed on it.*

---

## P0 — Charter & requirements (before any code)

**Order of steps and why the order matters:** decisions were recorded *before* they were
needed, so nothing downstream was improvised.

1. **CHARTER.md** — fixed the one sentence everything is checked against: *grant or
   decline a personal loan at application time*. Same dataset with a different sentence
   (pricing, collections) is a different project with different features and metrics.
2. **RISK_REGISTER.md** — ranked what could sink the project (likelihood × impact).
   Top risks: mishandled right-censoring and leakage from the 40+ post-origination
   columns present in the raw file. The ranking is why P2 gets disproportionate budget.
3. **Dataset switch (charter v0.2)** — moved from a pre-cleaned academic subset to the
   full Kaggle file *on purpose*: the "clean" version had silently dropped 878k
   unresolved loans (hiding survivorship bias) and dropped the `term` column. Taking
   the raw file made censoring and leakage **our documented decisions instead of
   someone else's hidden ones**.
   - *Interview line: "I chose the dirtier dataset because the clean one made my two
     hardest problems invisible instead of solved."*
4. **ADRs** — each significant fork (tool stack, environment) recorded as an immutable
   context/decision/consequences snapshot. The charter states *what*; the ADR preserves
   *why, given what we knew then*.
5. **Environment lockfile** (`uv.lock`, Python pinned) — reproducibility's third leg:
   run = data hash + code commit + **exact library versions**. Without the third, the
   first two are theatre.
6. **Sprint plan** — 7 × 2-week sprints, phase epics and estimated tickets on GitHub;
   ops phases scheduled as fixed blocks so they cannot be squeezed by modelling overrun.

## P1 — Data acquisition & data contract

**The problem P1 solves:** every later result rests on one 1.6 GB CSV. P1 turns "a file
on my laptop" into "data I can prove is the right bytes (DVC), in a verified shape
(Pandera)". Bytes and shape are different guarantees; you need both.

**Step 1 — DVC tracking** (`dvc add` on the five raw files)
- *What:* DVC hashes each file, stores the bytes in a local cache, and leaves a
  five-line `.dvc` pointer file (hash + size) that **is** committed to git. Data and
  code now version together: any commit names the exact bytes it was built against,
  and `dvc status` detects corruption or tampering immediately.
- *Why not commit the data?* Git stores every version forever — GitHub caps files at
  100 MB precisely because repos aren't object stores. Pointer-in-git,
  bytes-in-cache is the standard resolution.
- *Deliberate scoping:* no DVC remote (no S3). Solo project, $0 budget, publicly
  re-downloadable data. The versioning guarantee (hash in git) is fully intact; only
  the *sharing* convenience is skipped.
- *Interview line: "git answers 'which code'; DVC answers 'which bytes'. My run IDs
  cite both."*

**Step 2 — Typed ingest** (`src/credit_default/ingest.py`)
- *What:* reads the CSV through an explicit 28-column **allowlist** with explicit
  dtypes, drops the 33 junk footer rows with an exact-count assertion, parses dates,
  asserts the total row count (2,260,701 raw → 2,260,668 clean), writes a 60 MB
  parquet working copy (derived, reproducible, not committed).
- *Why an allowlist and not a drop-list:* the raw file contains ~40 post-origination
  leakage columns (`total_pymnt`, `recoveries`…). With a drop-list, forgetting one
  silently poisons the model. With an allowlist, a forgotten column merely doesn't
  appear. Tests prove `int_rate`/`grade`/`total_pymnt` can never enter.
- *Why explicit dtypes:* pandas inference on this file is unreliable (mixed types,
  footer junk) and inference can change between library versions — an invisible
  reproducibility leak.

**Step 3 — Schema profile** (`scripts/profile_schema.py` → `docs/SCHEMA.md`)
- *What:* reads all 151 columns **as strings** (zero inference) and measures: null
  rate, cardinality, numeric parseability, ranges, top categories.
- *Why before the contract:* a contract copied from Kaggle's docs would be the docs'
  errors, made executable. Measure first, then encode. The measurements surprised us:
  `dti` runs −1…999, incomes hit $110M (self-reported), `revol_util` reaches 892%,
  two bureau columns are 51%/84% null *by meaning* (null = "no such event"), zips are
  masked to `###xx`.
- *Dual use:* the same profile is the evidence base for the P2 leakage ledger.

**Step 4 — Executable contract** (`src/credit_default/contract.py`, Pandera)
- *What:* the measured facts as running code — closed category sets, measured ranges
  with documented headroom, meaningful nulls kept nullable, two cross-column
  invariants (`fico_high ≥ fico_low`; `earliest_cr_line ≤ issue_d`), and
  `strict=True` so an *unexpected* column is itself a violation.
- *Why "executable" matters:* a doc describes; a contract **stops the pipeline** with
  the exact column, check, and offending rows. It re-tests every belief on every run.
- *It paid off immediately:* first full-data validation caught 30 rows with nulls that
  the profile's percentage rounding had hidden — 29 of them 2007 "credit-policy"
  legacy rows. We amended the contract to describe reality and routed the exclusion
  decision to P2, where row filtering belongs.
  - *Interview line: "my data contract found data-quality issues in its first five
    minutes that three prior passes over the data had missed — that's the argument
    for executable contracts in one sentence."*

**Step 5 — DATA_CONTRACT.md** — the human-readable summary, with the principle list
(measurement over documentation; allowlist; closed vocabularies; verify-don't-repair)
and the amendment process (by PR only).

**Why this exact order:** DVC first (pin the bytes before reading them), ingest second
(a safe typed reader to measure through), profile third (evidence), contract fourth
(encode the evidence), docs last (summarise what is now true). Each step consumes the
previous one's output; none could be honestly written before its predecessor.

**Branch/PR discipline:** all of P1 was built on `feature/p1-data-contract`, one commit
per ticket (#13–#16), merged to `main` via a reviewed pull request — the same flow a
team would use, exercised solo so the history reads like a team's.

---

## P2 — Leakage audit & label design

**The problem P2 solves:** two questions that make or break the project's honesty —
*which columns may the model look at* (leakage), and *what exactly counts as the
answer* (the label). Both were answered as tested code plus generated documents,
before any model exists.

**Step 1 — Leakage ledger, first pass** (`src/credit_default/ledger.py` →
`docs/LEAKAGE_LEDGER.md`)
- Every one of the 151 columns got a verdict + one-line justification against the test
  question: *could a loan officer see this at submission time — and is it the
  borrower's information rather than LC's own assessment?*
- Final census: 81 FEATURE, 40 BANNED_POST, 4 BANNED_UNDERWRITING, 7 METADATA,
  18 EXCLUDED_SCOPE, 1 TARGET.
- The two subtle bans worth quoting: `last_fico_range_*` (the borrower's FICO
  *re-pulled during the loan* — post-origination information wearing an innocent
  name) and `installment` (monthly payment = f(amount, term, **rate**) — it smuggles
  the banned interest rate back in through arithmetic).
- *Design decision:* the ledger is a Python dict; the document is generated from it
  and the P4 pipeline imports `feature_columns()` from it. Audit and pipeline cannot
  disagree by construction; tests enforce 151-column coverage and pin the classic
  leaks as banned.
- *Interview line: "my leakage audit is importable — the feature pipeline literally
  cannot use a column the audit didn't approve."*

**Step 2 — Second pass: 24 UNDECIDED → 0**
- Genuinely ambiguous columns were parked honestly in pass 1, then resolved
  deliberately: with *measurement* where possible (`funded_amnt` differs from
  `loan_amnt` in only 2,065 rows, ~all pre-2013 — it's a funding-process outcome,
  banned), with a recorded scope decision where legitimate-but-out-of-v1 (the
  16-column joint-applicant group → new EXCLUDED_SCOPE category), and with a timing
  argument where needed (`verification_status` completes before origination — the
  charter's decision point — so it's a FEATURE, with a serving-side caveat).
- A test now enforces zero UNDECIDED forever.

**Step 3 — Label truth table** (`src/credit_default/labels.py`)
- All nine `loan_status` values mapped explicitly; an unknown status *raises* instead
  of being absorbed. Exclusions carry reasons and are counted, never silently dropped:
  1,345,350 labelled (19.96% default) / 912,569 transitory / 2,749 credit-policy legacy.
- The two judgment calls, recorded: `Default` status (40 loans, a 121+-day
  delinquency stage) → 1, tagged [ASSUMED]; credit-policy legacy loans → excluded as
  a different underwriting population.
- *Why the ceremony:* the label is the one thing you cannot fix later — a wrong label
  silently poisons every downstream model, metric, and dashboard.

**Step 4 — Vintage composition figure** (`docs/figures/vintage_composition.png` +
`VINTAGE_NOTES.md`)
- The risk register's "look before you model" artifact. Measured: the 2013–2015
  36-month train window is ≥99.9% resolved (zero-censoring, now proven not assumed);
  60-month resolution collapses from 2014 (v1 exclusion justified); default rates
  drift 12%→20% across 2013–2016 (the real signal the replay will detect); and the
  2017–18 "improvement" is a snapshot-boundary artifact — the trap to name in any
  drift discussion.

**Step 5 — Class balance, measured** (`docs/CLASS_BALANCE.md`)
- v1 training scope: 546,018 loans, 14.07% default (≈ 1:6 imbalance — mild; PR-AUC
  primary, no resampling without evidence). Default rate rises within the window
  itself, so even the training years contain drift — P3's split must respect order.

**P2 exit state:** R1 and R2 (the project's two top risks) re-scored 20→10 with
written evidence; Charter §3's target definition confirmed against the real file.

---

## P3 — Temporal splits & evaluation protocol

**The problem P3 solves:** lock the rules of the game before any player exists.
Split boundaries, metrics, and the operating threshold were all fixed *before the
first model*, so none of them can quietly bend toward whatever makes a model look good.

**Step 1 — `splits.py`: vintage split with maturity arithmetic**
- Membership is a pure function of issue date + term: train 2013–2015 (36-month,
  labelled), validation 2016-H1, holdout 2016-H2, replay 2017–2018. No shuffle, no
  seed — determinism by construction.
- The maturity gap is *enforced in code*: the config raises if train_end + 36 months
  exceeds the observed data window; our train_end sits exactly at that limit
  (2015-12 + 36m = 2018-12), and a test pins it.
- *Interview line: "my split config won't compile with an immature training window —
  the censoring rule is an assertion, not a convention."*

**Step 2 — the frozen holdout (152,838 loans, hashed)**
- The holdout IDs live in a committed manifest with a recorded sha256. Three
  mechanisms make "we don't touch it until P6" checkable: freeze() refuses to
  overwrite; verify() recomputes the holdout from the rules and detects tampering,
  rule drift, or data drift; and reading it requires the spelled-out keyword
  `i_understand_this_is_for_final_p6_evaluation=True` — impossible accidentally,
  visible in any review diff.

**Step 3 — EVAL_PROTOCOL.md, frozen**
- Five metrics, PR-AUC primary; selection only on later vintages; ties go to the
  simpler model; a loser that isn't reproducible from its run ID doesn't count.
- The label-coverage rule is the honest heart of it: 2016+ labels exist only for the
  fast-resolving subset (validation 82% covered at 18.4% default; holdout 60% at
  22.1% — same world, different coverage). Quoting a metric there without its
  coverage number is defined as a protocol violation.

**Step 4 — the cost matrix (ADR-0003) and the derived threshold**
- FN:FP = 5:1 [ASSUMED], anchored to the measured $12,715 mean funded amount:
  a funded default costs a large slice of principal; a wrong decline costs ~3 years
  of margin — order-of-magnitude reasoning, honestly labelled, with a 3:1–8:1
  sensitivity band reported everywhere.
- The threshold is *derived, never tuned*: θ = C_FP/(C_FP+C_FN) ≈ 0.167 at baseline,
  implemented in `threshold.py` with the sensitivity table P6 must print. F1-max
  thresholds are explicitly forbidden in the protocol.
- The assumption is under recorded review: issue #70 tracks researching real
  LGD/recovery/margin evidence to confirm or supersede the ratio — the project's
  first ADR with a scheduled challenge.
- *Interview line: "I can tell you exactly which number in my system is assumed,
  where that's recorded, what would change if it's wrong, and who's on the hook to
  check it — that's what an assumption register is for."*

---

## P4 — Feature pipeline

**The problem P4 solves:** models eat fixed-length rows of numbers; loans arrive as
text, dates, and numerics full of meaningful gaps. The pipeline is the translator —
and the project's core claim is that the *same* translator runs at training time and
inside the serving API. Diagram: `figures/feature_pipeline_flow.svg` (two colored
paths converging on one purple box — that convergence is the whole design).

**Step 1 — Ingest widened to the audit** (`ingest.py` rewritten)
- The P1 ingest read a cautious 28 columns; the finished ledger approved 81. The
  allowlist is now *computed* from `ledger.feature_columns()` — the audit and the
  reader cannot disagree — and the Pandera contract grew 56 measured-bound columns
  to match. The rebuilt 186 MB parquet passes every check on all 2,260,668 rows.

**Step 2 — The skeleton with partition proof** (`features/pipeline.py`)
- Column groups (numeric / categorical / date-derived / frequency-encoded /
  excluded-with-reason) are derived from the ledger, and a test asserts they
  **partition** it exactly: a banned column cannot enter, an approved column cannot
  be silently forgotten. A second test smuggles `total_pymnt` into the input and
  proves it never reaches the matrix.
- *Interview line: "my pipeline's column lists are computed from the leakage audit
  and tested to cover it exactly — forgetting a feature is a test failure, not a
  silent loss."*

**Step 3 — The transform decisions** (finalised in #30, each recorded)
- **Missing-indicator columns**: half of applicants have no `mths_since_last_delinq`
  because they were *never delinquent* — a good sign. Median-imputing alone would
  disguise them as mildly-bad median cases; an indicator column keeps the null's
  meaning visible. 28 indicators on real data.
- **`dti` clipped to [0, 100]**: the raw −1…999 sentinels carry no ratio meaning.
- **`zip_code` frequency-encoded**: one learned column (share of training loans per
  masked zip, unseen zip → 0) instead of 956 one-hots; target encoding rejected in
  writing as leak-prone.
- **Scaling** on the numeric branch (the logistic baseline needs it; trees don't
  care); one-hots unscaled. Unknown categories at serve time encode as zeros —
  a strange loan gets a cautious score, never a 500 error.

**Step 4 — Fit-on-train enforced by construction** (`TrainWindowGate`)
- The pipeline's first step *refuses to fit* on any row issued outside 2013–2015,
  while transform passes everything. Imputers, scalers and encoders can only ever
  learn from the training window — the "future leaks in through the median" bug is
  structurally impossible, and tests prove both the refusal and the lawful
  transform of 2018 replay rows.
- *Interview line: "fit-on-train-only isn't a convention in my repo — fit() throws."*

**Step 5 — Parity, proven across the wire** (`serving.py` + pinned fixture)
- A committed 64-row synthetic fixture (sha256-pinned: silent regeneration fails the
  build) goes down both paths: the training batch, and row-by-row through a real
  `json.dumps`/`loads` round trip plus the serving converter that rebuilds exact
  training dtypes. Required result: **byte-identical matrices** — `np.array_equal`,
  not approximately.
- Scoring payloads structurally exclude `loan_status`: the serve path cannot
  receive the answer.

**Step 6 — Determinism, three layers deep**
- Same process: two fresh builds, identical output. **Cross-process**: two
  interpreters with *different hash seeds*, identical matrix bytes. **Pickle
  boundary**: the serialised fitted pipeline (what P7 ships, what P8 serves)
  transforms byte-identically after double dump/load. Plus the same claims on a
  20k-row real sample.
- CI wiring pre-done: `realdata` marker; `pytest -m "not realdata"` = 85 tests,
  ~4s, zero raw-data dependency.

**P4 exit state:** raw parquet → 184-feature matrix end-to-end; every feature in a
generated, sync-tested catalogue with its application-time justification; parity and
determinism as failing-capable tests rather than intentions.

---

*Next section: P5 — baselines & experiment tracking, added at P5 exit.*
