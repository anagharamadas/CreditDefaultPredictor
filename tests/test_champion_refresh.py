"""Ticket #79: an alias move must reach a RUNNING service, and reach it coherently.

The P9 end-to-end walkthrough found the service loading @champion once and never
looking again: rollback — P11's emergency path — did nothing until a restart, and
during the stale window decisions were recorded under a version the registry had
already retired.

These tests drive the watcher directly rather than through sleep-and-hope. The
background loop is thin (sleep, then call `check_once` in a thread); what needs
proving is `check_once` itself and the fact that scoring reads the swapped record.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from credit_default.api import create_app
from credit_default.api.champion import ChampionWatcher


class VersionedStub:
    """Scores differ by version, so a swap is visible in the OUTPUT, not just in
    metadata — a test that only checked the reported number could pass while the
    old model was still doing the work."""

    def __init__(self, version: int):
        self.version = version

    def predict_proba(self, frame):
        p = np.full(len(frame), 0.1 * self.version)
        return np.column_stack([1 - p, p])


@pytest.fixture()
def registry():
    """A one-line stand-in for the registry: a mutable alias -> version mapping."""
    return {"version": 1, "load_calls": 0, "probe_calls": 0}


@pytest.fixture()
def watcher(registry):
    def loader():
        registry["load_calls"] += 1
        return VersionedStub(registry["version"]), "stub-model", registry["version"]

    def probe():
        registry["probe_calls"] += 1
        return registry["version"]

    return ChampionWatcher(loader=loader, probe=probe, alias="champion", refresh_seconds=0)


def test_a_moved_alias_is_picked_up_without_a_restart(watcher, registry):
    watcher.load_now()
    assert watcher.current.version == 1

    registry["version"] = 3          # the rollback gesture: one alias move
    assert watcher.check_once() is True
    assert watcher.current.version == 3


def test_an_unchanged_alias_does_not_reload_the_model(watcher, registry):
    """The probe is cheap and the load is not. Polling every 30s is only defensible
    if a no-op poll costs one small registry call, not a model download."""
    watcher.load_now()
    assert registry["load_calls"] == 1

    for _ in range(5):
        assert watcher.check_once() is False
    assert registry["load_calls"] == 1      # no reloads
    assert registry["probe_calls"] == 5     # but it did keep checking


def test_the_swap_carries_model_name_and_version_together(watcher, registry):
    """The audit-trail half of #79. Model, name and version are one frozen record,
    so no reader can observe the new model paired with the old version number."""
    watcher.load_now()
    before = watcher.current
    registry["version"] = 2
    watcher.check_once()
    after = watcher.current

    assert before is not after                  # replaced, never mutated in place
    assert before.version == 1 and after.version == 2
    assert after.model.version == after.version  # the model IS the version reported


def test_a_registry_outage_does_not_unseat_a_working_model(registry):
    """A service holding a perfectly good model should not be taken down because
    the registry it no longer needs became unreachable."""
    def loader():
        return VersionedStub(1), "stub-model", 1

    def probe():
        raise ConnectionError("registry unreachable")

    watcher = ChampionWatcher(loader=loader, probe=probe, refresh_seconds=0)
    watcher.load_now()

    assert watcher.check_once() is False
    assert watcher.current.version == 1                     # still serving
    assert watcher.load_error is None                       # readiness stays green
    assert "ConnectionError" in watcher.last_check_error  # but the outage IS visible


def test_a_failed_load_is_reported_rather_than_raised():
    def loader():
        raise ConnectionError("registry unreachable")

    watcher = ChampionWatcher(loader=loader, probe=None, refresh_seconds=0)
    assert watcher.load_now() is None
    assert watcher.current is None
    assert "registry unreachable" in watcher.load_error


def test_scoring_reflects_the_swap_end_to_end(registry, payload):
    """The acceptance criterion, through the real app: move the alias, and both the
    score and the recorded version change on the NEXT request."""
    def loader():
        return VersionedStub(registry["version"]), "stub-model", registry["version"]

    app = create_app(
        model_loader=loader,
        store_opener=None,
        alias_probe=lambda: registry["version"],
        refresh_seconds=0,        # no background loop; this test steps it by hand
    )
    with TestClient(app) as client:
        first = client.post("/score", json=payload).json()
        assert first["model_version"] == 1
        assert first["p_default"] == pytest.approx(0.1)

        registry["version"] = 4
        assert app.state.champion.check_once() is True

        second = client.post("/score", json=payload).json()
        assert second["model_version"] == 4
        assert second["p_default"] == pytest.approx(0.4)

        ready = client.get("/ready").json()
        assert ready["model_version"] == 4
        assert ready["model_alias"] == "champion"


def test_ready_publishes_the_staleness_facts(registry, payload):
    """Bounded staleness is only acceptable if it is observable. /ready has to say
    which alias, which version, and how recently it was confirmed."""
    app = create_app(
        model_loader=lambda: (VersionedStub(1), "stub-model", 1),
        store_opener=None,
        alias_probe=lambda: registry["version"],
        refresh_seconds=30,
    )
    with TestClient(app) as client:
        body = client.get("/ready").json()

    assert body["model_alias"] == "champion"
    assert body["staleness_budget_seconds"] == 30
    assert body["alias_checked_at"] is not None
    assert body["model_loaded_at"] is not None
    assert body["alias_check_error"] is None


def test_polling_can_be_switched_off(payload):
    """MODEL_REFRESH_SECONDS=0 pins a replica to the model it started with. /ready
    reports a null budget so the pinning is visible rather than silent."""
    app = create_app(
        model_loader=lambda: (VersionedStub(1), "stub-model", 1),
        store_opener=None,
        alias_probe=None,
    )
    with TestClient(app) as client:
        body = client.get("/ready").json()

    assert body["ready"] is True
    assert body["staleness_budget_seconds"] is None
