"""Replay harness: selection and ordering rules (fast), plus a live slice."""

import pandas as pd
import pytest

from credit_default.replay import SOURCE, replay_frame


@pytest.fixture(scope="module")
def frame():
    pytest.importorskip("pyarrow")
    from pathlib import Path

    from credit_default.ingest import INTERIM_ACCEPTED

    if not Path(INTERIM_ACCEPTED).exists():
        pytest.skip("interim parquet not built")
    return replay_frame(["2017-01", "2017-02"])


pytestmark = pytest.mark.realdata


def test_only_replay_vintages_are_selected(frame):
    months = set(frame["issue_d"].dt.to_period("M").astype(str))
    assert months == {"2017-01", "2017-02"}
    assert (frame["split"] == "replay").all()


def test_loans_arrive_in_issue_order(frame):
    """A partial run must be a PREFIX of a full one, not a random subset — otherwise
    an interrupted replay silently biases whatever was measured from it."""
    assert frame["issue_d"].is_monotonic_increasing


def test_unlabelled_loans_are_included(frame):
    """At scoring time nobody knows the outcome. Replaying only resolved loans would
    rebuild exactly the survivorship bias this project exists to avoid."""
    assert frame["default"].isna().any(), "replay must carry loans whose outcome is unknown"


def test_36_month_scope_only(frame):
    assert set(frame["term"].astype(str).unique()) == {" 36 months"}


def test_source_tag_is_distinct_from_live_traffic():
    assert SOURCE == "replay"  # the store separates replay from live by this column


@pytest.mark.services
def test_a_small_slice_reaches_the_store():
    """One month, capped, through the real API — proves the loop, not the volume.

    Writes under its OWN traffic tag. Sharing the real `replay` tag once caused this
    test to delete a completed 665,090-row replay during a full-suite run.
    """
    from credit_default.replay import clear_replay_rows, replay_month
    from credit_default.store import open_pool

    tag = "pytest-replay"
    sample = replay_frame(["2017-01"]).head(20)
    stats = replay_month(sample, workers=8, source=tag)
    assert stats["failed"] == 0, stats["failure_sample"]
    assert stats["scored"] == 20

    pool = open_pool()
    try:
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT issue_d, model_version, source FROM predictions"
                " WHERE source = %s AND loan_id = ANY(%s)",
                (tag, [str(i) for i in sample["id"]]),
            ).fetchall()
        assert len(rows) == 20
        # the vintage, not the scoring date, is what drift is measured along
        assert all(str(r[0]).startswith("2017-01") for r in rows)
        assert all(r[2] == tag for r in rows)
    finally:
        pool.close()
        clear_replay_rows(tag)          # only this test's traffic


def test_resume_skips_already_scored_loans(monkeypatch):
    """Resumability is what makes a 55-minute run survivable."""
    from credit_default import replay as module

    monkeypatch.setattr(module, "already_replayed", lambda *a, **k: {"1", "2"})
    frame = pd.DataFrame({"id": ["1", "2", "3"], "month": ["2017-01"] * 3})
    remaining = frame[~frame["id"].astype(str).isin(module.already_replayed())]
    assert remaining["id"].tolist() == ["3"]
