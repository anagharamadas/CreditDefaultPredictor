# Architecture Decision Records

One numbered, dated, immutable record per significant design fork: context, decision,
alternatives rejected, consequences accepted. Accepted ADRs are never edited — a change
of course gets a new ADR that supersedes the old one, so the trail of "what we knew and
decided at the time" stays honest.

The charter states each decision as a fact; the ADR holds the reasoning.

## Index

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-tool-stack.md) | Tool stack for the MLOps pipeline | ACCEPTED | 2026-08-18 |
| [0002](0002-python-environment.md) | Python environment: conda host, uv-locked deps | ACCEPTED | 2026-08-18 |
| [0003](0003-cost-matrix.md) | Cost matrix: FN:FP = 5:1 [ASSUMED], 3:1–8:1 sensitivity | ACCEPTED | 2026-09-04 |
| [0004](0004-model-selection.md) | v1 model: LightGBM uncalibrated (bootstrap-real margin) | ACCEPTED | 2026-09-04 |

## Expected future ADRs

Forks already identified in the roadmap that will get an ADR when decided:

- Censoring policy finalisation (P2) — currently fixed by Charter §3.3; formalise if revisited.
- Cost-matrix revision — if the open FN:FP research ticket contradicts ADR-0003, its
  outcome lands as a superseding ADR.
- ~~Model selection and operating threshold (P6)~~ — done: ADR-0004 (+ threshold via ADR-0003).
- Deploy target (by P8) — left open in ADR-0001.
- Drift-monitoring tool: Evidently vs NannyML vs custom tests (by P10) — left open in ADR-0001.
- Approval-gate design (P11).
