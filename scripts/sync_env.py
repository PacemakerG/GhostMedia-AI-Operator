#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")):
            value = value[1:-1]
        data[key] = value
    return data


def first_non_empty(env: dict[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    return default


def toml_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def toml_array_from_csv(csv_value: str) -> str:
    items = [x.strip() for x in csv_value.split(",") if x.strip()]
    return "[" + ", ".join(toml_str(item) for item in items) + "]"


def py_str(value: str) -> str:
    return repr(value)


def py_bool(value: str, default: bool = False) -> bool:
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def replace_line(content: str, key: str, new_value: str) -> tuple[str, bool]:
    pattern = re.compile(rf"(?m)^(\s*{re.escape(key)}\s*=\s*).*$")
    if not pattern.search(content):
        return content, False
    return pattern.sub(rf"\1{new_value}", content, count=1), True


def ensure_file(dst: Path, src: Path) -> None:
    if not dst.exists() and src.exists():
        shutil.copyfile(src, dst)


def sync_content(env: dict[str, str]) -> list[str]:
    changed_keys: list[str] = []
    config_path = ROOT / "content-vedio-agent" / "config.toml"
    ensure_file(config_path, ROOT / "content-vedio-agent" / "config.example.toml")
    content = config_path.read_text(encoding="utf-8")
    original = content

    provider = first_non_empty(env, "CONTENT_LLM_PROVIDER", "GM_LLM_PROVIDER")
    if provider:
        content, ok = replace_line(content, "llm_provider", toml_str(provider))
        if ok:
            changed_keys.append("content.llm_provider")

    model = first_non_empty(env, "CONTENT_LLM_MODEL", "GM_LLM_MODEL")
    api_key = first_non_empty(env, "CONTENT_LLM_API_KEY", "GM_LLM_API_KEY")
    api_base = first_non_empty(env, "CONTENT_LLM_API_BASE", "GM_LLM_API_BASE")

    provider_fields = {
        "openai": ("openai_api_key", "openai_model_name", "openai_base_url"),
        "deepseek": ("deepseek_api_key", "deepseek_model_name", "deepseek_base_url"),
        "moonshot": ("moonshot_api_key", "moonshot_model_name", "moonshot_base_url"),
        "qwen": ("qwen_api_key", "qwen_model_name", None),
        "gemini": ("gemini_api_key", "gemini_model_name", "gemini_base_url"),
        "ollama": (None, "ollama_model_name", "ollama_base_url"),
        "oneapi": ("oneapi_api_key", "oneapi_model_name", "oneapi_base_url"),
        "azure": ("azure_api_key", "azure_model_name", "azure_base_url"),
        "modelscope": ("modelscope_api_key", "modelscope_model_name", "modelscope_base_url"),
    }

    if provider in provider_fields:
        key_field, model_field, base_field = provider_fields[provider]
        if key_field and api_key:
            content, ok = replace_line(content, key_field, toml_str(api_key))
            if ok:
                changed_keys.append(f"content.{key_field}")
        if model_field and model:
            content, ok = replace_line(content, model_field, toml_str(model))
            if ok:
                changed_keys.append(f"content.{model_field}")
        if base_field and api_base:
            content, ok = replace_line(content, base_field, toml_str(api_base))
            if ok:
                changed_keys.append(f"content.{base_field}")

    pexels_csv = first_non_empty(env, "CONTENT_PEXELS_API_KEYS")
    if pexels_csv:
        content, ok = replace_line(content, "pexels_api_keys", toml_array_from_csv(pexels_csv))
        if ok:
            changed_keys.append("content.pexels_api_keys")

    pixabay_csv = first_non_empty(env, "CONTENT_PIXABAY_API_KEYS")
    if pixabay_csv:
        content, ok = replace_line(content, "pixabay_api_keys", toml_array_from_csv(pixabay_csv))
        if ok:
            changed_keys.append("content.pixabay_api_keys")

    subtitle_provider = first_non_empty(env, "CONTENT_SUBTITLE_PROVIDER")
    if subtitle_provider:
        content, ok = replace_line(content, "subtitle_provider", toml_str(subtitle_provider))
        if ok:
            changed_keys.append("content.subtitle_provider")

    speech_key = first_non_empty(env, "CONTENT_AZURE_SPEECH_KEY", "GM_AZURE_SPEECH_KEY")
    if speech_key:
        content, ok = replace_line(content, "speech_key", toml_str(speech_key))
        if ok:
            changed_keys.append("content.azure.speech_key")

    speech_region = first_non_empty(env, "CONTENT_AZURE_SPEECH_REGION", "GM_AZURE_SPEECH_REGION")
    if speech_region:
        content, ok = replace_line(content, "speech_region", toml_str(speech_region))
        if ok:
            changed_keys.append("content.azure.speech_region")

    if content != original:
        config_path.write_text(content, encoding="utf-8")
    return changed_keys


def sync_social(env: dict[str, str]) -> list[str]:
    changed_keys: list[str] = []
    conf_path = ROOT / "social-auto-upload" / "conf.py"
    ensure_file(conf_path, ROOT / "social-auto-upload" / "conf.example.py")
    content = conf_path.read_text(encoding="utf-8")
    original = content

    chrome_path = first_non_empty(env, "SOCIAL_LOCAL_CHROME_PATH")
    if chrome_path:
        content, ok = replace_line(content, "LOCAL_CHROME_PATH", py_str(chrome_path))
        if ok:
            changed_keys.append("social.LOCAL_CHROME_PATH")

    xhs_server = first_non_empty(env, "SOCIAL_XHS_SERVER")
    if xhs_server:
        content, ok = replace_line(content, "XHS_SERVER", py_str(xhs_server))
        if ok:
            changed_keys.append("social.XHS_SERVER")

    if "SOCIAL_LOCAL_CHROME_HEADLESS" in env:
        bool_val = py_bool(env.get("SOCIAL_LOCAL_CHROME_HEADLESS", ""), default=False)
        content, ok = replace_line(content, "LOCAL_CHROME_HEADLESS", "True" if bool_val else "False")
        if ok:
            changed_keys.append("social.LOCAL_CHROME_HEADLESS")

    if content != original:
        conf_path.write_text(content, encoding="utf-8")
    return changed_keys


def main() -> int:
    if not ENV_FILE.exists():
        print("未找到根目录 .env，已跳过同步。")
        print("请先执行: cp .env.example .env")
        return 0

    env = parse_env(ENV_FILE)
    changed: list[str] = []
    changed.extend(sync_content(env))
    changed.extend(sync_social(env))

    if changed:
        print("已从根 .env 同步以下配置：")
        for item in changed:
            print(f"  - {item}")
    else:
        print("未检测到需要同步的字段（或 .env 中未填写对应值）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
