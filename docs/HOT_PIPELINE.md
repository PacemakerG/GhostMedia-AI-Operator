# 热点到发布最小链路

这个链路用于快速验证：
`抓热点 -> 分类Agent -> 选3条热点 -> 微博/B站/抖音/小红书改写 -> （可选）一键发布`

## 1. 先决条件

1. 根目录 `.env` 已配置 `GM_LLM_API_KEY / GM_LLM_MODEL / GM_LLM_API_BASE`
2. 本链路是“文本生产链路”，`CONTENT_PEXELS_API_KEYS` 不是必填（只有做自动拉视频素材时才需要）
3. 已执行过：

```bash
bash scripts/sync_env.sh
```

## 2. 仅跑内容生产（不发布）

```bash
bash scripts/run_hot_pipeline.sh
```

如需切换写作风格，可增加：

```bash
bash scripts/run_hot_pipeline.sh --style-profile maoshenstyle
```

输出会写入：
- `orchestrator/output/<时间戳>/hotspots.json`
- `orchestrator/output/<时间戳>/category_classification.json`
- `orchestrator/output/<时间戳>/research_report.md`
- `orchestrator/output/<时间戳>/article.md`
- `orchestrator/output/<时间戳>/publish_pack.md`
- `orchestrator/output/<时间戳>/news_packs/news_1.md`
- `orchestrator/output/<时间戳>/news_packs/news_2.md`
- `orchestrator/output/<时间戳>/news_packs/news_3.md`
- `orchestrator/output/<时间戳>/token_usage.json`

其中 `token_usage.json` 会按 agent 记录：
- `classifier_agent`
- `strategy_agent`

并统计 `prompt_tokens / completion_tokens / total_tokens`，每次运行还会追加到：
- `orchestrator/output/token_usage_history.jsonl`

## 3. 跳过抓取，复用最新热点

```bash
bash scripts/run_hot_pipeline.sh --skip-trend
```

## 4. 一键发布（可选）

需要先准备好平台 Cookie 和视频文件。

```bash
bash scripts/run_hot_pipeline.sh \
  --skip-trend \
  --publish \
  --publish-platform douyin \
  --account-name your_account \
  --video-file /absolute/path/demo.mp4
```

脚本会自动生成同名 `demo.txt`（标题+标签）并调用 `social-auto-upload` CLI 上传。

### 发布到 Bilibili

先准备 B站账号文件（默认路径）：
- `social-auto-upload/cookies/bilibili_uploader/account.json`

单独发布（推荐先测）：

```bash
bash scripts/run_bilibili_browser_publish.sh \
  --video-file /absolute/path/demo.mp4
```

在热链路中直接发布到 B站：

```bash
bash scripts/run_hot_pipeline.sh \
  --skip-trend \
  --publish \
  --publish-platform bilibili \
  --video-file /absolute/path/demo.mp4
```

## 5. 当前内置分类Agent

1. 娱乐圈女明星新闻
2. 娱乐圈男明星新闻
3. 国际政治
4. 国内政治
5. 电竞比赛
6. 传统体育比赛
7. 其他热点

## 6. 当前内容结构

每次运行只选 3 条最值得打的热点。每条热点都会生成：

1. 微博版：短促、立场鲜明、适合评论区开打
2. B站版：标题 + 导语 + 相对完整展开
3. 抖音版：开场钩子 + 口播稿 + 配文
4. 小红书版：更强代入感和情绪表达

## 7. 风格画像

当前支持：

1. `maoshenstyle`：猫神风格，强调先下判断、短句、反差、讽刺感和判词式标题

运行结果会在 `generated.json` 中附带 `_style_profile`，便于后续回溯本轮使用的风格参数。
