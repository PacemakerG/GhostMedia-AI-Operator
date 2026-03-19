#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
PUBLISH_LOG_ROOT = ROOT_DIR / "orchestrator" / "publish_logs"


def parse_title_and_tags(video_file: Path) -> tuple[str, list[str]]:
    txt_file = video_file.with_suffix(".txt")
    if not txt_file.exists():
        return "", []
    lines = txt_file.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return "", []
    title = lines[0].strip()
    tags: list[str] = []
    if len(lines) > 1:
        tags = [tag.strip().lstrip("#") for tag in lines[1].split() if tag.strip()]
    return title, tags


def append_history(entry: dict[str, Any]) -> None:
    PUBLISH_LOG_ROOT.mkdir(parents=True, exist_ok=True)
    history_file = PUBLISH_LOG_ROOT / "publish_history.jsonl"
    with history_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_markdown_report(path: Path, entry: dict[str, Any]) -> None:
    lines = [
        "# 发布记录",
        "",
        f"- 时间：{entry['ended_at']}",
        f"- 平台：{entry['platform']}",
        f"- 账号：{entry['account_name']}",
        f"- 状态：{entry['status']}",
        f"- 耗时：{entry['duration_seconds']:.1f}s",
        f"- 视频：{entry['video_file']}",
        f"- 标题：{entry['title']}",
        f"- 话题：{', '.join(entry['tags']) if entry['tags'] else '-'}",
    ]
    if entry.get("schedule"):
        lines.append(f"- 定时：{entry['schedule']}")
    lines.extend(["", "## 命令", f"`{' '.join(entry['command'])}`", "", "## 终端输出", "```text"])
    lines.append(entry.get("stdout", "").rstrip())
    lines.append("```")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_publish(platform: str, account_name: str, video_file: Path, publish_type: int, schedule: str) -> Path:
    title, tags = parse_title_and_tags(video_file)

    cmd = [
        "bash",
        "scripts/run_social.sh",
        "cli",
        platform,
        account_name,
        "upload",
        str(video_file),
    ]
    if publish_type:
        cmd.extend(["-pt", str(publish_type)])
    if schedule:
        cmd.extend(["-t", schedule])

    start_ts = time.time()
    started_at = datetime.fromtimestamp(start_ts).isoformat()
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
    )
    end_ts = time.time()
    ended_at = datetime.fromtimestamp(end_ts).isoformat()

    timestamp_slug = datetime.fromtimestamp(end_ts).strftime("%Y%m%d_%H%M%S")
    run_dir = PUBLISH_LOG_ROOT / f"{timestamp_slug}_{platform}_{account_name}"
    run_dir.mkdir(parents=True, exist_ok=True)

    raw_output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    (run_dir / "publish.raw.log").write_text(raw_output, encoding="utf-8")

    entry = {
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": end_ts - start_ts,
        "platform": platform,
        "account_name": account_name,
        "video_file": str(video_file),
        "title": title,
        "tags": tags,
        "publish_type": publish_type,
        "schedule": schedule,
        "command": cmd,
        "return_code": proc.returncode,
        "status": "success" if proc.returncode == 0 else "failed",
        "stdout": raw_output,
    }

    (run_dir / "publish.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown_report(run_dir / "publish.md", entry)
    append_history(entry)

    sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    return run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="带结构化日志的多平台发布运行器")
    parser.add_argument("platform", help="发布平台，如 douyin")
    parser.add_argument("account_name", help="账号别名，如 main")
    parser.add_argument("video_file", help="视频绝对路径")
    parser.add_argument("-pt", "--publish-type", type=int, default=0, choices=[0, 1], help="0 立即发布，1 定时")
    parser.add_argument("-t", "--schedule", default="", help="定时时间，格式 YYYY-MM-DD HH:MM")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video_file = Path(args.video_file).expanduser().resolve()
    if not video_file.exists():
        raise FileNotFoundError(f"视频不存在: {video_file}")
    run_dir = run_publish(
        platform=args.platform,
        account_name=args.account_name,
        video_file=video_file,
        publish_type=args.publish_type,
        schedule=args.schedule,
    )
    print(f"\n发布日志目录: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
