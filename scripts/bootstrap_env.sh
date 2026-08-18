#!/usr/bin/env bash
# Bootstrap the project environment from a clean machine.
#
# Model: a conda env supplies the Python 3.12 interpreter; uv installs every
# dependency into that same env from uv.lock. There is no separate .venv/.
# See docs/adr/0002-python-environment.md
#
# Usage:  bash scripts/bootstrap_env.sh
# Then:   conda activate credit-default-predictor

set -euo pipefail

ENV_NAME="credit-default-predictor"
PY_VERSION="3.12"

command -v conda >/dev/null || { echo "conda not found on PATH"; exit 1; }
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "==> creating conda env '$ENV_NAME' (python $PY_VERSION)"
  conda create -y -n "$ENV_NAME" "python=$PY_VERSION"
else
  echo "==> conda env '$ENV_NAME' already exists"
fi

conda activate "$ENV_NAME"

echo "==> installing uv into the env"
python -m pip install --quiet --upgrade uv

echo "==> installing activation hooks (UV_PROJECT_ENVIRONMENT)"
mkdir -p "$CONDA_PREFIX/etc/conda/activate.d" "$CONDA_PREFIX/etc/conda/deactivate.d"
cat > "$CONDA_PREFIX/etc/conda/activate.d/uv_project_env.sh" <<'HOOK'
#!/bin/sh
# Point uv at this conda env instead of creating a separate .venv/.
# See docs/adr/0002-python-environment.md
export UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX"
HOOK
cat > "$CONDA_PREFIX/etc/conda/deactivate.d/uv_project_env.sh" <<'HOOK'
#!/bin/sh
unset UV_PROJECT_ENVIRONMENT
HOOK
chmod +x "$CONDA_PREFIX"/etc/conda/*activate.d/uv_project_env.sh
export UV_PROJECT_ENVIRONMENT="$CONDA_PREFIX"

echo "==> syncing pinned dependencies from uv.lock"
uv sync --frozen --inexact

echo "==> verifying"
uv lock --check
python - <<'CHECK'
import importlib.metadata as md
pkgs = ["pandas", "mlflow", "dvc", "prefect", "fastapi", "pandera",
        "pyarrow", "uvicorn", "pytest", "ruff"]
for p in pkgs:
    print(f"  {p:10} {md.version(p)}")
CHECK

echo
echo "Done. Run:  conda activate $ENV_NAME"
