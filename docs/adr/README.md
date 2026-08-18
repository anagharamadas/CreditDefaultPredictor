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

## Expected future ADRs

Forks already identified in the roadmap that will get an ADR when decided:

- Censoring policy finalisation (P2) — currently fixed by Charter §3.3; formalise if revisited.
- Cost matrix and split boundaries (P3).
- Model selection and operating threshold (P6).
- Deploy target (by P8) — left open in ADR-0001.
- Drift-monitoring tool: Evidently vs NannyML vs custom tests (by P10) — left open in ADR-0001.
- Approval-gate design (P11).
