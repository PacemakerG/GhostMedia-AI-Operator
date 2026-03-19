#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python "${ROOT_DIR}/scripts/import_codex_env.py"
bash "${ROOT_DIR}/scripts/sync_env.sh"
