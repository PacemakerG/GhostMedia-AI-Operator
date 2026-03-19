#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${ROOT_DIR}/content-vedio-agent"
ENV_NAME="${GHOSTMEDIA_ENV:-ghostmedia}"
MODE="${1:-api}"

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

python "${ROOT_DIR}/scripts/sync_env.py" >/dev/null

if [ ! -f "${PROJECT_DIR}/config.toml" ]; then
  cp "${PROJECT_DIR}/config.example.toml" "${PROJECT_DIR}/config.toml"
  echo "已自动创建 content-vedio-agent/config.toml"
fi

cd "${PROJECT_DIR}"

case "${MODE}" in
  api)
    exec python main.py
    ;;
  webui)
    exec bash webui.sh
    ;;
  test)
    exec python -m unittest discover -s test
    ;;
  *)
    echo "用法: bash scripts/run_content.sh [api|webui|test]"
    exit 1
    ;;
esac
