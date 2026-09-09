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

## P5 — Baselines & experiment tracking

**The problem P5 solves:** the first models exist — and every one of them is
tracked, protocol-evaluated, lineage-stamped, and reproducible. The model quality
is deliberately unremarkable; the machinery around it is the deliverable.

**Step 1 — MLflow server, composed** (`docker-compose.yml` + `tracking.py`)
- MLflow v3.15.1 (matching the locked client — server/client skew is R9) with a
  sqlite backend on a local volume; proven to survive container restarts. Port 5001
  because macOS AirPlay squats on 5000. `setup_tracking()` *raises* when the server
  is down: a run that cannot be tracked should fail, not run untracked.

**Step 2 — Three baselines, protocol-evaluated** (`train.py`)
- Prior (everyone gets the training default rate): PR-AUC 0.1835 = prevalence,
  ROC 0.500, cost 0.918/loan @5:1 — the floor, and its predictability is itself a
  system check (it caught a real bug — see below).
- Logistic: PR-AUC 0.3236, ROC 0.695, cost 0.625. LightGBM (zero-search, params
  fixed per Charter non-goal 8): PR-AUC 0.3446, ROC 0.709, cost 0.610.
- All metrics on VALIDATION's labelled subset with coverage (0.821) logged beside
  them; full 3:1–8:1 cost band logged; holdout untouched.
- *The bug story:* first real run reported expected cost 0.000 — impossible, since
  the prior must pay ~5× the default rate. Two pandas Series with different indexes
  had silently aligned-to-nothing. Found by *reading* the results against a known
  expectation; fixed with a regression test. Predictable metrics are canaries.

**Step 3 — Lineage enforced, not encouraged** (`start_tracked_run`)
- The only sanctioned way to open a run gathers git commit (+dirty flag), raw-data
  md5 (from the DVC pointer) and holdout-manifest sha *before* the run starts, and
  raises if any fact is unresolvable. An untraceable run is worse than no run.

**Step 4 — Reproduce-from-run-ID, demonstrated** (`scripts/reproduce_run.py`,
`docs/REPRODUCIBILITY.md`)
- The script refuses unless the environment matches the recorded lineage exactly,
  re-executes the entrypoint, compares protocol metrics. Live result: **delta 0.0
  on every metric** — bit-exact. Charter §4.2, cashed. Boundary stated honestly:
  same-machine claim, no cross-platform bit-exactness asserted.
- *Interview line: "hand me a run ID from six weeks ago and I'll hand you the same
  numbers — the script that proves it is in the repo, with its transcript."*

**Step 5 — The DAG** (`flows.py`, Prefect)
- ingest → contract-gate → three trainings as retryable, observable tasks; the
  contract is a *pipeline gate*, so bad data stops the flow before any model sees
  it. Prefect records execution; MLflow records results. The flow's three runs
  matched the standalone metrics to every digit — determinism straight through the
  orchestration layer.

**P5 exit state:** three baselines logged with full lineage; any run reproducible
from its ID alone (demonstrated); training runs as one orchestrated flow.

---

## P6 — Selection, calibration, decision policy

**The problem P6 solves:** choose one model, honestly — with every choice made by
rules frozen before any model existed, and the holdout opened exactly once at the end.

**Step 1 — Evaluation harness** (`evaluation.py`)
- Comparisons score models loaded FROM their MLflow artifacts (`runs:/<id>/model`),
  not retrained lookalikes; each comparison is itself a lineage-tagged run with the
  ranked table attached. The holdout door is guarded at this layer too: the split
  function refuses without the spelled-out acknowledgment, then verifies the frozen
  manifest end-to-end and cross-checks the frame against the frozen ID list.

**Step 2 — Calibration: assessed, method built, REJECTED** (`calibration.py`)
- The reliability table showed *systematic under-prediction* (mean 0.157 vs observed
  0.184) with the diagnosis in its shape: base-rate drift, not classifier distortion.
- The window-honest isotonic scheme (base model 2013-01..2015-06, calibrator
  2015-07..2015-12 — out-of-sample for the model, inside the train window) made
  everything worse: a within-window calibrator can only learn the past's rate, and
  the shortened fit window costs six months of data plus the whole 2015+ bureau
  block. Decision: keep uncalibrated; the obligation moves to P10 monitoring.
- *Interview line: "I built the calibrator, measured it, and rejected it with
  evidence — 'assessed calibration' doesn't mean 'applied a calibrator'."*

**Step 3 — The operating points** (`decision_policy.py` → DECISION_POLICY.md)
- θ stays a derivation (a test greps the module and forbids score-maximising
  statistics). At the 5:1 baseline: decline 38.7%, funded-book default rate
  18.4%→11.1%, declined pool defaults at 2.7× funded, 33.5% saving vs
  fund-everyone. The 3:1→8:1 band swings declines 17%→61% — the quantified case
  for the open cost-ratio research (issue #70).

**Step 4 — Slices** (`slices.py` → SLICE_REPORT.md)
- 39 slices; 8 flagged, coherently: high-FICO bands rank hard at low base rates,
  three small purposes discriminate weakly, and late-validation months show the
  drift gap growing monotonically (−5.5→−7.2pp). **No state or income slice
  flagged** — the calibration gap is a time phenomenon, not concentrated in any
  proxy group. Framed throughout as the R7 documentation obligation, never a
  compliance claim.

**Step 5 — Selection justified, holdout opened once** (`p6_final_report.py`,
ADR-0004)
- The lightgbm-vs-logistic margin passed a month-stratified bootstrap:
  +0.0209 PR-AUC, 95% CI [+0.0177, +0.0242] — excludes zero, so the
  simpler-model tie rule doesn't bind.
- Then, with the acknowledgment spelled out and the manifest verified, the holdout
  opened for the one-shot final report (coverage 0.604, stated): PR-AUC 0.3767,
  ranking preserved, ECE worsened to 0.064 — drift deepening on schedule. ADR-0004
  records the selection, the rejections (including the calibrator, with its
  structural reason), and the accepted consequences.

**P6 exit state:** selection justified against baselines on later vintages;
calibration assessed; threshold derived, not tuned; slices reported; the holdout's
seal broken exactly once, on the record.

---

## P7 — Packaging & registry

**The problem P7 solves:** the chosen model becomes a *deployable, promotable,
revocable thing* with its provenance attached — instead of a pickle in a folder.

**Step 1 — Registration** (`registry.py`)
- `credit-default-granting` v1 registered from the specific ADR-0004 run (pinned
  by run ID in code — the selection was a decision about a run, not "latest").
  Version tags chain registry → run → lineage tags → exact commit/data/splits.
- The artifact was already pipeline+model as one object (the P4 design); the
  registry makes it versioned and addressable. Serving loads
  `models:/credit-default-granting@champion` and **nothing else**.

**Step 2 — The lifecycle as alias moves**
- MLflow 3.x removed registry "stages"; aliases implement the same lifecycle
  (`@staging` = under review, `@champion` = serving) — the ticket's intent
  honoured under the current API, with the adaptation recorded (ADR-0001's
  verify-against-pinned-version discipline paying off).
- Promotion IS an alias move; **rollback is the same move backwards** — rehearsed
  in a self-cleaning test: v2 promoted, then the alias returned to v1. That
  one-line gesture is P11's rollback path, already proven.
- *Interview line: "deploy and rollback are the same recorded operation in my
  registry — moving one alias — so rollback needs no special machinery to trust."*

**Step 3 — The model card** (`docs/MODEL_CARD.md`)
- Intended use, training vintages + censoring assumptions, protocol metrics with
  coverage stated, ADR-0004's accepted negatives (drift under-prediction, ECE
  growth), Charter §8 limitations carried over, the R7 fairness framing, and an
  explicit **prohibited uses** list (60-month loans, other markets, pricing,
  automated adverse decisions, compliance claims).
- A small test pins the card's load-bearing content: the source run ID, coverage,
  [ASSUMED], "not legal advice", the scope exclusions — the card cannot silently
  lose its caveats.

**P7 exit state:** one registered artifact, promotable and revocable by recorded
alias moves, described by a card that leads with what it must not be used for.

---

## P8 — Serving API

**The problem P8 solves:** the registered model becomes a service that scores real
requests — enforcing the *same* contract training used, recording every decision,
and refusing to operate when it cannot do either.

**Step 1 — Two-layer validation** (`api/schemas.py`, `api/app.py`)
- pydantic handles *structure* (field names, types, closed category vocabularies,
  `extra="forbid"`) — and the schema is **generated from the same constants** that
  drive ingest and the contract, so it cannot drift from them.
- Pandera handles *bounds and cross-column invariants* — and it is literally the
  training contract object with `loan_status` removed, not a serving copy. Between
  them sits the #28 converter the parity tests hold byte-identical.
- *Interview line: "my API can't enforce a different contract than training did —
  it imports the same object."*

**Step 2 — The champion, and nothing else** (`registry_model_loader`)
- The model arrives only via `models:/credit-default-granting@champion`.
  `MODEL_ALIAS` selects the alias; promotion and rollback (P11) move that alias —
  **the service is never redeployed to change models**.

**Step 3 — The Compose stack** (`Dockerfile`, `docker-compose.yml`)
- api + postgres + mlflow, every value env-overridable with a working default.
  The image installs from the same `uv.lock` the laptop syncs, so container and
  dev environment run identical versions; it runs unprivileged (uid 10001).
- Two real integration bugs surfaced here that no unit test could have found:
  MLflow 3.x's DNS-rebinding protection 403-ing the compose service name, and
  `registry.load()` silently falling back to a local store when the caller forgot
  to set the tracking URI. Both fixed with the reason recorded at the fix.

**Step 4 — The prediction store** (`store.py`)
- Designed for its consumers, not as a log: `issue_d` stored **separately** from
  `scored_at` (replaying three years in an afternoon makes every `scored_at`
  "today" — the vintage is the axis drift is measured along), features as JSONB
  so a v2 feature set needs no migration, the decision policy in force stored so
  a past decision stays auditable against the assumption behind it, and
  deliberately **no label column** — outcomes arrive months later and are joined
  at analysis time.
- **Write policy: a credit decision that cannot be recorded is not made.** The
  store is a readiness dependency. Demonstrated by stopping Postgres mid-flight:
  `/score` returns 503 "decision not recorded, so not returned"; on restore the
  pool self-heals.

**Step 5 — Traceable operations** (`api/logging_config.py`)
- One request id per request, held in a `ContextVar`, so every log line below
  inherits it without being passed it; echoed in the response header. Logs are
  JSON, one object per line.
- Privacy rule, verified rather than asserted: rejections log the loan id and the
  *violated column names* — never feature values. A grep of the container logs for
  the rejected value returned zero hits. The full payload lives in the store,
  behind database access; logs are the wider surface and get less.

**Step 6 — Cold start** (`docs/SERVING_DEMO.md`)
- `docker compose down -v` → `up` → **first scored request in 8 seconds**, with
  the API installing its own database schema into the empty volume. The teardown
  asymmetry is deliberate: prediction history is disposable (the replay rebuilds
  it), the model registry is not.
- The doc states the prerequisite chain honestly: a genuinely fresh clone needs
  data → ingest → training → registration before it can score, which is why P12's
  five-minute demo will need a seeded shortcut rather than pretending otherwise.

**P8 exit state:** a containerised service that enforces the training contract,
serves only the registry champion, records every decision with its vintage, traces
every request end to end, and fails closed when it cannot do those things.

---

## P9 — CI/CD and the quality gate

**The problem P9 solves:** up to here, every guarantee was checked *by me, on my
machine*. That is exactly the arrangement in which an environment-dependent pass
survives unnoticed.

**Step 1 — CI that lacks a developer's advantages** (`.github/workflows/ci.yml`)
- Runs on every push to main and every PR, in a fresh clone with **no raw data**
  (1.6 GB, DVC-tracked, never committed), no Docker services, no conda env, and no
  shell habits. Four tiers, ordered cheapest-first so failures are legible:
  lockfile reproducibility → lint → the 139-test suite → the entrypoints run as a
  *program* → generated docs still match their generating code.
- It invokes plain `pytest` deliberately. The week before, the suite had passed for
  me under `python -m pytest` (which silently adds the working directory to the
  import path) and failed for anyone running the documented command.

**Step 2 — CI earns its keep on the first run**
- Tier 3 failed with "train/serve parity broken" — on GitHub, while passing on my
  Mac *and* in a local Linux container. The container was the clue: Docker on
  Apple Silicon runs arm64; GitHub runners are x86-64.
- The system was fine — the real parity test passed on that same runner. **My smoke
  script was wrong**: it compared five rows computed inside a 21-row batch against a
  separate 5-row batch and demanded bit-equality. That is not a parity check; it
  asserts that linear algebra accumulates identically at different matrix shapes,
  which nothing guarantees and x86 vectorisation does not honour.
- The distinction that matters: the *transform* is elementwise, so it is genuinely
  bit-exact at any batch size — and that is the guarantee this project makes.
  Predictions involve a matrix multiply, whose summation order may vary with shape.
- *Interview line: "CI caught an over-strict assertion of mine on its first run,
  because the runner had hardware I don't. No amount of local testing would have
  found it — both of my Linux checks were arm64."*

**Step 3 — The model quality gate** (`quality_gate.py`)
- Three rules from the protocol frozen in P3: ranking must improve *beyond noise*
  (bootstrap interval entirely above zero — a higher number alone is not enough);
  calibration must not degrade beyond noise (blocking the bad trade of buying
  ranking with worse probabilities, which would break a threshold *derived from*
  probabilities); ties go to the incumbent.
- **Fails closed.** Cannot evaluate → exit 2, a refusal. A gate whose job is to
  withhold approval must treat "cannot check" as "no".
- Proven in both directions, because a gate that only ever refuses is useless:
  champion vs itself → blocked (a tie); LightGBM vs a temporarily-registered
  logistic incumbent → passed at +0.0209, reproducing ADR-0004's figure exactly.

**Step 4 — Honest about what CI cannot do** (`docs/TESTING.md`)
- Nine tests are excluded by marker because the runner truly lacks what they need
  (the un-committed raw data; the running stack). The quality gate is the bigger
  gap: it needs models and real data, so its **rules** are unit-tested in CI while
  its **execution** happens where the models live.
- Stated rather than papered over: a green CI badge means *the code is sound*, not
  *the model is approved*. Two different claims, deliberately kept apart.

**Step 5 — Connect everything once and look for seams**
(`docs/E2E_WALKTHROUGH.md`)
- Every component had passing tests; this asked a different question — do they work
  when *connected*? Raw file → parquet (26s) → flow training (28s) → quality gate →
  register → promote → serve → stored prediction, walked once, deliberately.
- Two good results: a full retrain from freshly rebuilt data produced a model
  measurably **identical** to the incumbent (difference 0.00000, CI [0, 0]) — so the
  gate blocked it as a tie, correctly; and the frozen holdout re-verified against the
  rebuilt parquet, proving those 152,838 IDs are a function of raw data and rules
  rather than of a convenient intermediate file.
- **Two gaps found, neither reachable by a unit test.** The service caches its
  champion at startup, so moving the registry alias does nothing until a restart —
  which means P7's one-line rollback gesture is incomplete, and predictions can be
  recorded under a stale `model_version` (issue #79). And at 32ms a request, replaying
  665k loans sequentially takes ~6 hours, which would quietly kill the repeatability
  that makes the replay worth building (issue #80).
- *Interview line: "the integration exercise found that my rollback wouldn't have
  worked — before the phase that depends on it, rather than during."*

---

*Next section: P10 — drift, replay, observability, added at P10 exit.*
