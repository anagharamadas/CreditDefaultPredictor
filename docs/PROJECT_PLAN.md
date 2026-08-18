# Project Plan — Sprint Structure

Status: v1.0, 2026-08-18
Owner: Anagha Ramadas (Product Owner, Scrum Master, and Engineer — solo team)

Execution tracking lives on GitHub: phase **epics** (issues #1–#12), **task tickets**
labelled `phase:P*` with estimates and acceptance criteria, and one **milestone per
sprint** with due date and sprint goal. This document records the plan's shape and the
working agreement; the tickets are the source of truth for day-to-day status.

## Working agreement

- Capacity: 4 h/day, Mon–Fri → 20 h/week → **40 h per 2-week sprint**
  (Sprint 1 starts Wed 2026-08-19, so it has 8 working days = 32 h).
- Planned load is kept ~10% under capacity; the difference covers ceremonies and spillover.
- Ceremonies, compressed for a team of one but still *recorded*:
  - **Sprint planning** (30 min, first day): confirm the sprint's tickets, adjust estimates.
  - **Review + retro** (30 min, last day): close the milestone with an evidence comment on
    each finished epic; write 3 bullet points (went well / didn't / change) into the
    milestone description; re-score the risk register if anything moved.
- Definition of done for any ticket: acceptance criteria checked, code merged to `main`
  with green checks (once CI exists), docs updated in the same PR.
- Scope changes mid-sprint go to the backlog or the next milestone — never silently into
  the current sprint.

## Sprint map

| Sprint | Dates | Cap | Planned | Goal (phases) |
|---|---|---|---|---|
| 1 | Wed Aug 19 – Fri Aug 28 | 32h | 28h | **P1** data under DVC + executable contract; **P2** started (ledger pass 1, labels.py, vintage plots) |
| 2 | Aug 31 – Sep 11 | 40h | 33h | **P2** ledger closed, balance measured; **P3** splits + eval protocol frozen; **P4** pipeline started |
| 3 | Sep 14 – Sep 25 | 40h | 36h | **P4** pipeline + parity tests done; **P5** three baselines in MLflow, lineage reproducible, Prefect flow |
| 4 | Sep 28 – Oct 9 | 40h | 36h | **P6** selection + calibration + threshold + slices; **P7** registry + model card; **P8** API started |
| 5 | Oct 12 – Oct 23 | 40h | 36h | **P8** serving + prediction store done; **P9** CI/CD with model quality gate; end-to-end walkthrough |
| 6 | Oct 26 – Nov 6 | 40h | 32h | **P10** replay 2016–2018, drift + performance monitoring under label lag, dashboard |
| 7 | Nov 9 – Nov 20 | 40h | 31h | **P11** HITL approval + rollback demonstrated; **P12** runbook, 5-min demo, interview drill |

Total planned: ~232 h of estimated ticket work across 264 h of capacity.
Estimates include learning-curve time (junior operator, several new tools — see ADR-0001).

## Deliverable per sprint (the demo at each review)

1. `dvc status` clean + Pandera contract running green against real data.
2. Leakage ledger with zero UNDECIDED + frozen, hashed holdout manifest.
3. An MLflow UI showing three baselines, any of them reproducible from run ID alone.
4. A registered, calibrated model with a model card — and an API skeleton in Compose.
5. `docker compose up` → scored request persisted in Postgres; CI refusing a bad model.
6. A dashboard showing genuine drift emerging month-by-month from replayed history.
7. A recorded retrain approval, a recorded rollback, and a <5-minute stranger demo.

## Buffer policy

Sprint 7 ends 2026-11-20; anything cut lands in an optional Sprint 8 (Nov 23 – Dec 4)
before any BACKLOG.md item is considered. Slippage >1 sprint triggers a scope cut from
the modelling phases, never from the ops phases (Charter §6 effort-split rule).
