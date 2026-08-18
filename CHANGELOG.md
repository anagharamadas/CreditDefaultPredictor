# Changelog

Notable changes to this project. Format follows [Keep a Changelog](https://keepachangelog.com/);
entries are dated rather than semver-numbered until there is a releasable artifact
(expected at P7, first registered model).

This file records *what* changed; *why* lives in the charter revision notes and
[docs/adr/](docs/adr/README.md).

## [Unreleased]

- Environment lockfile (last open P0 checklist item).

## 2026-08-18

### Added
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
