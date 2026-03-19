# GhostMedia-AI-Operator

全 AI 自媒体运营系统（规划中）。

## 目标

构建一个端到端自动化运营闭环：
- 选题与素材发现
- 内容采集与结构化
- 自动剪辑与封面生成
- 文案与标题生成
- 多平台自动发布
- 评论互动与复盘优化

## 当前阶段

已完成基础模块迁移（根目录）：
- `Trend-grab-agent`：热点抓取与分析
- `content-vedio-agent`：内容生成与视频配音
- `social-auto-upload`：多平台自动发布
- `Riona-AI-Agent`：评论互动运营官（后续接入）

## Stage A 快速开始

1. 初始化环境与配置模板：

```bash
bash scripts/setup_ghostmedia.sh
cp .env.example .env
bash scripts/import_codex_env.sh   # 从 ~/.codex 自动导入模型与Key（可选）
bash scripts/sync_env.sh
```

2. 分模块启动：

```bash
bash scripts/run_trend.sh doctor
bash scripts/run_content.sh api
bash scripts/run_social.sh backend
```

3. 参考手册：
- [Stage A 运行手册](docs/STAGE_A_RUNBOOK.md)
- [配置模板说明](docs/CONFIG_TEMPLATES.md)
- [统一环境变量配置](docs/UNIFIED_ENV.md)
- [热点到发布最小链路](docs/HOT_PIPELINE.md)
- [FacelessNews 无脸快评链路](docs/FACELESS_NEWS.md)
- [导演 Agent 到 Content 协议](docs/DIRECTOR_TO_CONTENT_PIPELINE.md)
- [Faceless 视频运行器](docs/FACELESS_VIDEO_RUNNER.md)

## 建议后续目录

- `Trend-grab-agent`：热点抓取与分析
- `content-vedio-agent`：内容生成与视频配音
- `social-auto-upload`：多平台发布执行
- `Riona-AI-Agent`：互动运营（评论/私信）
- `agents/topic-researcher`：选题与热点追踪
- `agents/content-collector`：素材采集与清洗
- `agents/video-editor`：自动剪辑流水线
- `agents/copywriter`：文案与标题生成
- `agents/publisher`：发布编排
- `agents/community-manager`：评论互动与私信策略
- `orchestration`：任务调度与状态编排
