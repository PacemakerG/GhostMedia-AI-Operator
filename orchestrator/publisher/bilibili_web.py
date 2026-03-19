from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
from PIL import Image
from playwright.sync_api import BrowserContext, Page, Response, TimeoutError, sync_playwright


ROOT_DIR = Path(__file__).resolve().parents[2]
PUBLISH_LOG_ROOT = ROOT_DIR / "social-auto-upload" / "logs" / "bilibili"
DEFAULT_BILIBILI_URL = "https://member.bilibili.com/platform/upload/video/frame?spm_id_from=333.1007.top_bar.upload"


@dataclass
class PublishPayload:
    video_file: Path
    title: str
    tags: list[str]
    desc: str
    account_file: Path
    cover_file: Path | None = None
    headless: bool = True
    upload_timeout_seconds: int = 1800
    page_url: str = DEFAULT_BILIBILI_URL
    keep_debug_artifacts: bool = False
    stop_after: str = ""


class BilibiliWebPublisher:
    def __init__(self, payload: PublishPayload):
        self.payload = payload
        self.started_at_ts = time.time()
        timestamp_slug = datetime.fromtimestamp(self.started_at_ts).strftime("%Y%m%d_%H%M%S")
        self.run_dir = PUBLISH_LOG_ROOT / timestamp_slug
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir = self.run_dir / "debug"
        self.events: list[dict[str, Any]] = []
        self.video_info = probe_video_info(self.payload.video_file)
        self.generated_cover_path: Path | None = None
        self._flush_events()

    def run(self) -> dict[str, Any]:
        publish_response: dict[str, Any] = {}
        error_message = ""
        browser = None
        context = None
        page = None
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=self.payload.headless,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                    env={
                        **os.environ,
                        "LD_LIBRARY_PATH": f"{os.environ.get('CONDA_PREFIX', '')}/lib:{os.environ.get('LD_LIBRARY_PATH', '')}",
                    },
                )
                context = browser.new_context(viewport={"width": 1440, "height": 2200})
                self._install_cookies(context)
                page = context.new_page()
                page.set_default_timeout(60_000)
                page.goto(self.payload.page_url, wait_until="domcontentloaded", timeout=60_000)
                self._handle_common_popups(page)
                self._ensure_logged_in(page)
                if self._maybe_stop_after("page_ready", page):
                    publish_response = {"data": {"mode": "stopped", "stage": "page_ready"}}
                    return publish_response

                self._upload_video(page)
                if self._maybe_stop_after("upload_complete", page):
                    publish_response = {"data": {"mode": "stopped", "stage": "upload_complete"}}
                    return publish_response
                self._fill_metadata(page)
                if self._maybe_stop_after("metadata_filled", page):
                    publish_response = {"data": {"mode": "stopped", "stage": "metadata_filled"}}
                    return publish_response
                try:
                    self._ensure_cover(page)
                except Exception as cover_exc:
                    self._event("cover_skip", reason=str(cover_exc))
                if self._maybe_stop_after("cover_ready", page):
                    publish_response = {"data": {"mode": "stopped", "stage": "cover_ready"}}
                    return publish_response
                publish_response = self._submit(page)
        except Exception as exc:
            error_message = str(exc)
            if page is not None:
                self._capture_failure(page)
            self._write_report(ok=False, publish_response=publish_response, error_message=error_message)
            raise
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            self._cleanup_debug_artifacts(ok=not error_message)

        self._write_report(ok=True, publish_response=publish_response, error_message="")
        return publish_response

    def _maybe_stop_after(self, stage: str, page: Page) -> bool:
        target = (self.payload.stop_after or "").strip()
        if not target:
            return False
        if target != stage:
            return False
        self._event("stop_after_reached", stage=stage)
        self._write_report(ok=True, publish_response={"data": {"mode": "stopped", "stage": stage}}, error_message="")
        return True

    def _install_cookies(self, context: BrowserContext) -> None:
        data = json.loads(self.payload.account_file.read_text(encoding="utf-8"))
        cookies: list[dict[str, Any]] = []
        for cookie in data["cookie_info"]["cookies"]:
            cookies.append(
                {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": ".bilibili.com",
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                }
            )
        context.add_cookies(cookies)
        self._event("cookies_loaded", count=len(cookies))

    def _ensure_logged_in(self, page: Page) -> None:
        page.wait_for_timeout(8_000)
        if "passport.bilibili.com" in page.url:
            raise RuntimeError("B站投稿页跳转到了登录页，当前 cookie 已失效")
        upload_input_count = page.locator('input[type="file"][accept*=".mp4"]').count()
        body_text = page.locator("body").inner_text()
        ready_markers = [
            "点击上传",
            "上传视频",
            "投稿",
            "拖拽到此区域",
        ]
        if upload_input_count <= 0 and not any(marker in body_text for marker in ready_markers):
            raise RuntimeError("未进入 B 站投稿页，页面内容不符合预期")
        self._event("page_ready", url=page.url)

    def _upload_video(self, page: Page) -> None:
        self._event("upload_start", video_file=str(self.payload.video_file))
        upload_input = page.locator('input[type="file"][accept*=".mp4"]').first
        upload_input.set_input_files(str(self.payload.video_file))
        title_input = page.get_by_placeholder("请输入稿件标题")
        title_input.wait_for(state="visible", timeout=self.payload.upload_timeout_seconds * 1000)
        self._handle_common_popups(page)
        page.locator("text=上传完成").first.wait_for(
            state="visible",
            timeout=self.payload.upload_timeout_seconds * 1000,
        )
        self._event("upload_complete")

    def _fill_metadata(self, page: Page) -> None:
        title_input = page.get_by_placeholder("请输入稿件标题").first
        title_input.click()
        title_input.fill(self.payload.title[:80])

        desc_editor = page.locator('[contenteditable="true"][data-placeholder*="填写更全面"]').first
        desc_editor.click()
        desc_editor.fill("")
        if self.payload.desc:
            desc_editor.type(self.payload.desc, delay=20)

        tag_input = page.get_by_placeholder("按回车键Enter创建标签").first
        for tag in self.payload.tags[:10]:
            clean_tag = tag.strip().lstrip("#")
            if not clean_tag:
                continue
            tag_input.fill(clean_tag)
            tag_input.press("Enter")
            page.wait_for_timeout(400)

        self._handle_common_popups(page)
        self._event(
            "metadata_filled",
            title=self.payload.title,
            tags=self.payload.tags,
        )

    def _ensure_cover(self, page: Page) -> None:
        cover_file = self.payload.cover_file or self._generate_cover_from_video()
        self._event("cover_prepare", cover_file=str(cover_file))
        page.get_by_text("封面设置", exact=True).click()
        cover_editor = page.locator(".cover-editor").first
        cover_editor.wait_for(state="visible", timeout=30_000)
        cover_input = page.locator('input[type="file"][accept="image/png, image/jpeg"]').first
        cover_input.wait_for(state="attached")
        cover_input.set_input_files(str(cover_file))
        page.wait_for_timeout(3_000)
        finish_button = cover_editor.locator(".cover-editor-button .submit").first
        finish_button.wait_for(state="visible", timeout=30_000)
        finish_button.click()
        cover_editor.wait_for(state="hidden", timeout=30_000)
        self._event("cover_ready")

    def _submit(self, page: Page) -> dict[str, Any]:
        publish_button = page.locator("span.submit-add").first
        publish_button.wait_for(state="visible")
        self._event("submit_start")

        def is_submit_response(response: Response) -> bool:
            return (
                response.request.method == "POST"
                and "/x/vu/web/add" in response.url
            )

        with page.expect_response(is_submit_response, timeout=180_000) as response_info:
            publish_button.click()
            self._confirm_submit_if_needed(page)
        response = response_info.value
        body = response.json()
        (self.run_dir / "submit_response.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._event(
            "submit_response",
            status=response.status,
            code=body.get("code"),
            message=body.get("message"),
            aid=(body.get("data") or {}).get("aid"),
            bvid=(body.get("data") or {}).get("bvid"),
        )
        if body.get("code") != 0:
            self._capture_failure(page)
            raise RuntimeError(f"B站投稿失败: {body}")
        return body

    def _confirm_submit_if_needed(self, page: Page) -> None:
        for text in ["确认", "同意"]:
            if self._click_first_visible_text(page, text, timeout_ms=2_000):
                page.wait_for_timeout(500)

    def _handle_common_popups(self, page: Page) -> None:
        for text in ["知道了", "暂不考虑", "同意"]:
            if self._click_first_visible_text(page, text, timeout_ms=1_000):
                page.wait_for_timeout(300)

    def _capture_failure(self, page: Page) -> None:
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(self.debug_dir / "failure.png"), full_page=True)
        except Exception:
            pass
        try:
            (self.debug_dir / "failure.html").write_text(page.content(), encoding="utf-8")
        except Exception:
            pass
        (self.debug_dir / "events.json").write_text(
            json.dumps(self.events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _event(self, step: str, **kwargs: Any) -> None:
        self.events.append(
            {
                "time": datetime.now().isoformat(),
                "step": step,
                **kwargs,
            }
        )
        self._flush_events()

    def _flush_events(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "events.json").write_text(
            json.dumps(self.events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if self.events:
            (self.run_dir / "status.json").write_text(
                json.dumps(self.events[-1], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _click_first_visible_text(self, page: Page, text: str, *, timeout_ms: int) -> bool:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            locator = page.get_by_text(text, exact=True)
            try:
                count = locator.count()
            except Exception:
                count = 0
            for idx in range(count):
                candidate = locator.nth(idx)
                try:
                    if candidate.is_visible():
                        candidate.click()
                        return True
                except Exception:
                    continue
            page.wait_for_timeout(250)
        return False

    def _write_report(self, *, ok: bool, publish_response: dict[str, Any], error_message: str) -> None:
        ended_at_ts = time.time()
        response_data = publish_response.get("data") or {}
        entry = {
            "started_at": datetime.fromtimestamp(self.started_at_ts).isoformat(),
            "ended_at": datetime.fromtimestamp(ended_at_ts).isoformat(),
            "duration_seconds": ended_at_ts - self.started_at_ts,
            "platform": "bilibili",
            "mode": "browser",
            "status": "success" if ok else "failed",
            "video_file": str(self.payload.video_file),
            "title": self.payload.title,
            "tags": self.payload.tags,
            "video_duration_seconds": self.video_info["duration_seconds"],
            "video_duration_text": self.video_info["duration_text"],
            "video_size_bytes": self.video_info["size_bytes"],
            "video_size_text": self.video_info["size_text"],
            "video_resolution": self.video_info["resolution"],
            "aid": response_data.get("aid"),
            "bvid": response_data.get("bvid"),
            "error": error_message,
            "failed_step": self.events[-1]["step"] if self.events else "",
            "events": self.events,
        }
        (self.run_dir / "publish.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        lines = [
            "# Bilibili 网页投稿记录",
            "",
            f"- 时间：{entry['ended_at']}",
            f"- 状态：{entry['status']}",
            f"- 耗时：{entry['duration_seconds']:.1f}s",
            f"- 标题：{entry['title']}",
            f"- 视频时长：{entry['video_duration_text']}",
            f"- 视频大小：{entry['video_size_text']}",
            f"- 分辨率：{entry['video_resolution'] or '-'}",
            f"- 标签：{', '.join(self.payload.tags) if self.payload.tags else '-'}",
            f"- BVID：{entry['bvid'] or '-'}",
            f"- AID：{entry['aid'] or '-'}",
        ]
        if error_message:
            lines.extend(
                [
                    "",
                    "## 错误",
                    "",
                    f"- 失败环节：{entry['failed_step'] or '-'}",
                    f"- 错误：`{error_message}`",
                    f"- 调试目录：`{self.debug_dir}`",
                ]
            )
        (self.run_dir / "publish.md").write_text("\n".join(lines), encoding="utf-8")

        history_file = PUBLISH_LOG_ROOT / "publish_history.jsonl"
        with history_file.open("a", encoding="utf-8") as f:
            history_entry = {
                "time": entry["ended_at"],
                "platform": entry["platform"],
                "status": entry["status"],
                "title": entry["title"],
                "video_duration_text": entry["video_duration_text"],
                "video_size_text": entry["video_size_text"],
                "bvid": entry["bvid"],
                "aid": entry["aid"],
                "failed_step": entry["failed_step"],
                "log_dir": str(self.run_dir),
            }
            f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")

    def _generate_cover_from_video(self) -> Path:
        cover_path = self.run_dir / "generated_cover.jpg"
        reader = imageio.get_reader(str(self.payload.video_file))
        try:
            frame = reader.get_data(0)
        finally:
            reader.close()
        Image.fromarray(frame).save(cover_path, format="JPEG", quality=90)
        self.generated_cover_path = cover_path
        return cover_path

    def _cleanup_debug_artifacts(self, *, ok: bool) -> None:
        if not ok:
            return
        if self.payload.keep_debug_artifacts:
            return
        if self.generated_cover_path and self.generated_cover_path.exists():
            self.generated_cover_path.unlink(missing_ok=True)
        debug_files = list(self.debug_dir.glob("*")) if self.debug_dir.exists() else []
        for path in debug_files:
            path.unlink(missing_ok=True)
        if self.debug_dir.exists():
            self.debug_dir.rmdir()


def parse_caption_from_video(video_file: Path) -> tuple[str, list[str]]:
    candidates = [
        video_file.with_name(f"{video_file.stem}-bili.txt"),
        video_file.with_suffix(".txt"),
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        lines = [line.strip() for line in candidate.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            continue
        title = lines[0]
        tags: list[str] = []
        for line in lines[1:]:
            if "#" not in line:
                continue
            tags.extend(re.findall(r"#([A-Za-z0-9_\u4e00-\u9fa5]+)", line))
        dedup_tags: list[str] = []
        seen = set()
        for tag in tags:
            clean_tag = tag.strip().lstrip("#")
            if not clean_tag or clean_tag in seen:
                continue
            seen.add(clean_tag)
            dedup_tags.append(clean_tag)
        return title, dedup_tags
    return video_file.stem, []


def probe_video_info(video_file: Path) -> dict[str, Any]:
    size_bytes = video_file.stat().st_size
    duration_seconds: float | None = None
    resolution = ""
    try:
        reader = imageio.get_reader(str(video_file))
        try:
            meta = reader.get_meta_data()
            duration_seconds = _safe_float(meta.get("duration"))
            if duration_seconds is None:
                fps = _safe_float(meta.get("fps"))
                nframes = _safe_float(meta.get("nframes"))
                if fps and nframes and not math.isinf(nframes):
                    duration_seconds = nframes / fps
            size = meta.get("size")
            if isinstance(size, tuple) and len(size) == 2:
                resolution = f"{size[0]}x{size[1]}"
        finally:
            reader.close()
    except Exception:
        pass
    return {
        "size_bytes": size_bytes,
        "size_text": format_size(size_bytes),
        "duration_seconds": round(duration_seconds, 2) if duration_seconds is not None else None,
        "duration_text": format_duration(duration_seconds),
        "resolution": resolution,
    }


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def format_size(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{size_bytes}B"


def format_duration(duration_seconds: float | None) -> str:
    if duration_seconds is None:
        return "-"
    total_seconds = max(0, int(round(duration_seconds)))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"
