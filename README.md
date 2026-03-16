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

已接入初始发布模块：
- `apps/social-auto-upload`（来自 `dreammis/social-auto-upload`，作为首个发布执行器）

## 建议后续目录

- `apps/social-auto-upload`：多平台发布执行
- `agents/topic-researcher`：选题与热点追踪
- `agents/content-collector`：素材采集与清洗
- `agents/video-editor`：自动剪辑流水线
- `agents/copywriter`：文案与标题生成
- `agents/publisher`：发布编排
- `agents/community-manager`：评论互动与私信策略
- `orchestration`：任务调度与状态编排
