#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from orchestrator.publisher.douyin_official import (  # noqa: E402
    DouyinOfficialError,
    DouyinOfficialPublisher,
    load_douyin_official_config,
)


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
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        data[key.strip()] = value
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通过抖音开放平台官方接口发布视频")
    parser.add_argument("--video-file", required=True, help="视频绝对路径")
    parser.add_argument("--title", default="", help="标题")
    parser.add_argument("--desc", default="", help="简介")
    parser.add_argument("--tags", default="", help="逗号分隔标签")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    video_file = Path(args.video_file).expanduser().resolve()
    if not video_file.exists():
        raise FileNotFoundError(f"视频不存在: {video_file}")

    env = parse_env(ROOT_DIR / ".env")
    config = load_douyin_official_config(env)
    if not config:
        raise DouyinOfficialError(
            "缺少抖音开放平台配置，需要在 .env 中填写 DOUYIN_OPEN_CLIENT_KEY / "
            "DOUYIN_OPEN_CLIENT_SECRET / DOUYIN_OPEN_REFRESH_TOKEN / DOUYIN_OPEN_OPEN_ID"
        )

    tags = [x.strip() for x in args.tags.split(",") if x.strip()]
    publisher = DouyinOfficialPublisher(config)
    result = publisher.publish(
        video_file=video_file,
        title=args.title.strip() or video_file.stem,
        desc=args.desc.strip(),
        hashtags=tags,
    )
    print("抖音官方接口发布成功")
    if result.get("video_id"):
        print(f"video_id: {result['video_id']}")
    if result.get("item_id"):
        print(f"item_id: {result['item_id']}")
    print(f"日志目录: {result['log_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
