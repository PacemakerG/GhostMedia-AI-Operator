# FacelessNews 最小链路

`facelessnews` 用于把热点编排结果转成一套适合短平快“无脸快评视频”的素材包，不直接重写视频引擎，而是复用 `content-vedio-agent`。

## 1. 目标

当前模板定位：

1. 黑底大字开场
2. 快节奏口播
3. B-roll 素材拼接
4. 大字幕居中
5. 结尾提问，引导评论区站队

默认使用 `douyin` 版本文案作为底稿。

## 2. 生成 FacelessNews 素材包

先确保已经跑过热点主链路，目录中存在 `generated.json`。

```bash
bash scripts/run_faceless_news.sh
```

如需指定某一轮热点输出：

```bash
bash scripts/run_faceless_news.sh \
  --source-dir /home/elon/workspace/GhostMedia-AI-Operator/orchestrator/output/20260317_023025
```

## 3. 输出内容

会在对应热点输出目录下新增：

- `faceless_news/README.md`
- `faceless_news/news_1/brief.json`
- `faceless_news/news_1/task_request.json`
- `faceless_news/news_1/script.txt`
- `faceless_news/news_1/caption.txt`
- `faceless_news/news_1/render_content_api.sh`

其中：

- `brief.json`：封面标题、钩子、口播稿、分镜、搜索词
- `task_request.json`：可直接提交给 `content-vedio-agent` 的请求体
- `render_content_api.sh`：调用 `/api/v1/videos` 的最小脚本

## 4. 直接提交视频渲染

先启动视频服务：

```bash
bash scripts/run_content.sh api
```

再生成并直接提交：

```bash
bash scripts/run_faceless_news.sh --submit
```

也可以单独在某个热点目录执行：

```bash
./render_content_api.sh
```

## 5. 当前默认参数

- 文案来源：`douyin`
- 画幅：`9:16`
- 素材源：`pexels`
- 音色：`zh-CN-YunxiNeural-Male`
- 语速：`1.18`
- 字幕位置：`center`

如果 `pexels` 未配置 Key，可以改成 `--video-source local`，但前提是先准备本地素材。
