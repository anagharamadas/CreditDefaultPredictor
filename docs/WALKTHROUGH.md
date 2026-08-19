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

*Next section: P2 — leakage ledger and label design, added at P2 exit.*
