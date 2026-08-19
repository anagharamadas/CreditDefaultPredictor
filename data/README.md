# Data — provenance and integrity manifest

Raw data is **never committed to this repo** (files exceed GitHub's 100 MB limit, and
committing data is bad practice regardless). Raw files are **DVC-tracked**: each has a
committed `.dvc` pointer file recording its md5 and size, and `dvc status` verifies the
local bytes against it. No DVC remote is configured (deliberate: solo project, public
re-downloadable data, $0 budget) — this manifest plus the pointer files are the
versioning record. If your local file's md5 and row count match this table, you have
the right data.

Raw files are immutable. Nothing under `data/raw/` is ever edited in place; all cleaning
happens downstream in code.

## Layout

```
data/
  raw/
    kaggle/    accepted_2007_to_2018Q4.csv (+ .gz), rejected_2007_to_2018Q4.csv (+ .gz)
    zenodo/    LC_loans_granting_model_dataset.csv   (benchmark only)
```

## Manifest (verified 2026-07-23)

| File | md5 | Rows (excl. header) | Size |
|---|---|---|---|
| `raw/kaggle/accepted_2007_to_2018Q4.csv` | `40d0463a883c602e3732b5f821a3dac7` | 2,260,701 | 1.6 GB |
| `raw/kaggle/rejected_2007_to_2018Q4.csv` | `e4fb3f2e3dd1dcc16c7efdcf749cc84c` | 27,648,741 | 1.7 GB |
| `raw/zenodo/LC_loans_granting_model_dataset.csv` | `b019384d6bc65bf2a3e839362e4ff502` | 1,347,681 | 160 MB |

The Zenodo md5 matches the value published on its Zenodo record.

Verify locally:

```bash
md5 data/raw/kaggle/accepted_2007_to_2018Q4.csv   # macOS; use md5sum on Linux
```

## Sources

- **Primary**: Kaggle dataset `wordsforthewise/lending-club`
  (https://www.kaggle.com/datasets/wordsforthewise/lending-club), accepted + rejected
  loans, 2007–2018Q4, statuses frozen at the distribution's snapshot (files dated
  Dec 2019). Licence: verify on the Kaggle page before publishing derived artifacts
  [VERIFY].
- **Benchmark**: Ariza-Garzón, Sanz-Guerrero & Arroyo Gallardo (Universidad Complutense
  de Madrid), *LC loans granting model dataset*, Zenodo, 2024, CC-BY-4.0,
  DOI 10.5281/zenodo.11295916. Derived from the Kaggle distribution above; used only for
  cross-checking against published results.

## Known raw-file quirks (handled at ingest, see RISK_REGISTER R13/R14)

- `accepted`: 33 footer rows with null `id`/`term`/`loan_status`; mixed dtypes; free-text
  columns (`emp_title`, `title`, `desc`) contain embedded commas — always parse with a
  real CSV parser, never `split(',')`.
- `rejected`: `Debt-To-Income Ratio` is a percent-string (`"10%"`); `Risk_Score`
  provenance unverified.
