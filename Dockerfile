# Serving image. Dependencies come from uv.lock — the SAME lockfile the dev
# environment syncs (ADR-0002), so container and laptop run identical versions.
# The image installs into the system interpreter rather than a .venv, mirroring
# that ADR's "one environment, uv-locked" posture.
FROM python:3.12-slim AS base

# libgomp1: LightGBM's native library needs OpenMP — the container equivalent of
# the `brew install libomp` the README records for macOS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

# Dependency layer first: unchanged lockfile -> cached rebuild.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
ENV PYTHONPATH=/app/src

# Run unprivileged: nothing here needs root, and a scoring service reachable over
# the network is exactly the process that should not have it. The home directory
# exists because MLflow writes a download cache there when fetching model
# artifacts from the registry.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

LABEL org.opencontainers.image.title="credit-default-granting API" \
      org.opencontainers.image.source="https://github.com/anagharamadas/CreditDefaultPredictor" \
      org.opencontainers.image.description="Serves the registry champion model behind the training data contract."

EXPOSE 8000
CMD ["uvicorn", "credit_default.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
