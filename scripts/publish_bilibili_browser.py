#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from orchestrator.publisher.bilibili_web import BilibiliWebPublisher, PublishPayload, parse_caption_from_video


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通过 Playwright 自动投稿到 B 站")
    parser.add_argument("--video-file", required=True, help="视频绝对路径")
    parser.add_argument(
        "--account-file",
        default=str(ROOT_DIR / "social-auto-upload" / "cookies" / "bilibili_uploader" / "account.json"),
        help="B站 cookie 文件路径",
    )
    parser.add_argument("--title", default="", help="手动标题，优先级高于伴随 txt")
    parser.add_argument("--desc", default="", help="简介，不填则使用标题")
    parser.add_argument("--tags", default="", help="逗号分隔标签，不填则自动从伴随 txt 解析")
    parser.add_argument("--headful", action="store_true", help="使用有头浏览器，便于人工观察")
    parser.add_argument("--upload-timeout", type=int, default=1800, help="等待上传完成的超时时间，单位秒")
    parser.add_argument(
        "--stop-after",
        choices=["page_ready", "upload_complete", "metadata_filled", "cover_ready"],
        default="",
        help="调试/稳定性测试用：达到指定阶段后停止，不提交投稿",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video_file = Path(args.video_file).expanduser().resolve()
    account_file = Path(args.account_file).expanduser().resolve()
    if not video_file.exists():
        raise FileNotFoundError(f"视频不存在: {video_file}")
    if not account_file.exists():
        raise FileNotFoundError(f"cookie 文件不存在: {account_file}")

    parsed_title, parsed_tags = parse_caption_from_video(video_file)
    title = args.title.strip() or parsed_title
    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()] if args.tags.strip() else parsed_tags
    desc = args.desc.strip() or title

    publisher = BilibiliWebPublisher(
        PublishPayload(
            video_file=video_file,
            title=title,
            tags=tags,
            desc=desc,
            account_file=account_file,
            headless=not args.headful,
            upload_timeout_seconds=args.upload_timeout,
            stop_after=args.stop_after,
        )
    )
    result = publisher.run()
    print("B站网页投稿成功")
    if result.get("data"):
        data = result["data"]
        if data.get("bvid"):
            print(f"BVID: {data['bvid']}")
        if data.get("aid"):
            print(f"AID: {data['aid']}")
    print(f"日志目录: {publisher.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
