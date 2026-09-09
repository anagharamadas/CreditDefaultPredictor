"""The gate's rules, tested as pure logic (no registry, no server, no raw data)
plus a live end-to-end check when the stack is up.

`decide()` is deliberately separable from the I/O so these run in CI, where none
of the models exist.
"""

import pytest

from credit_default.quality_gate import decide

# measurements are (mean, ci_low, ci_high) of candidate MINUS incumbent
BETTER_RANKING = (0.021, 0.018, 0.024)      # interval entirely above zero
NOISY_RANKING = (0.004, -0.002, 0.010)      # interval spans zero
WORSE_RANKING = (-0.019, -0.025, -0.013)    # interval entirely below zero
SAME_CALIBRATION = (-0.0001, -0.0009, 0.0007)
WORSE_CALIBRATION = (0.004, 0.002, 0.006)   # Brier up = worse
BETTER_CALIBRATION = (-0.004, -0.006, -0.002)


def test_clear_improvement_passes():
    passed, reasons = decide({"pr_auc": BETTER_RANKING, "brier": SAME_CALIBRATION})
    assert passed
    assert any("beyond noise" in r for r in reasons)


def test_improvement_within_noise_is_a_tie_and_the_incumbent_keeps_the_slot():
    passed, reasons = decide({"pr_auc": NOISY_RANKING, "brier": SAME_CALIBRATION})
    assert not passed  # a higher number alone is not enough
    assert any("ties go to the incumbent" in r for r in reasons)


def test_worse_ranking_fails():
    passed, reasons = decide({"pr_auc": WORSE_RANKING, "brier": SAME_CALIBRATION})
    assert not passed
    assert any("WORSE" in r for r in reasons)


def test_better_ranking_bought_with_worse_calibration_is_refused():
    """The trade this gate exists to prevent: a sharper ranker whose probabilities
    mean less, feeding a threshold derived from probabilities."""
    passed, reasons = decide({"pr_auc": BETTER_RANKING, "brier": WORSE_CALIBRATION})
    assert not passed
    assert any("calibration degraded" in r for r in reasons)


def test_improvement_on_both_axes_passes():
    passed, _ = decide({"pr_auc": BETTER_RANKING, "brier": BETTER_CALIBRATION})
    assert passed


def test_a_model_cannot_pass_on_calibration_alone():
    passed, _ = decide({"pr_auc": NOISY_RANKING, "brier": BETTER_CALIBRATION})
    assert not passed  # rule 1 is the primary metric; rule 2 is only a guard


def test_verdict_report_is_readable():
    from credit_default.quality_gate import GateVerdict

    verdict = GateVerdict(
        passed=False,
        candidate_run_id="abc123",
        incumbent="credit-default-granting@champion (v1)",
        reasons=["ranking difference is within noise"],
        measurements={"pr_auc": NOISY_RANKING},
    )
    report = verdict.report()
    assert "FAIL — promotion blocked" in report
    assert "abc123" in report and "v1" in report
    assert "95% CI" in report


def test_cannot_evaluate_exits_2_not_0():
    """Fail closed: an unverifiable candidate must not be reported as passing."""
    from credit_default.quality_gate import main

    assert main("no-such-run-id") == 2


# --- live check ----------------------------------------------------------------------

@pytest.mark.services
@pytest.mark.realdata
def test_champion_does_not_beat_itself():
    """The incumbent compared against itself is a tie, so the gate must refuse —
    a real end-to-end exercise of the whole path, with a knowable answer."""
    from credit_default.evaluation import latest_runs
    from credit_default.quality_gate import run_gate

    champion_run = latest_runs(families=("lightgbm",))["lightgbm"]
    verdict = run_gate(champion_run)
    assert not verdict.passed
    assert abs(verdict.measurements["pr_auc"][0]) < 1e-9  # identical scores
