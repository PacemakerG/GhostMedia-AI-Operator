# X 平台爬虫模块
# 负责从 X 平台抓取用户推文、图片和视频信息

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

# 模拟导入，实际使用需要安装 twscrape 或类似库
# from twscrape import API, Tweet


@dataclass
class MediaItem:
    """媒体文件信息"""

    url: str
    type: str  # 'image' | 'video'
    filename: str
    size: int = 0
    width: int = 0
    height: int = 0
    duration: float = 0.0  # 视频时长


@dataclass
class TweetData:
    """推文数据结构"""

    tweet_id: str
    username: str
    display_name: str
    content: str
    created_at: datetime
    likes: int
    retweets: int
    replies: int
    views: int
    media: List[MediaItem]
    hashtags: List[str]
    mentions: List[str]
    is_retweet: bool
    is_reply: bool
    quoted_tweet_id: Optional[str] = None

    def to_dict(self) -> Dict:
        """转换为字典"""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


class XCrawler:
    """X 平台爬虫"""

    def __init__(self, config: Dict, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.data_dir = Path(config.get("data_dir", "data/raw"))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 登录凭证
        self.credentials = config.get("x_credentials", {})

        # API 实例（实际使用时初始化）
        self.api = None

        # 请求间隔（防反爬）
        self.request_delay = config.get("request_delay", 2.0)

    async def init_api(self):
        """初始化 X API"""
        self.logger.info("初始化 X API...")
        # 实际实现：
        # from twscrape import API
        # self.api = API()
        # await self.api.login(
        #     username=self.credentials['username'],
        #     password=self.credentials['password']
        # )
        pass

    async def fetch_user_tweets(
        self,
        username: str,
        limit: int = 20,
        include_retweets: bool = False,
        include_replies: bool = False,
    ) -> List[TweetData]:
        """获取指定用户的推文

        Args:
            username: X 用户名（不含@）
            limit: 最多获取条数
            include_retweets: 是否包含转发
            include_replies: 是否包含回复

        Returns:
            TweetData 列表
        """
        self.logger.info(f"开始抓取用户 @{username} 的推文，限制 {limit} 条")

        tweets = []

        # 实际实现：
        # async for tweet in self.api.user_tweets(username, limit=limit):
        #     if not include_retweets and tweet.is_retweet:
        #         continue
        #     if not include_replies and tweet.is_reply:
        #         continue
        #
        #     tweet_data = self._parse_tweet(tweet)
        #     tweets.append(tweet_data)
        #
        #     await asyncio.sleep(self.request_delay)

        # 模拟数据
        tweets = self._generate_mock_tweets(username, limit)

        self.logger.info(f"成功抓取 {len(tweets)} 条推文")

        # 保存原始数据
        await self._save_raw_data(username, tweets)

        return tweets

    def _parse_tweet(self, tweet) -> TweetData:
        """解析推文数据"""
        # 解析媒体文件
        media = []
        # for m in tweet.media:
        #     media.append(MediaItem(...))

        return TweetData(
            tweet_id=str(tweet.id),
            username=tweet.username,
            display_name=tweet.display_name,
            content=tweet.content,
            created_at=tweet.created_at,
            likes=tweet.likes,
            retweets=tweet.retweets,
            replies=tweet.replies,
            views=tweet.views,
            media=media,
            hashtags=tweet.hashtags,
            mentions=tweet.mentions,
            is_retweet=tweet.is_retweet,
            is_reply=tweet.is_reply,
        )

    async def _save_raw_data(self, username: str, tweets: List[TweetData]):
        """保存原始数据到本地"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{username}_{timestamp}.json"
        filepath = self.data_dir / filename

        data = {
            "username": username,
            "crawl_time": datetime.now().isoformat(),
            "tweet_count": len(tweets),
            "tweets": [t.to_dict() for t in tweets],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.logger.info(f"原始数据已保存: {filepath}")

    def _generate_mock_tweets(self, username: str, limit: int) -> List[TweetData]:
        """生成模拟数据（用于测试）"""
        import random

        mock_contents = [
            "今天天气真好，出门散步发现了一只可爱的猫咪！🐱 #猫咪 #生活",
            "刚刚看到的新闻太震撼了，这个世界变化太快...",
            "分享一个有趣的发现：原来猫是这样思考的，太可爱了！",
            "今天的早餐，简简单单但很好吃。大家早上好！",
            "转发一条重要信息，希望能帮到需要的人。",
        ]

        tweets = []
        for i in range(min(limit, len(mock_contents))):
            tweet = TweetData(
                tweet_id=f"mock_{i}_{int(datetime.now().timestamp())}",
                username=username,
                display_name=f"{username} (Test)",
                content=mock_contents[i],
                created_at=datetime.now(),
                likes=random.randint(10, 1000),
                retweets=random.randint(0, 100),
                replies=random.randint(0, 50),
                views=random.randint(1000, 100000),
                media=[],
                hashtags=["测试", "mock"],
                mentions=[],
                is_retweet=False,
                is_reply=False,
            )
            tweets.append(tweet)

        return tweets
