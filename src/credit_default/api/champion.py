"""Keeping the served model in step with the registry alias (ticket #79, ADR-0006).

The P9 end-to-end walkthrough found that the service loaded `@champion` once at
startup and never looked again, so moving the alias — which P7 calls "deployment",
and P11 calls "rollback" — did nothing to a running process until it was restarted.
Worse, during that window decisions were *recorded* under the old `model_version`,
so the audit trail disagreed with the registry.

The mechanism chosen (see ADR-0006 for the rejected alternatives) is a background
poll with a bounded, observable staleness window:

- A cheap probe asks the registry only *which version* the alias points at. That is
  one small API call, not a model download, so it can run often.
- A full load happens only when the answer changes.
- The swap is a single assignment of a frozen `ServingModel`. Model, name and
  version travel together, which is the point: as three separate attributes a swap
  landing between two reads could score with the new model and record the old
  version — exactly the inconsistency this ticket is about.
- A probe failure is NOT fatal. The current model keeps serving and the error
  becomes visible on /ready, because a registry outage should not take down a
  service that already has the model it needs.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

log = logging.getLogger("credit_default.api")

#: How long the service may keep serving a superseded alias. Rollback is not
#: instantaneous; it is late by at most this much, and /ready says when it last
#: looked so the lateness is measurable rather than assumed.
DEFAULT_REFRESH_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class ServingModel:
    """What is being served, as one indivisible fact."""

    model: object
    name: str
    version: int
    loaded_at: datetime


class ChampionWatcher:
    """Holds the current `ServingModel` and keeps it in step with the alias.

    `loader()` returns `(model, name, version)` — the expensive path.
    `probe()` returns the version the alias currently points at — the cheap path.
    Both are injectable so tests can move an alias without a registry.
    """

    def __init__(
        self,
        loader: Callable[[], tuple[object, str, int]],
        probe: Callable[[], int] | None = None,
        alias: str = "champion",
        refresh_seconds: float = DEFAULT_REFRESH_SECONDS,
    ) -> None:
        self._loader = loader
        self._probe = probe
        self.alias = alias
        self.refresh_seconds = refresh_seconds

        self.current: ServingModel | None = None
        self.load_error: str | None = None
        self.last_checked_at: datetime | None = None
        self.last_check_error: str | None = None
        self._task: asyncio.Task | None = None

    # --- blocking operations (run in a worker thread from the loop) -------------

    def load_now(self) -> ServingModel | None:
        """Load whatever the alias points at and publish it. Never raises: a load
        failure is reported through readiness, which is the contract /ready has."""
        try:
            model, name, version = self._loader()
        except Exception as exc:  # noqa: BLE001 — readiness reports any load failure
            self.load_error = f"{type(exc).__name__}: {exc}"
            log.error("champion load failed", extra={"alias": self.alias,
                                                     "error": type(exc).__name__})
            return None
        self.load_error = None
        self.current = ServingModel(model, name, int(version), datetime.now(tz=UTC))
        self.last_checked_at = self.current.loaded_at
        return self.current

    def check_once(self) -> bool:
        """One probe-and-maybe-swap cycle. Returns True if the model changed."""
        if self._probe is None:
            return False
        try:
            version = int(self._probe())
        except Exception as exc:  # noqa: BLE001 — a registry blip must not unseat us
            self.last_check_error = f"{type(exc).__name__}: {exc}"
            log.warning("champion check failed; continuing on the loaded model",
                        extra={"alias": self.alias, "error": type(exc).__name__})
            return False
        self.last_check_error = None
        self.last_checked_at = datetime.now(tz=UTC)

        if self.current is not None and version == self.current.version:
            return False

        previous = self.current.version if self.current else None
        if self.load_now() is None:
            return False
        log.info(
            "champion swapped",
            extra={"alias": self.alias, "from_version": previous,
                   "to_version": self.current.version},
        )
        return True

    # --- the loop ---------------------------------------------------------------

    async def run(self) -> None:
        """Poll until cancelled. The blocking registry calls go to a thread so the
        event loop keeps serving requests while a swap downloads a model."""
        while True:
            await asyncio.sleep(self.refresh_seconds)
            await asyncio.to_thread(self.check_once)

    def start(self) -> None:
        if self._probe is not None and self.refresh_seconds > 0:
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    # --- reporting ----------------------------------------------------------------

    def status(self) -> dict:
        """The staleness facts /ready publishes, so a stale window is visible from
        outside rather than inferred from behaviour."""
        return {
            "model_alias": self.alias,
            "alias_checked_at": self.last_checked_at,
            "staleness_budget_seconds": self.refresh_seconds if self._probe else None,
            "alias_check_error": self.last_check_error,
        }


def refresh_seconds_from_env() -> float:
    """`MODEL_REFRESH_SECONDS=0` disables polling — the documented way to pin a
    replica to the model it started with, e.g. while reproducing a past decision."""
    raw = os.environ.get("MODEL_REFRESH_SECONDS")
    return DEFAULT_REFRESH_SECONDS if raw is None else float(raw)
