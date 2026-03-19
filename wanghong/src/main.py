#!/usr/bin/env python3
"""
X 平台内容抓取 + AI 改写主程序

功能：
1. 抓取指定 X 用户的主页内容
2. 下载图片和视频到本地
3. 使用 AI 改写文案
4. 保存为结构化数据

用法：
    python main.py --username Maoshen9527 --limit 20 --style humorous
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# 导入自定义模块
sys.path.insert(0, str(Path(__file__).parent))

from crawler.x_crawler import XCrawler, TweetData
from downloader.media_downloader import MediaDownloader, DownloadResult
from rewriter.ai_rewriter import AIContentRewriter, RewriteResult


class XContentPipeline:
    """X 平台内容处理流水线"""

    def __init__(self, config: Dict):
        self.config = config
        self.logger = self._setup_logging()

        # 初始化各模块
        self.crawler = XCrawler(config, self.logger)
        self.downloader = MediaDownloader(config, self.logger)
        self.rewriter = AIContentRewriter(config, self.logger)

        # 输出目录
        self.output_dir = Path(config.get("output_dir", "data/processed"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info("流水线初始化完成")

    def _setup_logging(self) -> logging.Logger:
        """配置日志"""
        logger = logging.getLogger("XContentPipeline")
        logger.setLevel(logging.INFO)

        # 避免重复添加 handler
        if not logger.handlers:
            # 控制台输出
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

            # 文件输出
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            file_handler = logging.FileHandler(
                log_dir / f"pipeline_{datetime.now():%Y%m%d}.log", encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(console_formatter)
            logger.addHandler(file_handler)

        return logger

    async def process_user(
        self,
        username: str,
        limit: int = 20,
        rewrite_style: str = "humorous",
        skip_download: bool = False,
    ) -> Dict:
        """处理指定用户的内容

        Args:
            username: X 用户名
            limit: 抓取推文数量
            rewrite_style: 改写风格
            skip_download: 是否跳过下载媒体

        Returns:
            处理结果统计
        """
        self.logger.info(f"开始处理用户: @{username}")
        self.logger.info(f"配置: limit={limit}, style={rewrite_style}")

        results = {
            "username": username,
            "timestamp": datetime.now().isoformat(),
            "config": {"limit": limit, "style": rewrite_style},
            "stats": {
                "tweets_fetched": 0,
                "media_downloaded": 0,
                "content_rewritten": 0,
                "errors": 0,
            },
            "data": [],
        }

        try:
            # 步骤 1: 抓取推文
            self.logger.info("步骤 1/3: 抓取推文...")
            tweets = await self.crawler.fetch_user_tweets(
                username=username, limit=limit
            )
            results["stats"]["tweets_fetched"] = len(tweets)
            self.logger.info(f"抓取完成: {len(tweets)} 条推文")

            # 步骤 2: 下载媒体（可选）
            if not skip_download and tweets:
                self.logger.info("步骤 2/3: 下载媒体文件...")

                # 收集所有媒体
                all_media = []
                for tweet in tweets:
                    for media in tweet.media:
                        all_media.append(
                            {
                                "url": media.url,
                                "type": media.type,
                                "tweet_id": tweet.tweet_id,
                            }
                        )

                if all_media:
                    download_results = await self.downloader.download_media(all_media)
                    success_count = sum(1 for r in download_results if r.success)
                    results["stats"]["media_downloaded"] = success_count
                    self.logger.info(f"媒体下载完成: {success_count}/{len(all_media)}")
                else:
                    self.logger.info("没有媒体需要下载")
            else:
                self.logger.info("跳过媒体下载")

            # 步骤 3: AI 改写文案
            self.logger.info("步骤 3/3: AI 改写文案...")

            for i, tweet in enumerate(tweets):
                self.logger.debug(f"改写 {i + 1}/{len(tweets)}: {tweet.tweet_id}")

                try:
                    # 准备上下文
                    context = {
                        "likes": tweet.likes,
                        "retweets": tweet.retweets,
                        "hashtags": tweet.hashtags,
                        "username": tweet.username,
                    }

                    # 调用改写
                    rewrite_result = await self.rewriter.rewrite(
                        content=tweet.content, style=rewrite_style, context=context
                    )

                    # 构建输出数据
                    item = {
                        "original": {
                            "tweet_id": tweet.tweet_id,
                            "username": tweet.username,
                            "content": tweet.content,
                            "created_at": tweet.created_at.isoformat(),
                            "stats": {
                                "likes": tweet.likes,
                                "retweets": tweet.retweets,
                                "replies": tweet.replies,
                                "views": tweet.views,
                            },
                            "hashtags": tweet.hashtags,
                            "mentions": tweet.mentions,
                            "media_count": len(tweet.media),
                        },
                        "rewritten": {
                            "content": rewrite_result.rewritten_text,
                            "style": rewrite_result.style,
                            "hashtags": rewrite_result.hashtags,
                            "emoji_suggestions": rewrite_result.emoji_suggestions,
                            "engagement_score": rewrite_result.engagement_score,
                            "warnings": rewrite_result.warnings,
                        },
                    }

                    results["data"].append(item)
                    results["stats"]["content_rewritten"] += 1

                except Exception as e:
                    self.logger.error(f"改写失败 {tweet.tweet_id}: {e}")
                    results["stats"]["errors"] += 1

                    # 记录错误但继续
                    item = {
                        "original": {
                            "tweet_id": tweet.tweet_id,
                            "content": tweet.content,
                            "error": str(e),
                        },
                        "rewritten": None,
                    }
                    results["data"].append(item)

            self.logger.info(
                f"改写完成: {results['stats']['content_rewritten']}/{len(tweets)}"
            )

        except Exception as e:
            self.logger.error(f"处理失败: {e}")
            results["error"] = str(e)

        # 保存结果
        await self._save_results(results)

        return results

    async def _save_results(self, results: Dict):
        """保存处理结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        username = results["username"]
        filename = f"{username}_{timestamp}.json"
        filepath = self.output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        self.logger.info(f"结果已保存: {filepath}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="X 平台内容抓取 + AI 改写工具")

    parser.add_argument("--username", "-u", required=True, help="X 用户名（不含@）")

    parser.add_argument(
        "--limit", "-l", type=int, default=20, help="抓取推文数量（默认: 20）"
    )

    parser.add_argument(
        "--style",
        "-s",
        default="humorous",
        choices=["humorous", "professional", "emotional", "concise", "storytelling"],
        help="改写风格（默认: humorous）",
    )

    parser.add_argument("--no-download", action="store_true", help="跳过下载媒体文件")

    parser.add_argument(
        "--config", "-c", default="config/config.yaml", help="配置文件路径"
    )

    args = parser.parse_args()

    # 加载配置
    import yaml

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        print("使用默认配置...")
        config = {
            "data_dir": "data/raw",
            "output_dir": "data/processed",
            "download_dir": "data/raw/media",
        }
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

    # 初始化流水线
    pipeline = XContentPipeline(config)

    # 运行处理
    print(f"\n{'=' * 60}")
    print(f"开始处理 X 用户: @{args.username}")
    print(f"配置: limit={args.limit}, style={args.style}")
    print(f"{'=' * 60}\n")

    results = await pipeline.process_user(
        username=args.username,
        limit=args.limit,
        rewrite_style=args.style,
        skip_download=args.no_download,
    )

    # 输出结果摘要
    print(f"\n{'=' * 60}")
    print("处理完成!")
    print(f"{'=' * 60}")
    print(f"推文抓取: {results['stats']['tweets_fetched']} 条")
    print(f"媒体下载: {results['stats']['media_downloaded']} 个")
    print(f"文案改写: {results['stats']['content_rewritten']} 条")
    print(f"错误数量: {results['stats']['errors']} 个")
    print(f"结果文件: data/processed/{results['username']}_*.json")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())
