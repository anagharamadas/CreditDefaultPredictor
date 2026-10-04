"""The serving app (ticket #45): champion model, contract-gated, health/readiness.

Request path: pydantic (structure) -> payloads_to_frame (the #28 converter — the
same dtype rebuild the parity tests hold byte-identical) -> the training Pandera
contract minus the target column (bounds + cross-column invariants) -> the ONE
pipeline inside the registered artifact -> decision at the derived threshold.

The model arrives ONLY via `models:/credit-default-granting@champion`; /ready is
false until that load succeeds. create_app(model_loader=...) exists so tests can
inject a stub without a registry.

The alias is re-checked in the background (ADR-0006, ticket #79) so that moving it
— promotion, and more importantly rollback — takes effect without a restart. The
served model, its name and its version are swapped together as one frozen record;
see `champion.py` for why that is not a detail.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pandera.errors
from fastapi import FastAPI, Header, HTTPException, Request, Response

from credit_default.api.champion import ChampionWatcher, refresh_seconds_from_env
from credit_default.api.logging_config import (
    REQUEST_ID_HEADER,
    configure_logging,
    current_request_id,
    new_request_id,
    request_id_var,
)
from credit_default.api.schemas import LoanApplication, ReadyResponse, ScoreResponse
from credit_default.contract import ACCEPTED_SCHEMA
from credit_default.features.serving import payloads_to_frame
from credit_default.store import build_record, init_schema, open_pool, persist
from credit_default.threshold import COST_FN, COST_FP, derive_threshold

#: the training contract, minus the column a scoring payload can never carry
SERVING_SCHEMA = ACCEPTED_SCHEMA.remove_columns(["loan_status"])
THRESHOLD = derive_threshold()

log = logging.getLogger("credit_default.api")


def served_alias() -> str:
    """MODEL_ALIAS selects which alias to serve (default `champion`)."""
    import os

    from credit_default.registry import CHAMPION

    return os.environ.get("MODEL_ALIAS", CHAMPION)


def registry_model_loader():
    """Production loader: the registry address, nothing else.

    Promotion and rollback move that alias in the registry — this service is not
    redeployed, and since #79 it is not restarted either.
    """
    from credit_default.registry import MODEL_NAME, load, resolve
    from credit_default.tracking import setup_tracking

    alias = served_alias()
    setup_tracking()
    return load(alias), MODEL_NAME, resolve(alias)


def registry_alias_probe() -> int:
    """The cheap half: which version the alias points at, without loading it."""
    from credit_default.registry import resolve
    from credit_default.tracking import setup_tracking

    setup_tracking()
    return resolve(served_alias())


def create_app(
    model_loader: Callable = registry_model_loader,
    store_opener: Callable | None = open_pool,
    alias_probe: Callable[[], int] | None = registry_alias_probe,
    refresh_seconds: float | None = None,
) -> FastAPI:
    watcher = ChampionWatcher(
        loader=model_loader,
        probe=alias_probe,
        alias=served_alias(),
        refresh_seconds=(
            refresh_seconds_from_env() if refresh_seconds is None else refresh_seconds
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.champion = watcher
        watcher.load_now()
        watcher.start()

        # The store is a readiness dependency, not a nice-to-have: the write policy
        # says an unrecordable decision is not made, so a service that cannot write
        # is not ready to score.
        app.state.pool = None
        app.state.store_error = None
        if store_opener is not None:
            try:
                app.state.pool = store_opener()
                init_schema(app.state.pool)
            except Exception as exc:  # noqa: BLE001 — readiness reports any store failure
                app.state.store_error = f"{type(exc).__name__}: {exc}"
        yield
        await watcher.stop()
        if app.state.pool is not None:
            app.state.pool.close()

    configure_logging()
    app = FastAPI(title="credit-default-granting API", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """One request id per request: accepted from the caller if supplied (so a
        replay batch or an upstream service can correlate), generated otherwise.
        Set as a ContextVar, echoed in the response header, and attached to every
        log line emitted below — including from code that never sees the request."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        # Everything that logs stays INSIDE the try: resetting the ContextVar in a
        # finally that runs before the completion log would strip the id from the
        # one line that most needs it.
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            log.info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            return response
        except Exception:
            log.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise
        finally:
            request_id_var.reset(token)

    @app.get("/health")
    def health() -> dict:
        return {"status": "up"}  # process liveness only; readiness is the real gate

    @app.get("/ready", response_model=ReadyResponse)
    def ready(response: Response) -> ReadyResponse:
        serving = watcher.current
        problems = [p for p in (watcher.load_error, app.state.store_error) if p]
        if serving is None or problems:
            response.status_code = 503
            return ReadyResponse(
                ready=False,
                detail="; ".join(problems) or "model not loaded",
                **watcher.status(),
            )
        # The staleness facts travel with readiness deliberately: "which alias, which
        # version, how recently confirmed" is what an operator needs mid-rollback.
        return ReadyResponse(
            ready=True,
            model_name=serving.name,
            model_version=serving.version,
            model_loaded_at=serving.loaded_at,
            store_ready=app.state.pool is not None,
            **watcher.status(),
        )

    @app.post("/score", response_model=ScoreResponse)
    def score(
        application: LoanApplication,
        # The replay harness (#50) sets X-Source so replay traffic is
        # distinguishable from live traffic in the store. The request id comes from
        # the middleware's ContextVar, not a parameter.
        request_source: str = Header(default="live", alias="X-Source"),
    ) -> ScoreResponse:
        # Read the served model ONCE into a local. A background swap replaces the
        # whole record, so this request finishes against a consistent
        # (model, name, version) triple — it cannot score with one and record the
        # other, which is the audit-trail failure #79 describes.
        serving = watcher.current
        if serving is None:
            log.warning("scoring refused: model not loaded")
            raise HTTPException(status_code=503, detail="model not loaded")

        payload = application.model_dump(mode="json")
        frame = payloads_to_frame([payload])
        try:
            SERVING_SCHEMA.validate(frame, lazy=True)
        except pandera.errors.SchemaErrors as exc:
            failures = exc.failure_cases[["column", "check", "failure_case"]]
            # Log the loan id and the violated COLUMN NAMES only — never the payload
            # (see logging_config's privacy note).
            log.warning(
                "payload rejected by the data contract",
                extra={
                    "loan_id": payload.get("id"),
                    "violated_columns": sorted(set(failures["column"].dropna())),
                    "violation_count": len(failures),
                },
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "payload violates the data contract",
                    "violations": failures.head(20).to_dict(orient="records"),
                },
            ) from exc

        p_default = float(serving.model.predict_proba(frame)[:, 1][0])
        cost_ratio = f"{COST_FN:g}:{COST_FP:g} (ADR-0003 [ASSUMED])"
        response = ScoreResponse(
            id=payload["id"],
            p_default=p_default,
            decision="decline" if p_default >= THRESHOLD else "fund",
            threshold=THRESHOLD,
            cost_ratio_assumed=cost_ratio,
            model_name=serving.name,
            model_version=serving.version,
            scored_at=datetime.now(tz=UTC),
        )

        if app.state.pool is not None:
            record = build_record(
                payload=payload,
                p_default=response.p_default,
                decision=response.decision,
                threshold=response.threshold,
                cost_ratio=cost_ratio,
                model_name=response.model_name,
                model_version=response.model_version,
                scored_at=response.scored_at,
                request_id=current_request_id(),  # threaded by the middleware
                source=request_source,
            )
            try:
                persist(app.state.pool, record)
            except Exception as exc:
                # Write policy: a decision that cannot be recorded is not made.
                log.error(
                    "decision withheld: prediction store write failed",
                    extra={"loan_id": record.loan_id, "error": type(exc).__name__},
                )
                raise HTTPException(
                    status_code=503,
                    detail=f"decision not recorded, so not returned: {type(exc).__name__}",
                ) from exc
            response.prediction_id = record.prediction_id

        log.info(
            "decision",
            extra={
                "loan_id": response.id,
                "p_default": round(response.p_default, 6),
                "decision": response.decision,
                "threshold": round(response.threshold, 4),
                "model_version": response.model_version,
                "prediction_id": response.prediction_id,
                "source": request_source,
            },
        )
        return response

    return app


app = create_app()  # uvicorn credit_default.api.app:app
