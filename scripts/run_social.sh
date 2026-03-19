#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${ROOT_DIR}/social-auto-upload"
ENV_NAME="${GHOSTMEDIA_ENV:-ghostmedia}"
MODE="${1:-backend}"

if command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)"
  conda activate "${ENV_NAME}" || true
fi

if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "${ROOT_DIR}/.env"
  set +a
fi

export LD_LIBRARY_PATH="${CONDA_PREFIX:-}/lib:${LD_LIBRARY_PATH:-}"

python "${ROOT_DIR}/scripts/sync_env.py" >/dev/null

init_social() {
  if [ ! -f "${PROJECT_DIR}/conf.py" ]; then
    cp "${PROJECT_DIR}/conf.example.py" "${PROJECT_DIR}/conf.py"
    echo "已自动创建 social-auto-upload/conf.py"
  fi

  mkdir -p "${PROJECT_DIR}/cookiesFile" "${PROJECT_DIR}/videoFile"

  if [ ! -f "${PROJECT_DIR}/db/database.db" ]; then
    (
      cd "${PROJECT_DIR}/db"
      python createTable.py
    )
  fi
}

cd "${PROJECT_DIR}"
init_social

case "${MODE}" in
  backend)
    exec python sau_backend.py
    ;;
  frontend)
    cd "${PROJECT_DIR}/sau_frontend"
    npm install
    exec npm run dev
    ;;
  cli)
    shift || true
    exec python cli_main.py "$@"
    ;;
  *)
    echo "用法:"
    echo "  bash scripts/run_social.sh backend"
    echo "  bash scripts/run_social.sh frontend"
    echo "  bash scripts/run_social.sh cli <platform> <account_name> <action> ..."
    exit 1
    ;;
esac
