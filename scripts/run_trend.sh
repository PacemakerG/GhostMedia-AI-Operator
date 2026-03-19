#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${ROOT_DIR}/Trend-grab-agent"
ENV_NAME="${GHOSTMEDIA_ENV:-ghostmedia}"
MODE="${1:-run}"

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

if [ -f "${PROJECT_DIR}/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "${PROJECT_DIR}/.env"
  set +a
fi

if [ -z "${TIMEZONE:-}" ] && [ -n "${GM_TIMEZONE:-}" ]; then
  export TIMEZONE="${GM_TIMEZONE}"
fi

if [ -z "${AI_API_KEY:-}" ]; then
  if [ -n "${TREND_AI_API_KEY:-}" ]; then
    export AI_API_KEY="${TREND_AI_API_KEY}"
  elif [ -n "${GM_LLM_API_KEY:-}" ]; then
    export AI_API_KEY="${GM_LLM_API_KEY}"
  fi
fi

if [ -z "${AI_API_BASE:-}" ]; then
  if [ -n "${TREND_AI_API_BASE:-}" ]; then
    export AI_API_BASE="${TREND_AI_API_BASE}"
  elif [ -n "${GM_LLM_API_BASE:-}" ]; then
    export AI_API_BASE="${GM_LLM_API_BASE}"
  fi
fi

if [ -z "${AI_MODEL:-}" ]; then
  if [ -n "${TREND_AI_MODEL:-}" ]; then
    export AI_MODEL="${TREND_AI_MODEL}"
  elif [ -n "${GM_LLM_PROVIDER:-}" ] && [ -n "${GM_LLM_MODEL:-}" ]; then
    export AI_MODEL="${GM_LLM_PROVIDER}/${GM_LLM_MODEL}"
  fi
fi

cd "${PROJECT_DIR}"

case "${MODE}" in
  run)
    exec python -m trendradar
    ;;
  doctor)
    exec python -m trendradar --doctor
    ;;
  schedule)
    exec python -m trendradar --show-schedule
    ;;
  *)
    echo "用法: bash scripts/run_trend.sh [run|doctor|schedule]"
    exit 1
    ;;
esac
