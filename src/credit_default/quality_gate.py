"""Model quality gate (ticket #51): a candidate may not replace the incumbent
unless it is measurably better.

**What this is not.** It is not the human approval gate — that is P11, and it asks
a different question. This gate asks *"is the candidate better?"* and answers it
mechanically, with no judgement. P11 asks *"should we deploy it anyway, given the
drift evidence, the slices, and what we know that the numbers do not?"* and only a
person can answer that. Both must pass: this one filters out models that are simply
worse, so no human ever spends attention on them; P11 handles everything the metrics
cannot see. Neither replaces the other.

**The rules** (from docs/EVAL_PROTOCOL.md §3, fixed before any model existed):

1. *Ranking must improve, provably.* The candidate's PR-AUC must beat the
   incumbent's by more than sampling noise — the 95% bootstrap interval of the
   difference must lie entirely above zero. A higher number alone is not enough.
2. *Calibration must not degrade, provably.* The candidate's Brier score must not be
   significantly worse: the interval for that difference must not lie entirely above
   zero. Degrading calibration to buy ranking is a bad trade for a model whose
   probabilities feed a cost-based threshold.
3. *Ties go to the incumbent.* If rule 1's interval contains zero the candidate has
   not shown improvement, so the champion stays. Same rule as the protocol's
   "ties go to the simpler model", applied to churn: do not swap a live model for
   noise.

**Fail closed.** Any failure to evaluate — no incumbent, missing artifact,
unreachable tracking server — is a FAIL, never a pass by default. The gate's only
job is to withhold approval, so an inability to check must count as a refusal.

Run:  PYTHONPATH=src python -m credit_default.quality_gate <candidate_run_id>
      (exit code 0 = may proceed, 1 = blocked, 2 = could not evaluate)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import mlflow
import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss

from credit_default.evaluation import (
    month_stratified_bootstrap,
    probabilities,
    split_features,
)
from credit_default.registry import CHAMPION, MODEL_NAME, load, resolve
from credit_default.splits import VALIDATION
from credit_default.tracking import setup_tracking

METRICS = {"pr_auc": average_precision_score, "brier": brier_score_loss}


@dataclass
class GateVerdict:
    passed: bool
    candidate_run_id: str
    incumbent: str
    reasons: list[str] = field(default_factory=list)
    measurements: dict = field(default_factory=dict)

    def report(self) -> str:
        headline = "PASS — candidate may proceed" if self.passed else "FAIL — promotion blocked"
        lines = [
            f"quality gate: {headline}",
            f"  candidate : run {self.candidate_run_id}",
            f"  incumbent : {self.incumbent}",
        ]
        for name, (mean, lo, hi) in self.measurements.items():
            lines.append(f"  {name:<8}: {mean:+.5f}  95% CI [{lo:+.5f}, {hi:+.5f}]")
        lines += [f"  - {reason}" for reason in self.reasons]
        return "\n".join(lines)


def decide(measurements: dict[str, tuple[float, float, float]]) -> tuple[bool, list[str]]:
    """The rules, as a pure function of the measured differences (candidate minus
    incumbent). Separated from all I/O so it is unit-testable without a registry,
    a tracking server, or the raw data."""
    reasons: list[str] = []

    pr_mean, pr_lo, pr_hi = measurements["pr_auc"]
    if pr_lo > 0:
        reasons.append(f"ranking improved beyond noise (PR-AUC +{pr_mean:.5f}, CI excludes 0)")
        ranking_ok = True
    elif pr_hi < 0:
        reasons.append(f"ranking is WORSE beyond noise (PR-AUC {pr_mean:+.5f})")
        ranking_ok = False
    else:
        reasons.append(
            f"ranking difference is within noise (PR-AUC {pr_mean:+.5f}, CI spans 0) "
            "— ties go to the incumbent"
        )
        ranking_ok = False

    # Brier is an error score: LOWER is better, so a positive difference is worse.
    br_mean, br_lo, _ = measurements["brier"]
    if br_lo > 0:
        reasons.append(f"calibration degraded beyond noise (Brier {br_mean:+.5f})")
        calibration_ok = False
    else:
        reasons.append(f"calibration not degraded (Brier {br_mean:+.5f})")
        calibration_ok = True

    return ranking_ok and calibration_ok, reasons


def run_gate(
    candidate_run_id: str,
    incumbent_alias: str = CHAMPION,
    split_name: str = VALIDATION,
) -> GateVerdict:
    """Score both models on the protocol's comparison split and apply the rules."""
    setup_tracking()
    incumbent_version = resolve(incumbent_alias)
    incumbent_label = f"{MODEL_NAME}@{incumbent_alias} (v{incumbent_version})"

    x, y, coverage = split_features(split_name)
    candidate_scores = np.asarray(probabilities(mlflow.get_run(candidate_run_id), x))
    incumbent_scores = load(incumbent_alias).predict_proba(x)[:, 1]

    measurements = month_stratified_bootstrap(
        x, y, candidate_scores, incumbent_scores, METRICS
    )
    passed, reasons = decide(measurements)
    reasons.append(f"evaluated on {split_name}, label coverage {coverage:.3f}")
    return GateVerdict(
        passed=passed,
        candidate_run_id=candidate_run_id,
        incumbent=incumbent_label,
        reasons=reasons,
        measurements=measurements,
    )


def main(candidate_run_id: str) -> int:
    try:
        verdict = run_gate(candidate_run_id)
    except Exception as exc:  # noqa: BLE001 — fail closed, see the module docstring
        print(f"quality gate: CANNOT EVALUATE — {type(exc).__name__}: {exc}")
        print("treating as a refusal; an unverifiable candidate is not promotable.")
        return 2
    print(verdict.report())
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
