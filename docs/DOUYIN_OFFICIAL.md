# 抖音官方发布适配器

## 目标

将抖音发布从网页自动化切换到官方开放平台接口，减少 cookie 失效和页面改版导致的中断。

## 入口

- 适配器实现：`orchestrator/publisher/douyin_official.py`
- 手动发布脚本：`python scripts/publish_douyin_official.py ...`

## 必填配置

在根目录 `.env` 中填写：

```bash
DOUYIN_OPEN_CLIENT_KEY=
DOUYIN_OPEN_CLIENT_SECRET=
DOUYIN_OPEN_REFRESH_TOKEN=
DOUYIN_OPEN_OPEN_ID=
```

## 手动发布

```bash
python scripts/publish_douyin_official.py \
  --video-file /absolute/path/demo.mp4 \
  --title "标题" \
  --desc "简介" \
  --tags "热点,评论,新闻"
```

## 自动任务中的行为

如果 `.env` 中存在完整的抖音开放平台配置，`auto_cycle.py` 会优先走官方接口。

如果缺失上述配置，则自动回退到浏览器上传链路。

## 当前限制

首次接入需要你自己在抖音开放平台拿到：

1. 应用 `client_key`
2. 应用 `client_secret`
3. 用户授权后的 `refresh_token`
4. 对应授权用户的 `open_id`
