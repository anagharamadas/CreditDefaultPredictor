# Evaluation Protocol

Status: FROZEN at P3 (2026-09-04) — written before any model exists, so no metric or
population choice can be bent toward a model that looks good on it. Changes after this
point happen by PR with a stated reason, and never between two models being compared.

Split boundaries: `src/credit_default/splits.py` (measured audit table in its module
run). Cost assumptions: [adr/0003-cost-matrix.md](adr/0003-cost-matrix.md).
Threshold derivation: §5.

## 1. Populations

| Population | Use | Rule |
|---|---|---|
| TRAIN (2013-01..2015-12, 36-mo, labelled) | fitting + cross-validation folds *within* the window | 546,018 loans, 100% labelled |
| VALIDATION (2016-H1) | model comparison and selection (P5/P6) | labelled subset; coverage 82.1% — always stated |
| HOLDOUT (2016-H2, frozen) | final P6 report, opened once | 152,838 loans; access-guarded (holdout.py) |
| REPLAY (2017-2018) | P10 monitoring only | never used for selection, ever |

Rules that hold everywhere:

- **No random splits, anywhere.** Any within-train resampling for stability estimates
  must stratify by vintage month, never shuffle across the train boundary.
- **Selection metrics are computed on later vintages than training** — the whole point.
- **Label coverage accompanies every evaluation-split metric.** 2016+ labels exist only
  for resolved loans, a fast-resolving (biased) subsample: validation shows 18.35%
  default vs holdout 22.12% not because credit worsened but because coverage fell
  (82.1% → 60.4%). A metric quoted without its coverage number is a protocol violation.
- **Snapshot-label caveat, stated once and inherited everywhere:** training labels come
  from the ~2019 status snapshot. A strict as-of-2016 simulation would not have known
  late-2015 outcomes yet. This is the standard backtest compromise; the P10 replay is
  where as-of honesty is enforced dynamically.

## 2. Metrics (fixed set — Charter §4.1)

| Metric | Role |
|---|---|
| **PR-AUC** | Primary. 14.07% positive class; precision-recall is the honest ranking view. |
| ROC-AUC | Secondary; comparability with published work. |
| Brier score | Calibration, scalar. |
| Reliability curve | Calibration, visual; reported **per vintage half-year**. |
| Expected cost @ operating threshold | The business number; uses ADR-0003, reported with the 3:1–8:1 sensitivity band. |

No metric outside this table may be used to *select* between models. Additional
diagnostics may be *reported*, labelled as diagnostics.

## 3. Comparison rules

- A candidate must beat the incumbent on **primary metric (PR-AUC) on VALIDATION**, and
  must not degrade calibration (Brier) by more than noise — quantified via
  vintage-month bootstrap within the evaluation split.
- Ties or near-ties resolve toward the **simpler model** (fewer features, fewer
  hyperparameters, more interpretable) — Charter non-goal 1.
- Every comparison logs both runs' IDs; a comparison whose loser is not reproducible
  from its run ID does not count.

## 4. Slice reporting (P6)

PR-AUC, default rate and calibration by: vintage month, purpose, state (top-10 by
volume + rest), income band (quintiles), and FICO band. Geographic slices are the
R7 fairness-documentation obligation, not a compliance claim.

## 5. Threshold policy (fixed before any model output — ticket #26)

1. Probabilities must be **calibrated** before thresholding (method chosen in P6, fit
   inside the training window only).
2. The operating threshold is **derived, not tuned**: θ = C_FP / (C_FP + C_FN) from
   ADR-0003 ⇒ **θ ≈ 0.167** at the 5:1 baseline.
3. Sensitivity is part of the deliverable: report expected cost and decline rate at
   θ ∈ {0.111 (8:1), 0.143 (6:1), 0.167 (5:1), 0.200 (4:1), 0.250 (3:1)}.
4. Threshold-dependent numbers are quoted with their assumed ratio, e.g.
   "expected cost 412 $/loan @ 5:1 [ASSUMED]".
5. **Forbidden:** choosing θ by maximising F1, accuracy, Youden's J, or any metric
   without a cost interpretation; adjusting θ after seeing holdout results.

## 6. What would invalidate a result

- A holdout metric produced before the P6 final evaluation (the access guard exists,
  but so does grep).
- Any evaluation on a random split of pooled vintages.
- A threshold tuned on the split it is reported on.
- A metric on 2016+ data quoted without label coverage.
