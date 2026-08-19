# Data Contract — accepted-loans ingest

Status: v1.0, P1 exit
Executable form: `src/credit_default/contract.py` (Pandera). This page is the
human-readable summary; **the code is the authority**. Evidence base:
[SCHEMA.md](SCHEMA.md) (measured profile of all 151 raw columns).

## Scope

The contract governs the **ingested frame**: 28 candidate application-time columns
selected by allowlist in `src/credit_default/ingest.py`. It does not govern the other
123 raw columns — those never enter the pipeline (the P2 leakage ledger classifies all
151 and may promote or demote candidates, which will amend this contract).

## Contract principles

1. **Written against measurement, not documentation.** Every bound and category set
   comes from profiling the real file. Kaggle's column descriptions were treated as
   hypotheses.
2. **Allowlist, not blocklist.** A column not named in the contract is a violation —
   in both directions (`strict=True`). A leakage column smuggled into the frame fails
   validation even though the contract never mentions it.
3. **Closed vocabularies.** Categorical sets (loan status, purpose, state, term…) are
   exact. A new category appearing is news we want to hear as a failure, not absorb
   silently.
4. **Measured range + documented headroom.** Numeric bounds are the measured range
   widened only where a legitimate unseen value could appear, each with a comment:
   FICO uses scale bounds 300–850 (measured 610–845); `loan_amnt` caps at 50,000
   (measured max 40,000, LC's historical product cap).
5. **Nulls are facts, not dirt.** `mths_since_last_delinq` (51% null) and
   `mths_since_last_record` (84% null) stay nullable — null *means* "no such event on
   record" and is predictive signal, not missing data to impute away.
6. **The contract verifies; it does not repair.** `coerce=False` — dtype discipline is
   the ingest module's job. Row exclusion is P2's job.

## Notable measured facts encoded

| Fact | Contract treatment |
|---|---|
| `dti` spans −1 … 999 (sentinel-like extremes) | Range −2…1000 accepted at ingest; treatment is a P2/P4 decision |
| `annual_inc` up to $110M, self-reported | ≥0 with 1e9 sanity cap; no tighter bound is defensible |
| `revol_util` up to 892% | >100% is real (over-limit); capped at 1000 |
| `zip_code` masked to `###xx` | Regex-enforced; full zips never present |
| `term` has leading spaces (`" 36 months"`) | Preserved verbatim; normalisation is a transform, not a contract fix |
| 33 footer rows with null status | Dropped by ingest with exact-count assertion |

## Found by the contract on first run (would have been silent otherwise)

30 rows carry nulls the profile's rounding hid (0.001%): 29 are **2007
"credit-policy" legacy rows** with null `earliest_cr_line` (4 also null
`annual_inc`), 1 is a 2017 loan with null `zip_code`. Decision: the contract
describes raw reality (nullable at trace rates, commented in code); excluding the
credit-policy population is P2's documented decision, not a silent contract fix.

## Cross-column invariants

- `fico_range_high` ≥ `fico_range_low`
- `earliest_cr_line` ≤ `issue_d` (where present) — a credit history cannot start
  after the loan it precedes

## Revalidation

```bash
PYTHONPATH=src python -m credit_default.contract   # validates the interim parquet
pytest tests/test_contract.py                      # violation matrix + full-data check
```

Amendments to this contract happen by PR, alongside the code change and a line here
explaining what changed and why.
