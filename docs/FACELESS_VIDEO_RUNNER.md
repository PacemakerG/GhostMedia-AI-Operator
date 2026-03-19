# Faceless 视频运行器

这个运行器用于在提交 `task_request.json` 后，持续记录视频生成进度，并输出阶段耗时报告。

## 1. 用途

它负责：

1. 提交视频任务到 `content-vedio-agent`
2. 轮询任务状态
3. 记录阶段切换
4. 生成耗时报告
5. 保存最终视频地址

## 2. 使用方式

先确保视频服务已经启动：

```bash
bash scripts/run_content.sh api
```

然后执行：

```bash
bash scripts/run_faceless_video.sh \
  --task-request /home/elon/workspace/GhostMedia-AI-Operator/orchestrator/output/20260317_023025/faceless_news/news_1/task_request.json
```

## 3. 产物

运行后会在对应热点目录新增：

- `video_run/<时间戳>/progress.json`
- `video_run/<时间戳>/last_task_snapshot.json`
- `video_run/<时间戳>/submit_response.json`
- `video_run/<时间戳>/task_status_history.jsonl`
- `video_run/<时间戳>/timing_report.json`
- `video_run/<时间戳>/timing_report.md`

## 4. 当前阶段划分

当前按 `content-vedio-agent` 的 `progress` 值划分：

1. `script_generation`
2. `terms_generation`
3. `audio_generation`
4. `subtitle_generation`
5. `material_download`
6. `video_render`

这些阶段分别对应脚本确认、关键词确认、口播生成、字幕生成、素材下载、视频导出。
