from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT_DIR = Path(__file__).resolve().parents[2]
TOKENS_ROOT = ROOT_DIR / "orchestrator" / "runtime" / "tokens"
LOG_ROOT = ROOT_DIR / "social-auto-upload" / "logs" / "douyin_official"
OPEN_BASE = "https://open.douyin.com"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class DouyinOfficialConfig:
    client_key: str
    client_secret: str
    refresh_token: str
    open_id: str
    base_url: str = OPEN_BASE


class DouyinOfficialError(RuntimeError):
    pass


def load_douyin_official_config(env: dict[str, str]) -> DouyinOfficialConfig | None:
    client_key = env.get("DOUYIN_OPEN_CLIENT_KEY", "").strip()
    client_secret = env.get("DOUYIN_OPEN_CLIENT_SECRET", "").strip()
    refresh_token = env.get("DOUYIN_OPEN_REFRESH_TOKEN", "").strip()
    open_id = env.get("DOUYIN_OPEN_OPEN_ID", "").strip()
    if not all([client_key, client_secret, refresh_token, open_id]):
        return None
    return DouyinOfficialConfig(
        client_key=client_key,
        client_secret=client_secret,
        refresh_token=refresh_token,
        open_id=open_id,
    )


class DouyinOfficialPublisher:
    def __init__(self, config: DouyinOfficialConfig):
        self.config = config
        ensure_dir(TOKENS_ROOT)
        ensure_dir(LOG_ROOT)
        self.token_file = TOKENS_ROOT / "douyin_official_token.json"

    def _load_token_cache(self) -> dict[str, Any]:
        if not self.token_file.exists():
            return {}
        return json.loads(self.token_file.read_text(encoding="utf-8"))

    def _save_token_cache(self, data: dict[str, Any]) -> None:
        self.token_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def refresh_access_token(self) -> dict[str, Any]:
        resp = requests.post(
            f"{self.config.base_url}/oauth/refresh_token/",
            data={
                "client_key": self.config.client_key,
                "client_secret": self.config.client_secret,
                "refresh_token": self.config.refresh_token,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        payload = data.get("data") or {}
        if str(payload.get("error_code", "0")) != "0":
            raise DouyinOfficialError(f"刷新 access_token 失败: {data}")
        cache = {
            "access_token": payload.get("access_token", ""),
            "refresh_token": payload.get("refresh_token", self.config.refresh_token),
            "open_id": payload.get("open_id", self.config.open_id),
            "expires_in": payload.get("expires_in", ""),
            "refresh_expires_in": payload.get("refresh_expires_in", ""),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._save_token_cache(cache)
        return cache

    def get_access_token(self) -> tuple[str, str]:
        cache = self._load_token_cache()
        access_token = cache.get("access_token", "").strip()
        open_id = cache.get("open_id", "").strip() or self.config.open_id
        if access_token:
            return access_token, open_id
        cache = self.refresh_access_token()
        return cache["access_token"], cache.get("open_id", self.config.open_id)

    def upload_video(self, access_token: str, video_file: Path) -> dict[str, Any]:
        with video_file.open("rb") as f:
            resp = requests.post(
                f"{self.config.base_url}/video/upload/",
                headers={"access-token": access_token},
                files={"video": (video_file.name, f, "video/mp4")},
                timeout=300,
            )
        resp.raise_for_status()
        data = resp.json()
        payload = data.get("data") or {}
        if str(payload.get("error_code", "0")) != "0":
            raise DouyinOfficialError(f"上传视频失败: {data}")
        video = payload.get("video") or {}
        if not video.get("video_id"):
            raise DouyinOfficialError(f"上传返回缺少 video_id: {data}")
        return data

    def create_video(self, access_token: str, video_id: str, text: str) -> dict[str, Any]:
        resp = requests.post(
            f"{self.config.base_url}/video/create/",
            headers={
                "access-token": access_token,
                "Content-Type": "application/json",
            },
            json={
                "open_id": self.config.open_id,
                "video_id": video_id,
                "text": text,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        payload = data.get("data") or {}
        if str(payload.get("error_code", "0")) != "0":
            raise DouyinOfficialError(f"创建视频失败: {data}")
        return data

    def publish(self, *, video_file: Path, title: str, desc: str, hashtags: list[str]) -> dict[str, Any]:
        access_token, open_id = self.get_access_token()
        text_parts = [title.strip()]
        if desc.strip() and desc.strip() != title.strip():
            text_parts.append(desc.strip())
        if hashtags:
            text_parts.append(" ".join(f"#{tag.strip().lstrip('#')}" for tag in hashtags if tag.strip()))
        text = "\n".join(part for part in text_parts if part).strip()

        upload_result = self.upload_video(access_token, video_file)
        video_id = (((upload_result.get("data") or {}).get("video") or {}).get("video_id") or "").strip()
        create_result = self.create_video(access_token, video_id, text)

        log_dir = ensure_dir(LOG_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S"))
        payload = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "platform": "douyin_official",
            "status": "success",
            "title": title,
            "desc": desc,
            "tags": hashtags,
            "video_file": str(video_file),
            "open_id": open_id,
            "video_id": video_id,
            "item_id": ((create_result.get("data") or {}).get("item_id") or ""),
            "upload_result": upload_result,
            "create_result": create_result,
        }
        (log_dir / "publish.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (log_dir / "publish.md").write_text(
            "\n".join(
                [
                    "# Douyin Official 发布记录",
                    "",
                    f"- 时间：{payload['time']}",
                    f"- 状态：{payload['status']}",
                    f"- 标题：{payload['title']}",
                    f"- open_id：{payload['open_id']}",
                    f"- video_id：{payload['video_id']}",
                    f"- item_id：{payload['item_id'] or '-'}",
                ]
            ),
            encoding="utf-8",
        )
        history = LOG_ROOT / "publish_history.jsonl"
        with history.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "time": payload["time"],
                        "platform": payload["platform"],
                        "status": payload["status"],
                        "title": payload["title"],
                        "item_id": payload["item_id"],
                        "video_id": payload["video_id"],
                        "log_dir": str(log_dir),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        payload["log_dir"] = str(log_dir)
        return payload
