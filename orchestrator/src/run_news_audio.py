#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CONTENT_AUDIO_API = "http://127.0.0.1:8080/api/v1/audio"
STATE_LABELS = {-1: "FAILED", 1: "COMPLETE", 4: "PROCESSING"}


def http_json(url: str, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_audio_request(task_request: dict[str, Any]) -> dict[str, Any]:
    return {
        "video_script": task_request.get("video_script", ""),
        "voice_name": task_request.get("voice_name", ""),
        "voice_rate": task_request.get("voice_rate", 1.0),
        "voice_volume": task_request.get("voice_volume", 1.0),
        "voice_style": task_request.get("voice_style", ""),
        "voice_style_degree": task_request.get("voice_style_degree", 1.0),
        "voice_role": task_request.get("voice_role", ""),
        "subtitle_enabled": task_request.get("subtitle_enabled", True),
        "custom_audio_file": task_request.get("custom_audio_file", ""),
    }


def submit_and_monitor(task_request_path: Path, api_url: str, poll_interval: float) -> Path:
    task_request = json.loads(task_request_path.read_text(encoding="utf-8"))
    audio_request = build_audio_request(task_request)

    run_dir = task_request_path.parent / "audio_run" / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "audio_request.snapshot.json", audio_request)

    submit_response = http_json(api_url, method="POST", body=audio_request)
    write_json(run_dir / "submit_response.json", submit_response)

    task_id = submit_response["data"]["task_id"]
    task_url = api_url.rsplit("/", 1)[0] + f"/tasks/{task_id}"

    started_at = time.time()
    while True:
        raw = http_json(task_url)
        task = raw.get("data", {}) or {}
        now = time.time()
        state = int(task.get("state", 0) or 0)
        progress = int(task.get("progress", 0) or 0)
        payload = {
            "task_id": task_id,
            "state": state,
            "state_label": STATE_LABELS.get(state, str(state)),
            "progress": progress,
            "elapsed_seconds": round(now - started_at, 2),
            "audio_file": task.get("audio_file", ""),
            "subtitle_path": task.get("subtitle_path", ""),
            "error": task.get("error", ""),
            "last_polled_at": datetime.fromtimestamp(now).isoformat(),
        }
        write_json(run_dir / "progress.json", payload)
        write_json(run_dir / "last_task_snapshot.json", raw)

        print(
            f"[{payload['last_polled_at']}] state={payload['state_label']} "
            f"progress={progress} elapsed={payload['elapsed_seconds']:.1f}s"
        )

        if state in {-1, 1}:
            summary = {
                "task_id": task_id,
                "state": state,
                "state_label": payload["state_label"],
                "elapsed_seconds": payload["elapsed_seconds"],
                "audio_file": task.get("audio_file", ""),
                "subtitle_path": task.get("subtitle_path", ""),
                "error": task.get("error", ""),
            }
            write_json(run_dir / "result.json", summary)
            return run_dir

        time.sleep(poll_interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只生成 news 音频并记录运行结果")
    parser.add_argument("--task-request", required=True, help="task_request.json 路径")
    parser.add_argument(
        "--content-audio-api-url",
        default=DEFAULT_CONTENT_AUDIO_API,
        help="content-vedio-agent /audio 接口地址",
    )
    parser.add_argument("--poll-interval", type=float, default=2.0, help="轮询间隔，秒")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = submit_and_monitor(
        task_request_path=Path(args.task_request).expanduser().resolve(),
        api_url=args.content_audio_api_url,
        poll_interval=args.poll_interval,
    )
    print(f"音频运行目录: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
