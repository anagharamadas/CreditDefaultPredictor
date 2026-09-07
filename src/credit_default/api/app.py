"""The serving app (ticket #45): champion model, contract-gated, health/readiness.

Request path: pydantic (structure) -> payloads_to_frame (the #28 converter — the
same dtype rebuild the parity tests hold byte-identical) -> the training Pandera
contract minus the target column (bounds + cross-column invariants) -> the ONE
pipeline inside the registered artifact -> decision at the derived threshold.

The model arrives ONLY via `models:/credit-default-granting@champion`; /ready is
false until that load succeeds. create_app(model_loader=...) exists so tests can
inject a stub without a registry.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pandera.errors
from fastapi import FastAPI, Header, HTTPException, Response

from credit_default.api.schemas import LoanApplication, ReadyResponse, ScoreResponse
from credit_default.contract import ACCEPTED_SCHEMA
from credit_default.features.serving import payloads_to_frame
from credit_default.store import build_record, init_schema, open_pool, persist
from credit_default.threshold import COST_FN, COST_FP, derive_threshold

#: the training contract, minus the column a scoring payload can never carry
SERVING_SCHEMA = ACCEPTED_SCHEMA.remove_columns(["loan_status"])
THRESHOLD = derive_threshold()


def registry_model_loader():
    """Production loader: the registry address, nothing else.

    MODEL_ALIAS selects which alias to serve (default `champion`). Promotion and
    rollback move that alias in the registry — this service is not redeployed.
    """
    import os

    from credit_default.registry import CHAMPION, MODEL_NAME, load, resolve
    from credit_default.tracking import setup_tracking

    alias = os.environ.get("MODEL_ALIAS", CHAMPION)
    setup_tracking()
    return load(alias), MODEL_NAME, resolve(alias)


def create_app(
    model_loader: Callable = registry_model_loader,
    store_opener: Callable | None = open_pool,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            model, name, version = model_loader()
            app.state.model, app.state.model_name, app.state.model_version = model, name, version
            app.state.load_error = None
        except Exception as exc:  # noqa: BLE001 — readiness reports any load failure
            app.state.model = None
            app.state.load_error = f"{type(exc).__name__}: {exc}"

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
        if app.state.pool is not None:
            app.state.pool.close()

    app = FastAPI(title="credit-default-granting API", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"status": "up"}  # process liveness only; readiness is the real gate

    @app.get("/ready", response_model=ReadyResponse)
    def ready(response: Response) -> ReadyResponse:
        problems = [p for p in (app.state.load_error, app.state.store_error) if p]
        if app.state.model is None or problems:
            response.status_code = 503
            return ReadyResponse(ready=False, detail="; ".join(problems) or "model not loaded")
        return ReadyResponse(
            ready=True,
            model_name=app.state.model_name,
            model_version=app.state.model_version,
            store_ready=app.state.pool is not None,
        )

    @app.post("/score", response_model=ScoreResponse)
    def score(
        application: LoanApplication,
        # #48 replaces these with middleware-managed request IDs; the replay harness
        # (#50) sets X-Source so replay traffic is distinguishable from live traffic.
        request_id: str | None = Header(default=None, alias="X-Request-ID"),
        request_source: str = Header(default="live", alias="X-Source"),
    ) -> ScoreResponse:
        if app.state.model is None:
            raise HTTPException(status_code=503, detail="model not loaded")

        payload = application.model_dump(mode="json")
        frame = payloads_to_frame([payload])
        try:
            SERVING_SCHEMA.validate(frame, lazy=True)
        except pandera.errors.SchemaErrors as exc:
            failures = exc.failure_cases[["column", "check", "failure_case"]]
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "payload violates the data contract",
                    "violations": failures.head(20).to_dict(orient="records"),
                },
            ) from exc

        p_default = float(app.state.model.predict_proba(frame)[:, 1][0])
        cost_ratio = f"{COST_FN:g}:{COST_FP:g} (ADR-0003 [ASSUMED])"
        response = ScoreResponse(
            id=payload["id"],
            p_default=p_default,
            decision="decline" if p_default >= THRESHOLD else "fund",
            threshold=THRESHOLD,
            cost_ratio_assumed=cost_ratio,
            model_name=getattr(app.state, "model_name", "unknown"),
            model_version=getattr(app.state, "model_version", 0),
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
                request_id=request_id,          # #48 sources this from a header
                source=request_source,
            )
            try:
                persist(app.state.pool, record)
            except Exception as exc:
                # Write policy: a decision that cannot be recorded is not made.
                raise HTTPException(
                    status_code=503,
                    detail=f"decision not recorded, so not returned: {type(exc).__name__}",
                ) from exc
            response.prediction_id = record.prediction_id
        return response

    return app


app = create_app()  # uvicorn credit_default.api.app:app
