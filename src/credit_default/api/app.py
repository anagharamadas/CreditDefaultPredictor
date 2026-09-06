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
from fastapi import FastAPI, HTTPException, Response

from credit_default.api.schemas import LoanApplication, ReadyResponse, ScoreResponse
from credit_default.contract import ACCEPTED_SCHEMA
from credit_default.features.serving import payloads_to_frame
from credit_default.threshold import COST_FN, COST_FP, derive_threshold

#: the training contract, minus the column a scoring payload can never carry
SERVING_SCHEMA = ACCEPTED_SCHEMA.remove_columns(["loan_status"])
THRESHOLD = derive_threshold()


def registry_model_loader():
    """Production loader: the registry address, nothing else."""
    from credit_default.registry import CHAMPION, MODEL_NAME, load, resolve
    from credit_default.tracking import setup_tracking

    setup_tracking()
    return load(CHAMPION), MODEL_NAME, resolve(CHAMPION)


def create_app(model_loader: Callable = registry_model_loader) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            model, name, version = model_loader()
            app.state.model, app.state.model_name, app.state.model_version = model, name, version
            app.state.load_error = None
        except Exception as exc:  # noqa: BLE001 — readiness reports any load failure
            app.state.model = None
            app.state.load_error = f"{type(exc).__name__}: {exc}"
        yield

    app = FastAPI(title="credit-default-granting API", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"status": "up"}  # process liveness only; readiness is the real gate

    @app.get("/ready", response_model=ReadyResponse)
    def ready(response: Response) -> ReadyResponse:
        if app.state.model is None:
            response.status_code = 503
            return ReadyResponse(ready=False, detail=app.state.load_error)
        return ReadyResponse(
            ready=True,
            model_name=app.state.model_name,
            model_version=app.state.model_version,
        )

    @app.post("/score", response_model=ScoreResponse)
    def score(application: LoanApplication) -> ScoreResponse:
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
        return ScoreResponse(
            id=payload["id"],
            p_default=p_default,
            decision="decline" if p_default >= THRESHOLD else "fund",
            threshold=THRESHOLD,
            cost_ratio_assumed=f"{COST_FN:g}:{COST_FP:g} (ADR-0003 [ASSUMED])",
            model_name=getattr(app.state, "model_name", "unknown"),
            model_version=getattr(app.state, "model_version", 0),
            scored_at=datetime.now(tz=UTC),
        )

    return app


app = create_app()  # uvicorn credit_default.api.app:app
