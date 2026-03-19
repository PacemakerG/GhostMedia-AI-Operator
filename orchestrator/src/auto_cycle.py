#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrator.publisher.douyin_official import load_douyin_official_config


ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT_DIR / "orchestrator" / "output"
RUNTIME_ROOT = ROOT_DIR / "orchestrator" / "runtime"
JOBS_ROOT = RUNTIME_ROOT / "jobs"
LOCKS_ROOT = RUNTIME_ROOT / "locks"
CONTENT_TASK_ROOT = ROOT_DIR / "content-vedio-agent" / "storage" / "tasks"
SOCIAL_LOG_ROOT = ROOT_DIR / "social-auto-upload" / "logs"


@dataclass(frozen=True)
class StepPolicy:
    timeout_seconds: int
    max_attempts: int
    required: bool = True


POLICIES: dict[str, StepPolicy] = {
    "hot_pipeline": StepPolicy(timeout_seconds=25 * 60, max_attempts=3, required=True),
    "faceless_news": StepPolicy(timeout_seconds=5 * 60, max_attempts=2, required=True),
    "video_render": StepPolicy(timeout_seconds=30 * 60, max_attempts=2, required=True),
    "publish_douyin": StepPolicy(timeout_seconds=15 * 60, max_attempts=3, required=False),
    "publish_bilibili": StepPolicy(timeout_seconds=20 * 60, max_attempts=3, required=False),
}


def parse_env_file(path: Path) -> dict[str, str]:
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
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        data[key.strip()] = value
    return data


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def latest_output_dir() -> Path:
    candidates = [
        path for path in OUTPUT_ROOT.iterdir() if path.is_dir() and (path / "generated.json").exists()
    ]
    if not candidates:
        raise FileNotFoundError("未找到可用的 orchestrator 输出目录")
    candidates.sort(key=lambda p: p.name, reverse=True)
    return candidates[0]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class FileLock:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.fp = None

    def __enter__(self):
        ensure_dir(self.lock_path.parent)
        self.fp = self.lock_path.open("w", encoding="utf-8")
        try:
            fcntl.flock(self.fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"已有自动任务正在运行: {self.lock_path}") from exc
        self.fp.write(f"pid={os.getpid()}\nstarted_at={iso_now()}\n")
        self.fp.flush()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.fp:
            try:
                fcntl.flock(self.fp.fileno(), fcntl.LOCK_UN)
            finally:
                self.fp.close()


class RunContext:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.run_dir = ensure_dir(JOBS_ROOT / run_id)
        self.state_path = self.run_dir / "state.json"
        self.summary_path = self.run_dir / "summary.json"
        self.events_path = self.run_dir / "events.jsonl"
        self.heartbeat_path = self.run_dir / "heartbeat.json"
        self.state: dict[str, Any] = {
            "run_id": run_id,
            "status": "pending",
            "current_step": "",
            "started_at": iso_now(),
            "ended_at": "",
            "steps": {},
            "artifacts": {},
            "platforms": {},
            "errors": [],
        }
        self.flush_state()

    def log_event(self, event: str, **payload: Any) -> None:
        row = {"time": iso_now(), "event": event, **payload}
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.heartbeat_path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_status(self, status: str, current_step: str = "") -> None:
        self.state["status"] = status
        self.state["current_step"] = current_step
        self.flush_state()

    def set_artifact(self, key: str, value: Any) -> None:
        self.state.setdefault("artifacts", {})[key] = value
        self.flush_state()

    def set_platform_result(self, platform: str, result: dict[str, Any]) -> None:
        self.state.setdefault("platforms", {})[platform] = result
        self.flush_state()

    def add_error(self, step: str, error: str) -> None:
        self.state.setdefault("errors", []).append({"step": step, "error": error, "time": iso_now()})
        self.flush_state()

    def set_step_result(self, step: str, result: dict[str, Any]) -> None:
        self.state.setdefault("steps", {})[step] = result
        self.flush_state()

    def finalize(self, status: str) -> None:
        self.state["status"] = status
        self.state["ended_at"] = iso_now()
        self.flush_state()
        self.summary_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def flush_state(self) -> None:
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    root_env = parse_env_file(ROOT_DIR / ".env")
    env.update(root_env)
    conda_prefix = env.get("CONDA_PREFIX", "")
    env["LD_LIBRARY_PATH"] = f"{conda_prefix}/lib:{env.get('LD_LIBRARY_PATH', '')}"
    return env


def run_subprocess(
    *,
    ctx: RunContext,
    step: str,
    attempt: int,
    cmd: list[str],
    timeout_seconds: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    step_dir = ensure_dir(ctx.run_dir / step)
    log_path = step_dir / f"attempt_{attempt}.log"
    ctx.log_event("step_attempt_started", step=step, attempt=attempt, cmd=cmd, timeout_seconds=timeout_seconds)
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT_DIR),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + ("\n" + exc.stderr if exc.stderr else "")
        log_path.write_text(output, encoding="utf-8")
        raise RuntimeError(f"{step} 超时，超过 {timeout_seconds}s") from exc
    except subprocess.CalledProcessError as exc:
        output = (exc.stdout or "") + ("\n" + exc.stderr if exc.stderr else "")
        log_path.write_text(output, encoding="utf-8")
        raise RuntimeError(f"{step} 执行失败: {output.strip()[:800]}") from exc

    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    log_path.write_text(output, encoding="utf-8")
    duration = round(time.time() - started, 2)
    ctx.log_event("step_attempt_succeeded", step=step, attempt=attempt, duration_seconds=duration, log=str(log_path))
    return proc


def run_with_retry(
    *,
    ctx: RunContext,
    step: str,
    cmd_builder,
    parser=None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> Any:
    policy = POLICIES[step]
    last_error = ""
    for attempt in range(1, policy.max_attempts + 1):
        try:
            proc = run_subprocess(
                ctx=ctx,
                step=step,
                attempt=attempt,
                cmd=cmd_builder(attempt),
                timeout_seconds=policy.timeout_seconds,
                cwd=cwd,
                env=env,
            )
            data = parser(proc.stdout + ("\n" + proc.stderr if proc.stderr else "")) if parser else {}
            ctx.set_step_result(
                step,
                {
                    "status": "success",
                    "attempt": attempt,
                    "timeout_seconds": policy.timeout_seconds,
                    "data": data,
                },
            )
            return data
        except Exception as exc:
            last_error = str(exc)
            ctx.log_event("step_attempt_failed", step=step, attempt=attempt, error=last_error)
            if attempt >= policy.max_attempts:
                ctx.set_step_result(
                    step,
                    {
                        "status": "failed",
                        "attempt": attempt,
                        "timeout_seconds": policy.timeout_seconds,
                        "error": last_error,
                    },
                )
                raise
            time.sleep(min(10, attempt * 2))
    raise RuntimeError(last_error or f"{step} 失败")


def parse_output_dir(output: str) -> dict[str, Any]:
    match = re.search(r"输出目录:\s*(.+)", output)
    if not match:
        raise RuntimeError("未从输出中解析到输出目录")
    return {"output_dir": match.group(1).strip()}


def parse_faceless_output(output: str) -> dict[str, Any]:
    match = re.search(r"FacelessNews 输出目录:\s*(.+)", output)
    if not match:
        raise RuntimeError("未从输出中解析到 FacelessNews 输出目录")
    return {"faceless_dir": match.group(1).strip()}


def parse_video_run_output(output: str) -> dict[str, Any]:
    match = re.search(r"运行报告目录:\s*(.+)", output)
    if not match:
        raise RuntimeError("未从输出中解析到视频运行目录")
    return {"video_run_dir": match.group(1).strip()}


def parse_bilibili_publish_output(output: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    patterns = {
        "bvid": r"BVID:\s*(\S+)",
        "aid": r"AID:\s*(\S+)",
        "log_dir": r"日志目录:\s*(.+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if match:
            result[key] = match.group(1).strip()
    if "log_dir" not in result:
        raise RuntimeError("未从输出中解析到 B站日志目录")
    return result


def probe_video_info(video_file: Path) -> dict[str, Any]:
    size_bytes = video_file.stat().st_size
    size_text = f"{size_bytes / 1024 / 1024:.1f}MB"
    return {"size_bytes": size_bytes, "size_text": size_text}


def parse_selected_news(source_dir: Path, news_index: int) -> dict[str, Any]:
    brief_path = source_dir / "faceless_news" / f"news_{news_index}" / "brief.json"
    if not brief_path.exists():
        raise FileNotFoundError(f"未找到 brief.json: {brief_path}")
    return read_json(brief_path)


def ensure_sidecar_files(video_file: Path, brief: dict[str, Any]) -> dict[str, str]:
    title = brief.get("cover_title", video_file.stem)
    hashtags = brief.get("hashtags", []) or []
    caption = brief.get("caption", "")

    default_txt = video_file.with_suffix(".txt")
    default_txt.write_text(
        title + "\n" + " ".join(f"#{tag}" for tag in hashtags) + "\n",
        encoding="utf-8",
    )

    bili_txt = video_file.with_name(f"{video_file.stem}-bili.txt")
    bili_txt.write_text(
        title + "\n" + caption + "\n" + " ".join(f"#{tag}" for tag in hashtags) + "\n",
        encoding="utf-8",
    )
    return {"default_txt": str(default_txt), "bili_txt": str(bili_txt)}


def resolve_video_file(video_run_dir: Path) -> Path:
    submit_response = read_json(video_run_dir / "submit_response.json")
    task_id = submit_response["data"]["task_id"]
    video_file = CONTENT_TASK_ROOT / task_id / "final-1.mp4"
    if not video_file.exists():
        raise FileNotFoundError(f"未找到成片: {video_file}")
    return video_file


def write_douyin_log(run_timestamp: str, video_file: Path, title: str, hashtags: list[str], raw_output: str) -> Path:
    info = probe_video_info(video_file)
    run_dir = ensure_dir(SOCIAL_LOG_ROOT / "douyin" / run_timestamp)
    payload = {
        "started_at": run_timestamp,
        "ended_at": iso_now(),
        "duration_seconds": 0,
        "platform": "douyin",
        "mode": "browser",
        "status": "success",
        "video_file": str(video_file),
        "title": title,
        "tags": hashtags,
        "video_duration_text": "",
        "video_size_bytes": info["size_bytes"],
        "video_size_text": info["size_text"],
        "failed_step": "",
        "error": "",
    }
    (run_dir / "publish.raw.log").write_text(raw_output, encoding="utf-8")
    (run_dir / "publish.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "publish.md").write_text(
        "\n".join(
            [
                "# Douyin 投稿记录",
                "",
                f"- 时间：{payload['ended_at']}",
                f"- 状态：{payload['status']}",
                f"- 标题：{payload['title']}",
                f"- 视频大小：{payload['video_size_text']}",
            ]
        ),
        encoding="utf-8",
    )
    history_path = SOCIAL_LOG_ROOT / "douyin" / "publish_history.jsonl"
    with history_path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "time": payload["ended_at"],
                    "platform": "douyin",
                    "status": payload["status"],
                    "title": payload["title"],
                    "video_duration_text": payload["video_duration_text"],
                    "video_size_text": payload["video_size_text"],
                    "failed_step": payload["failed_step"],
                    "log_dir": str(run_dir.resolve()),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return run_dir


def normalize_bool(value: str, default: bool) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GhostMedia 自动周期任务执行器")
    parser.add_argument("--source-dir", default="", help="复用已有 hot_pipeline 输出目录")
    parser.add_argument("--news-index", type=int, default=0, help="默认发布第几条热点视频；0 表示从 .env 或默认值读取")
    parser.add_argument("--douyin-account", default="", help="抖音账号别名，默认 main 或 .env 配置")
    parser.add_argument("--bilibili-account-file", default="", help="B站账号 cookie 文件路径")
    parser.add_argument("--style-profile", default="", help="内容风格画像，不填则读 .env 或默认 maoshenstyle")
    parser.add_argument("--focus-platforms", default="", help="热点抓取聚焦平台，逗号分隔")
    parser.add_argument("--skip-hot-pipeline", action="store_true", help="跳过热点抓取与文案生成")
    parser.add_argument("--skip-video", action="store_true", help="跳过视频生成，复用已有视频")
    parser.add_argument("--skip-publish", action="store_true", help="只生成到视频，不执行发布")
    parser.add_argument("--bilibili-stop-after", default="", help="B站稳定性测试用 stop-after 参数")
    parser.add_argument("--disable-douyin", action="store_true", help="本轮禁用抖音发布")
    parser.add_argument("--disable-bilibili", action="store_true", help="本轮禁用 B站发布")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = build_env()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    ctx = RunContext(run_id=run_id)
    ctx.set_status("running", "bootstrap")

    news_index = args.news_index or int(env.get("GM_AUTO_NEWS_INDEX", "1") or "1")
    auto_douyin_account = args.douyin_account or env.get("GM_AUTO_DOUYIN_ACCOUNT", "main")
    auto_bili_enabled = normalize_bool(env.get("GM_AUTO_ENABLE_BILIBILI", "true"), default=True) and not args.disable_bilibili
    auto_douyin_enabled = normalize_bool(env.get("GM_AUTO_ENABLE_DOUYIN", "true"), default=True) and not args.disable_douyin
    douyin_official_available = load_douyin_official_config(env) is not None
    style_profile = args.style_profile or env.get("GM_AUTO_STYLE_PROFILE", "maoshenstyle")
    focus_platforms = args.focus_platforms or env.get("GM_AUTO_FOCUS_PLATFORMS", "")
    bilibili_account_file = (
        args.bilibili_account_file
        or env.get("GM_AUTO_BILIBILI_ACCOUNT_FILE", "")
        or str(ROOT_DIR / "social-auto-upload" / "cookies" / "bilibili_uploader" / "account.json")
    )

    ctx.set_artifact(
        "config",
        {
            "news_index": news_index,
            "douyin_account": auto_douyin_account,
            "bilibili_account_file": bilibili_account_file,
            "style_profile": style_profile,
            "focus_platforms": focus_platforms,
            "bilibili_enabled": auto_bili_enabled,
            "douyin_enabled": auto_douyin_enabled,
            "douyin_official_available": douyin_official_available,
        },
    )

    with FileLock(LOCKS_ROOT / "auto_cycle.lock"):
        try:
            if args.source_dir:
                source_dir = Path(args.source_dir).expanduser().resolve()
            elif args.skip_hot_pipeline:
                source_dir = latest_output_dir()
            else:
                ctx.set_status("running", "hot_pipeline")
                ctx.log_event("step_started", step="hot_pipeline")
                hot_data = run_with_retry(
                    ctx=ctx,
                    step="hot_pipeline",
                    cmd_builder=lambda attempt: [
                        "bash",
                        "scripts/run_hot_pipeline.sh",
                        "--style-profile",
                        style_profile,
                        *(["--focus-platforms", focus_platforms] if focus_platforms else []),
                    ],
                    parser=parse_output_dir,
                    env=env,
                )
                source_dir = Path(hot_data["output_dir"]).expanduser().resolve()
                ctx.set_artifact("source_dir", str(source_dir))

            ctx.set_artifact("source_dir", str(source_dir))

            ctx.set_status("running", "faceless_news")
            faceless_data = run_with_retry(
                ctx=ctx,
                step="faceless_news",
                cmd_builder=lambda attempt: [
                    "bash",
                    "scripts/run_faceless_news.sh",
                    "--source-dir",
                    str(source_dir),
                ],
                parser=parse_faceless_output,
                env=env,
            )
            faceless_dir = Path(faceless_data["faceless_dir"]).expanduser().resolve()
            news_dir = faceless_dir / f"news_{news_index}"
            task_request = news_dir / "task_request.json"
            if not task_request.exists():
                raise FileNotFoundError(f"未找到 task_request.json: {task_request}")
            ctx.set_artifact("faceless_dir", str(faceless_dir))
            ctx.set_artifact("news_dir", str(news_dir))

            if args.skip_video:
                video_run_dir = max((news_dir / "video_run").glob("*"), key=lambda p: p.name)
            else:
                ctx.set_status("running", "video_render")
                video_data = run_with_retry(
                    ctx=ctx,
                    step="video_render",
                    cmd_builder=lambda attempt: [
                        "bash",
                        "scripts/run_faceless_video.sh",
                        "--task-request",
                        str(task_request),
                        "--custom-audio-provider",
                        "",
                    ],
                    parser=parse_video_run_output,
                    env=env,
                )
                video_run_dir = Path(video_data["video_run_dir"]).expanduser().resolve()
            ctx.set_artifact("video_run_dir", str(video_run_dir))

            video_file = resolve_video_file(video_run_dir)
            brief = parse_selected_news(source_dir, news_index)
            sidecars = ensure_sidecar_files(video_file, brief)
            ctx.set_artifact("video_file", str(video_file))
            ctx.set_artifact("sidecars", sidecars)

            if args.skip_publish:
                ctx.finalize("ready_for_publish")
                return 0

            partial_success = False
            if auto_douyin_enabled:
                ctx.set_status("running", "publish_douyin")
                title = brief.get("cover_title", video_file.stem)
                hashtags = brief.get("hashtags", []) or []
                try:
                    if douyin_official_available:
                        output = run_with_retry(
                            ctx=ctx,
                            step="publish_douyin",
                            cmd_builder=lambda attempt: [
                                "python",
                                "scripts/publish_douyin_official.py",
                                "--video-file",
                                str(video_file),
                                "--title",
                                title,
                                "--desc",
                                brief.get("caption", title),
                                "--tags",
                                ",".join(hashtags),
                            ],
                            parser=lambda output: {
                                "log_dir": re.search(r"日志目录:\s*(.+)", output).group(1).strip() if re.search(r"日志目录:\s*(.+)", output) else "",
                                "video_id": re.search(r"video_id:\s*(\S+)", output).group(1).strip() if re.search(r"video_id:\s*(\S+)", output) else "",
                                "item_id": re.search(r"item_id:\s*(\S+)", output).group(1).strip() if re.search(r"item_id:\s*(\S+)", output) else "",
                            },
                            env=env,
                        )
                        ctx.set_platform_result(
                            "douyin",
                            {
                                "status": "success",
                                "mode": "official",
                                "log_dir": output.get("log_dir", ""),
                                "video_id": output.get("video_id", ""),
                                "item_id": output.get("item_id", ""),
                            },
                        )
                    else:
                        output = run_with_retry(
                            ctx=ctx,
                            step="publish_douyin",
                            cmd_builder=lambda attempt: [
                                "bash",
                                "scripts/run_social.sh",
                                "cli",
                                "douyin",
                                auto_douyin_account,
                                "upload",
                                str(video_file),
                            ],
                            parser=lambda output: {"raw_output": output},
                            env=env,
                        )
                        douyin_log_dir = write_douyin_log(
                            run_timestamp=datetime.now().strftime("%Y%m%d_%H%M%S"),
                            video_file=video_file,
                            title=title,
                            hashtags=hashtags,
                            raw_output=output["raw_output"],
                        )
                        ctx.set_platform_result(
                            "douyin",
                            {
                                "status": "success",
                                "mode": "browser",
                                "account": auto_douyin_account,
                                "log_dir": str(douyin_log_dir),
                            },
                        )
                    partial_success = True
                except Exception as exc:
                    ctx.add_error("publish_douyin", str(exc))
                    ctx.set_platform_result(
                        "douyin",
                        {
                            "status": "failed",
                            "mode": "official" if douyin_official_available else "browser",
                            "account": auto_douyin_account,
                            "error": str(exc),
                        },
                    )

            if auto_bili_enabled:
                ctx.set_status("running", "publish_bilibili")
                title = brief.get("cover_title", video_file.stem)
                hashtags = ",".join(brief.get("hashtags", []) or [])
                desc = brief.get("caption", title)
                try:
                    bili_data = run_with_retry(
                        ctx=ctx,
                        step="publish_bilibili",
                        cmd_builder=lambda attempt: [
                            "bash",
                            "scripts/run_bilibili_browser_publish.sh",
                            "--video-file",
                            str(video_file),
                            "--account-file",
                            bilibili_account_file,
                            "--title",
                            title,
                            "--tags",
                            hashtags,
                            "--desc",
                            desc,
                            *(["--stop-after", args.bilibili_stop_after] if args.bilibili_stop_after else []),
                        ],
                        parser=parse_bilibili_publish_output,
                        env=env,
                    )
                    ctx.set_platform_result(
                        "bilibili",
                        {
                            "status": "success",
                            "log_dir": bili_data.get("log_dir", ""),
                            "bvid": bili_data.get("bvid", ""),
                            "aid": bili_data.get("aid", ""),
                        },
                    )
                    partial_success = True
                except Exception as exc:
                    ctx.add_error("publish_bilibili", str(exc))
                    ctx.set_platform_result(
                        "bilibili",
                        {
                            "status": "skipped_after_retry",
                            "error": str(exc),
                        },
                    )

            platforms = ctx.state.get("platforms", {})
            all_failed = bool(platforms) and all(item.get("status") not in {"success"} for item in platforms.values())
            if platforms and all_failed:
                ctx.finalize("failed")
                return 1
            if partial_success and platforms and any(item.get("status") != "success" for item in platforms.values()):
                ctx.finalize("partial_success")
                return 0
            ctx.finalize("success")
            return 0
        except Exception as exc:
            ctx.add_error(ctx.state.get("current_step", "unknown"), str(exc))
            ctx.finalize("failed")
            print(f"自动任务失败: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
