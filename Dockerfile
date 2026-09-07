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

EXPOSE 8000
CMD ["uvicorn", "credit_default.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
