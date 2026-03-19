# 媒体下载器
# 负责下载推文中的图片和视频

import asyncio
import aiohttp
import aiofiles
import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class DownloadResult:
    """下载结果"""

    url: str
    local_path: str
    filename: str
    file_type: str  # 'image' | 'video'
    file_size: int
    success: bool
    error: Optional[str] = None


class MediaDownloader:
    """媒体文件下载器"""

    def __init__(self, config: Dict, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        # 下载目录
        self.download_dir = Path(config.get("download_dir", "data/raw/media"))
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # 子目录
        self.image_dir = self.download_dir / "images"
        self.video_dir = self.download_dir / "videos"
        self.image_dir.mkdir(exist_ok=True)
        self.video_dir.mkdir(exist_ok=True)

        # 并发限制
        self.max_concurrent = config.get("max_concurrent_downloads", 3)
        self.timeout = aiohttp.ClientTimeout(total=config.get("download_timeout", 60))

        # 文件大小限制
        self.max_image_size = config.get("max_image_size", 20 * 1024 * 1024)  # 20MB
        self.max_video_size = config.get("max_video_size", 500 * 1024 * 1024)  # 500MB

        # User-Agent
        self.headers = {
            "User-Agent": config.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
        }

        # 进度统计
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "total_bytes": 0,
        }

    async def download_media(self, media_items: List[Dict]) -> List[DownloadResult]:
        """批量下载媒体文件

        Args:
            media_items: 媒体信息列表，每项包含 url, type 等

        Returns:
            DownloadResult 列表
        """
        self.logger.info(f"开始下载 {len(media_items)} 个媒体文件")
        self.stats["total"] = len(media_items)

        # 去重
        seen_urls = set()
        unique_items = []
        for item in media_items:
            url = item.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_items.append(item)

        if len(unique_items) < len(media_items):
            self.logger.info(f"去重后剩余 {len(unique_items)} 个文件")

        # 使用信号量限制并发
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async with aiohttp.ClientSession(
            timeout=self.timeout, headers=self.headers
        ) as session:
            tasks = [
                self._download_with_semaphore(session, item, semaphore)
                for item in unique_items
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        download_results = []
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"下载任务异常: {result}")
                self.stats["failed"] += 1
            else:
                download_results.append(result)
                if result.success:
                    self.stats["success"] += 1
                    self.stats["total_bytes"] += result.file_size
                else:
                    self.stats["failed"] += 1

        self._log_stats()
        return download_results

    async def _download_with_semaphore(
        self, session: aiohttp.ClientSession, item: Dict, semaphore: asyncio.Semaphore
    ) -> DownloadResult:
        """使用信号量限制的下载"""
        async with semaphore:
            return await self._download_single(session, item)

    async def _download_single(
        self, session: aiohttp.ClientSession, item: Dict
    ) -> DownloadResult:
        """下载单个文件"""
        url = item.get("url")
        file_type = item.get("type", "image")

        if not url:
            return DownloadResult(
                url="",
                local_path="",
                filename="",
                file_type=file_type,
                file_size=0,
                success=False,
                error="URL为空",
            )

        # 生成文件名
        filename = self._generate_filename(url, file_type)

        # 选择保存目录
        if file_type == "video":
            save_dir = self.video_dir
            max_size = self.max_video_size
        else:
            save_dir = self.image_dir
            max_size = self.max_image_size

        local_path = save_dir / filename

        # 检查是否已存在
        if local_path.exists():
            self.logger.debug(f"文件已存在，跳过: {filename}")
            file_size = local_path.stat().st_size
            return DownloadResult(
                url=url,
                local_path=str(local_path),
                filename=filename,
                file_type=file_type,
                file_size=file_size,
                success=True,
            )

        try:
            # 下载文件
            self.logger.debug(f"开始下载: {filename}")

            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}")

                # 检查文件大小
                content_length = response.headers.get("Content-Length")
                if content_length:
                    size = int(content_length)
                    if size > max_size:
                        raise Exception(f"文件过大: {size} > {max_size}")

                # 写入文件
                content = await response.read()

                # 再次检查大小
                if len(content) > max_size:
                    raise Exception(f"文件过大: {len(content)} > {max_size}")

                async with aiofiles.open(local_path, "wb") as f:
                    await f.write(content)

                self.logger.debug(f"下载完成: {filename} ({len(content)} bytes)")

                return DownloadResult(
                    url=url,
                    local_path=str(local_path),
                    filename=filename,
                    file_type=file_type,
                    file_size=len(content),
                    success=True,
                )

        except Exception as e:
            self.logger.error(f"下载失败 {filename}: {e}")
            return DownloadResult(
                url=url,
                local_path="",
                filename=filename,
                file_type=file_type,
                file_size=0,
                success=False,
                error=str(e),
            )

    def _generate_filename(self, url: str, file_type: str) -> str:
        """生成文件名"""
        # 使用 URL hash 作为文件名
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]

        # 获取扩展名
        parsed = urlparse(url)
        path = parsed.path.lower()

        if file_type == "video":
            # 视频扩展名
            if ".mp4" in path:
                ext = "mp4"
            elif ".mov" in path:
                ext = "mov"
            else:
                ext = "mp4"
        else:
            # 图片扩展名
            if ".jpg" in path or ".jpeg" in path:
                ext = "jpg"
            elif ".png" in path:
                ext = "png"
            elif ".gif" in path:
                ext = "gif"
            elif ".webp" in path:
                ext = "webp"
            else:
                ext = "jpg"

        return f"{url_hash}.{ext}"

    def _log_stats(self):
        """输出统计信息"""
        total = self.stats["total"]
        success = self.stats["success"]
        failed = self.stats["failed"]
        skipped = self.stats["skipped"]

        total_mb = self.stats["total_bytes"] / (1024 * 1024)

        self.logger.info("=" * 60)
        self.logger.info("下载统计:")
        self.logger.info(f"  总计: {total} 个文件")
        self.logger.info(f"  成功: {success} 个")
        self.logger.info(f"  失败: {failed} 个")
        self.logger.info(f"  跳过: {skipped} 个")
        self.logger.info(f"  总大小: {total_mb:.2f} MB")
        self.logger.info("=" * 60)
