#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="${GHOSTMEDIA_ENV:-ghostmedia}"
VIDEO_FILE="${1:-}"
REPEATS="${2:-3}"
STOP_AFTER="${3:-page_ready}"

if [ -z "${VIDEO_FILE}" ]; then
  echo "用法: bash scripts/check_bilibili_browser_stability.sh <video_file> [repeats] [stop_after]"
  echo "示例: bash scripts/check_bilibili_browser_stability.sh /abs/demo.mp4 3 page_ready"
  exit 1
fi

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

export LD_LIBRARY_PATH="${CONDA_PREFIX:-/home/elon/miniconda3/envs/${ENV_NAME}}/lib:${LD_LIBRARY_PATH:-}"

SUCCESS=0
FAIL=0

for ((i=1; i<=REPEATS; i++)); do
  echo "[check ${i}/${REPEATS}] stop_after=${STOP_AFTER}"
  if OUTPUT=$(python "${ROOT_DIR}/scripts/publish_bilibili_browser.py" \
    --video-file "${VIDEO_FILE}" \
    --stop-after "${STOP_AFTER}" 2>&1); then
    echo "${OUTPUT}"
    SUCCESS=$((SUCCESS + 1))
  else
    echo "${OUTPUT}"
    FAIL=$((FAIL + 1))
  fi
  echo
done

echo "B站稳定性检查完成: success=${SUCCESS} fail=${FAIL} stage=${STOP_AFTER}"
if [ "${FAIL}" -gt 0 ]; then
  exit 1
fi
