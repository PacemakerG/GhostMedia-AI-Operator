#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="${1:-ghostmedia}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"

if ! command -v conda >/dev/null 2>&1; then
  echo "未找到 conda，请先安装 Miniconda/Anaconda。"
  exit 1
fi

eval "$(conda shell.bash hook)"

if conda env list | awk '{print $1}' | grep -Fxq "${ENV_NAME}"; then
  echo "Conda 环境已存在: ${ENV_NAME}"
else
  echo "创建 conda 环境: ${ENV_NAME} (python=${PYTHON_VERSION})"
  conda create -y -n "${ENV_NAME}" "python=${PYTHON_VERSION}"
fi

conda activate "${ENV_NAME}"

echo "升级 pip 基础工具..."
python -m pip install --upgrade pip setuptools wheel

echo "安装 Trend-grab-agent 依赖..."
python -m pip install -r "${ROOT_DIR}/Trend-grab-agent/requirements.txt"

echo "安装 content-vedio-agent 依赖..."
python -m pip install -r "${ROOT_DIR}/content-vedio-agent/requirements.txt"

echo "安装 social-auto-upload 依赖..."
python -m pip install -r "${ROOT_DIR}/social-auto-upload/requirements.txt"

if python -c "import playwright" >/dev/null 2>&1; then
  echo "安装 Playwright Chromium 驱动..."
  python -m playwright install chromium
fi

if [ ! -f "${ROOT_DIR}/content-vedio-agent/config.toml" ]; then
  cp "${ROOT_DIR}/content-vedio-agent/config.example.toml" "${ROOT_DIR}/content-vedio-agent/config.toml"
  echo "已初始化 content-vedio-agent/config.toml"
fi

if [ ! -f "${ROOT_DIR}/social-auto-upload/conf.py" ]; then
  cp "${ROOT_DIR}/social-auto-upload/conf.example.py" "${ROOT_DIR}/social-auto-upload/conf.py"
  echo "已初始化 social-auto-upload/conf.py"
fi

mkdir -p "${ROOT_DIR}/social-auto-upload/cookiesFile" "${ROOT_DIR}/social-auto-upload/videoFile"

if [ ! -f "${ROOT_DIR}/social-auto-upload/db/database.db" ]; then
  (
    cd "${ROOT_DIR}/social-auto-upload/db"
    python createTable.py
  )
fi

if [ ! -f "${ROOT_DIR}/Trend-grab-agent/.env" ]; then
  cp "${ROOT_DIR}/Trend-grab-agent/docker/.env" "${ROOT_DIR}/Trend-grab-agent/.env"
  echo "已初始化 Trend-grab-agent/.env（本地覆盖配置）"
fi

if [ ! -f "${ROOT_DIR}/.env" ] && [ -f "${ROOT_DIR}/.env.example" ]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  echo "已初始化根目录 .env（请按需填写密钥）"
fi

python "${ROOT_DIR}/scripts/sync_env.py" || true

echo ""
echo "环境准备完成。"
echo "激活命令: conda activate ${ENV_NAME}"
