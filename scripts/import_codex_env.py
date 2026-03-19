#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
CODEX_DIR = Path.home() / ".codex"
CODEX_CONFIG = CODEX_DIR / "config.toml"
CODEX_AUTH = CODEX_DIR / "auth.json"


def ensure_env_file() -> None:
    if ENV_PATH.exists():
        return
    if ENV_EXAMPLE_PATH.exists():
        ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        return
    ENV_PATH.write_text("", encoding="utf-8")


def load_codex_config() -> dict:
    if not CODEX_CONFIG.exists():
        raise FileNotFoundError(f"未找到 Codex 配置文件: {CODEX_CONFIG}")
    with CODEX_CONFIG.open("rb") as f:
        return tomllib.load(f)


def load_codex_auth() -> dict:
    if not CODEX_AUTH.exists():
        raise FileNotFoundError(f"未找到 Codex 认证文件: {CODEX_AUTH}")
    with CODEX_AUTH.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_active_model(config: dict) -> str:
    profile_name = config.get("profile", "")
    profiles = config.get("profiles", {})
    profile_data = profiles.get(profile_name, {}) if isinstance(profiles, dict) else {}
    return str(profile_data.get("model") or config.get("model") or "").strip()


def get_provider_name(config: dict) -> str:
    return str(config.get("model_provider") or "").strip()


def get_provider_base_url(config: dict, provider_name: str) -> str:
    providers = config.get("model_providers", {})
    if not isinstance(providers, dict):
        return ""
    provider_cfg = providers.get(provider_name, {})
    if not isinstance(provider_cfg, dict):
        return ""
    return str(provider_cfg.get("base_url") or "").strip()


def replace_or_append_env(content: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    line = f"{key}={value}"
    if pattern.search(content):
        return pattern.sub(line, content, count=1)
    if content and not content.endswith("\n"):
        content += "\n"
    return content + line + "\n"


def mask_secret(secret: str) -> str:
    if not secret:
        return "(empty)"
    if len(secret) <= 10:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


def main() -> int:
    ensure_env_file()
    config = load_codex_config()
    auth = load_codex_auth()

    active_model = get_active_model(config)
    provider_name = get_provider_name(config)
    base_url = get_provider_base_url(config, provider_name)
    openai_api_key = str(auth.get("OPENAI_API_KEY") or "").strip()

    if not active_model:
        raise RuntimeError("未从 Codex 配置中解析到 model")
    if not base_url:
        raise RuntimeError("未从 Codex 配置中解析到 base_url")
    if not openai_api_key:
        raise RuntimeError("未从 Codex 认证中解析到 OPENAI_API_KEY")

    content = ENV_PATH.read_text(encoding="utf-8")
    # 使用 openai 兼容映射到 GhostMedia（Trend/Content 均可识别）
    content = replace_or_append_env(content, "GM_LLM_PROVIDER", "openai")
    content = replace_or_append_env(content, "GM_LLM_MODEL", active_model)
    content = replace_or_append_env(content, "GM_LLM_API_BASE", base_url)
    content = replace_or_append_env(content, "GM_LLM_API_KEY", openai_api_key)
    ENV_PATH.write_text(content, encoding="utf-8")

    print("已从 ~/.codex 导入到 .env：")
    print(f"  - provider: openai (来源 model_provider={provider_name or 'unknown'})")
    print(f"  - model: {active_model}")
    print(f"  - base_url: {base_url}")
    print(f"  - key: {mask_secret(openai_api_key)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"导入失败: {exc}")
        raise SystemExit(1)
