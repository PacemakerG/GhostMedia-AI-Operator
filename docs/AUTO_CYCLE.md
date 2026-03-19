# 自动全流程运行

## 目标

每隔 2 小时自动执行一次完整链路：

1. 热点抓取与改写
2. FacelessNews 包生成
3. 视频渲染
4. 抖音发布
5. B站发布

## 核心机制

- 入口脚本：`bash scripts/run_auto_cycle.sh`
- 主执行器：`orchestrator/src/auto_cycle.py`
- 互斥锁：`orchestrator/runtime/locks/auto_cycle.lock`
- 每轮运行目录：`orchestrator/runtime/jobs/<run_id>/`

每一步都带：

- 超时
- 重试
- 状态落盘
- 失败日志

## 平台降级策略

- 抖音失败：记录失败，继续尝试 B站
- B站失败：最多重试 3 次，之后标记 `skipped_after_retry`
- 任一平台成功：本轮任务视为 `partial_success` 或 `success`
- 两个平台都失败：本轮任务记为 `failed`

## 默认超时

- `hot_pipeline`：25 分钟
- `faceless_news`：5 分钟
- `video_render`：30 分钟
- `publish_douyin`：15 分钟
- `publish_bilibili`：20 分钟

## 常用命令

手动跑一轮：

```bash
bash scripts/run_auto_cycle.sh
```

只验证已有输出目录，不重新抓热点：

```bash
bash scripts/run_auto_cycle.sh \
  --skip-hot-pipeline \
  --source-dir /home/elon/workspace/GhostMedia-AI-Operator/orchestrator/output/20260317_023025
```

只生成到视频，不发布：

```bash
bash scripts/run_auto_cycle.sh --skip-publish
```

做 B站稳定性测试，不真正提交：

```bash
bash scripts/run_auto_cycle.sh --bilibili-stop-after metadata_filled
```

## systemd 部署

当前推荐使用用户级 `systemd --user` 定时器，并开启 `linger`，这样即使退出登录也会继续运行。

```bash
loginctl enable-linger "$USER"
mkdir -p ~/.config/systemd/user
cp deploy/systemd/ghostmedia-auto.service ~/.config/systemd/user/
cp deploy/systemd/ghostmedia-auto.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ghostmedia-auto.timer
```

查看状态：

```bash
systemctl --user status ghostmedia-auto.timer
systemctl --user list-timers | grep ghostmedia-auto
```

## 旧的系统级安装方式

如果你明确要装到 `/etc/systemd/system`，也可以继续使用：

复制配置：

```bash
sudo cp deploy/systemd/ghostmedia-auto.service /etc/systemd/system/
sudo cp deploy/systemd/ghostmedia-auto.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ghostmedia-auto.timer
```

查看状态：

```bash
systemctl status ghostmedia-auto.timer
systemctl list-timers | grep ghostmedia-auto
```

查看最近任务结果：

- `orchestrator/runtime/jobs/<run_id>/summary.json`
- `orchestrator/runtime/jobs/<run_id>/events.jsonl`
- `orchestrator/runtime/jobs/<run_id>/state.json`
