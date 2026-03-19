#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CONTENT_API = "http://127.0.0.1:8080/api/v1/videos"
DEFAULT_TASK_REQUEST = (
    Path(__file__).resolve().parents[2]
    / "orchestrator"
    / "output"
    / "20260317_023025"
    / "faceless_news"
    / "news_1"
    / "task_request.json"
)


@dataclass(frozen=True)
class StageDef:
    key: str
    label: str
    progress_threshold: int


STAGES = [
    StageDef("script_generation", "脚本确认", 10),
    StageDef("terms_generation", "素材关键词确认", 20),
    StageDef("audio_generation", "口播音频生成", 30),
    StageDef("subtitle_generation", "字幕生成", 40),
    StageDef("material_download", "素材下载", 50),
    StageDef("video_render", "视频拼接与导出", 100),
]

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


def infer_stage(progress: int) -> str:
    for stage in STAGES:
        if progress < stage.progress_threshold:
            return stage.key
    return STAGES[-1].key


def format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    return f"{seconds:.1f}s"


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# 视频生成耗时报告",
        "",
        f"- 任务ID：{summary['task_id']}",
        f"- 开始时间：{summary['started_at']}",
        f"- 结束时间：{summary['ended_at']}",
        f"- 总耗时：{format_seconds(summary['total_duration_seconds'])}",
        f"- 最终状态：{summary['final_state_label']}",
        "",
        "## 阶段耗时",
    ]
    for item in summary["stages"]:
        lines.extend(
            [
                f"- {item['label']}",
                f"  开始：{item.get('started_at', '-')}",
                f"  结束：{item.get('ended_at', '-')}",
                f"  耗时：{format_seconds(item.get('duration_seconds'))}",
                f"  说明：{item.get('note', '')}",
            ]
        )

    lines.extend(["", "## 最终产物"])
    for video in summary.get("videos", []) or []:
        lines.append(f"- {video}")
    if summary.get("materials_count") is not None:
        lines.append(f"- 素材数：{summary['materials_count']}")

    if summary.get("error"):
        lines.extend(["", "## 错误", f"- {summary['error']}"])

    path.write_text("\n".join(lines), encoding="utf-8")


def apply_audio_speed(audio_file: Path, speed: float) -> Path:
    if speed <= 0:
        raise ValueError("voice speed must be > 0")
    if abs(speed - 1.0) < 1e-6:
        return audio_file

    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    temp_file = audio_file.with_name(audio_file.stem + f".x{speed:.2f}.mp3")

    factors = []
    remaining = speed
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(remaining)
    atempo = ",".join(f"atempo={factor:.4f}" for factor in factors)

    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(audio_file),
            "-filter:a",
            atempo,
            str(temp_file),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    temp_file.replace(audio_file)
    return audio_file


def build_custom_audio(audio_provider: str, text: str, output_file: Path, voice_speed: float) -> Path:
    provider = (audio_provider or "").strip().lower()
    if provider == "gtts":
        from gtts import gTTS

        gTTS(text=text, lang="zh-CN").save(str(output_file))
        return apply_audio_speed(output_file, voice_speed)
    raise ValueError(f"不支持的自定义音频提供器: {audio_provider}")


def condense_script(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return text
    sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])", text) if s.strip()]
    picked: list[str] = []
    total = 0
    for sentence in sentences:
        if total + len(sentence) > max_chars and picked:
            break
        picked.append(sentence)
        total += len(sentence)
        if total >= max_chars:
            break
    return "".join(picked) if picked else text[:max_chars]


def build_stage_summary(history: list[dict[str, Any]], ended_at: str, final_state: int) -> list[dict[str, Any]]:
    if not history:
        return []

    start_times: dict[str, float] = {}
    end_times: dict[str, float] = {}

    first_ts = history[0]["timestamp_epoch"]
    previous_end = first_ts
    for stage in STAGES:
        start_times[stage.key] = previous_end
        reached = next((row for row in history if row["progress"] >= stage.progress_threshold), None)
        if reached is not None:
            end_times[stage.key] = reached["timestamp_epoch"]
            previous_end = reached["timestamp_epoch"]
        elif final_state == -1:
            end_times[stage.key] = history[-1]["timestamp_epoch"]
            previous_end = history[-1]["timestamp_epoch"]
            break
        else:
            break

    items: list[dict[str, Any]] = []
    for stage in STAGES:
        started = start_times.get(stage.key)
        ended = end_times.get(stage.key)
        if started is None:
            continue
        duration = None if ended is None else max(0.0, ended - started)
        items.append(
            {
                "key": stage.key,
                "label": stage.label,
                "started_at": datetime.fromtimestamp(started).isoformat(),
                "ended_at": datetime.fromtimestamp(ended).isoformat() if ended is not None else "-",
                "duration_seconds": duration,
                "note": f"达到 progress >= {stage.progress_threshold}",
            }
        )
    return items


def submit_and_monitor(
    task_request_path: Path,
    api_url: str,
    poll_interval: float,
    custom_audio_provider: str,
    max_script_chars: int,
    voice_speed: float,
) -> Path:
    task_request = json.loads(task_request_path.read_text(encoding="utf-8"))
    run_dir = task_request_path.parent / "video_run" / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    task_request["video_script"] = condense_script(
        task_request.get("video_script", ""),
        max_chars=max_script_chars,
    )

    if custom_audio_provider:
        audio_file = build_custom_audio(
            audio_provider=custom_audio_provider,
            text=task_request.get("video_script", ""),
            output_file=run_dir / "custom_audio.mp3",
            voice_speed=voice_speed,
        )
        task_request["custom_audio_file"] = str(audio_file)
        task_request["subtitle_enabled"] = True

    write_json(run_dir / "task_request.snapshot.json", task_request)
    submit_response = http_json(api_url, method="POST", body=task_request)
    write_json(run_dir / "submit_response.json", submit_response)

    task_id = submit_response["data"]["task_id"]
    task_url = api_url.rsplit("/", 1)[0] + f"/tasks/{task_id}"

    history: list[dict[str, Any]] = []
    stage_seen: str | None = None
    started_at_epoch = time.time()
    started_at_iso = datetime.fromtimestamp(started_at_epoch).isoformat()

    while True:
        raw = http_json(task_url)
        task = raw.get("data", {}) or {}
        now_epoch = time.time()
        progress = int(task.get("progress", 0) or 0)
        state = int(task.get("state", 0) or 0)
        stage = infer_stage(progress)

        row = {
            "timestamp": datetime.fromtimestamp(now_epoch).isoformat(),
            "timestamp_epoch": now_epoch,
            "state": state,
            "state_label": STATE_LABELS.get(state, str(state)),
            "progress": progress,
            "stage": stage,
            "materials_count": len(task.get("materials", []) or []),
            "combined_videos_count": len(task.get("combined_videos", []) or []),
            "videos_count": len(task.get("videos", []) or []),
            "error": task.get("error", ""),
        }
        history.append(row)
        with (run_dir / "task_status_history.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

        progress_payload = {
            "task_id": task_id,
            "api_url": api_url,
            "task_url": task_url,
            "started_at": started_at_iso,
            "last_polled_at": row["timestamp"],
            "state": state,
            "state_label": row["state_label"],
            "progress": progress,
            "stage": stage,
            "elapsed_seconds": round(now_epoch - started_at_epoch, 2),
            "materials_count": row["materials_count"],
            "videos": task.get("videos", []) or [],
            "combined_videos": task.get("combined_videos", []) or [],
        }
        write_json(run_dir / "progress.json", progress_payload)
        write_json(run_dir / "last_task_snapshot.json", raw)

        if stage != stage_seen:
            elapsed = now_epoch - started_at_epoch
            print(f"[{row['timestamp']}] 阶段切换 -> {stage} progress={progress} elapsed={elapsed:.1f}s")
            stage_seen = stage
        else:
            print(f"[{row['timestamp']}] state={row['state_label']} progress={progress} stage={stage}")

        if state in {-1, 1}:
            ended_at_iso = row["timestamp"]
            total_duration = now_epoch - started_at_epoch
            summary = {
                "task_id": task_id,
                "started_at": started_at_iso,
                "ended_at": ended_at_iso,
                "total_duration_seconds": total_duration,
                "final_state": state,
                "final_state_label": row["state_label"],
                "videos": task.get("videos", []) or [],
                "combined_videos": task.get("combined_videos", []) or [],
                "materials_count": row["materials_count"],
                "error": task.get("error", ""),
                "stages": build_stage_summary(history, ended_at_iso, state),
            }
            write_json(run_dir / "timing_report.json", summary)
            write_markdown_report(run_dir / "timing_report.md", summary)
            return run_dir

        time.sleep(poll_interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 Faceless 视频任务并记录进度与耗时")
    parser.add_argument(
        "--task-request",
        default=str(DEFAULT_TASK_REQUEST),
        help="task_request.json 路径",
    )
    parser.add_argument(
        "--content-api-url",
        default=DEFAULT_CONTENT_API,
        help="content-vedio-agent /videos 接口地址",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=3.0,
        help="轮询间隔，单位秒",
    )
    parser.add_argument(
        "--custom-audio-provider",
        default="gtts",
        help="可选：先生成自定义音频再提交，如 gtts；留空则走 content 内置 TTS",
    )
    parser.add_argument(
        "--max-script-chars",
        type=int,
        default=220,
        help="提交前压缩口播稿的最大字符数，默认 220，传 0 表示不裁剪",
    )
    parser.add_argument(
        "--voice-speed",
        type=float,
        default=1.5,
        help="自定义音频语速，默认 1.5",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task_request_path = Path(args.task_request).expanduser().resolve()
    if not task_request_path.exists():
        raise FileNotFoundError(f"未找到 task_request.json: {task_request_path}")
    run_dir = submit_and_monitor(
        task_request_path=task_request_path,
        api_url=args.content_api_url,
        poll_interval=args.poll_interval,
        custom_audio_provider=args.custom_audio_provider,
        max_script_chars=args.max_script_chars,
        voice_speed=args.voice_speed,
    )
    print(f"运行报告目录: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
